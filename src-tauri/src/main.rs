// Keep a login-launched build from flashing a console window on Windows.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod config;
mod detect;
mod poller;
mod supervisor;

use config::TrayConfig;
use serde::Serialize;
use std::sync::Mutex;
use std::time::{Duration, Instant};
use supervisor::{Status, Supervisor};
use tauri::image::Image;
use tauri::menu::{MenuBuilder, MenuItem, MenuItemBuilder, PredefinedMenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{AppHandle, Manager, Wry};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_opener::OpenerExt;

const TRAY_ID: &str = "tt-main";

struct MenuHandles {
    spend: MenuItem<Wry>,
    status: MenuItem<Wry>,
    toggle: MenuItem<Wry>,
}

struct AppState {
    cfg: Mutex<TrayConfig>,
    sup: Mutex<Supervisor>,
    spend: Mutex<Option<f64>>,
    /// The API answers well before `next dev` has compiled its first route.
    /// Without this the menu says "Running" and "Open dashboard" lands the user
    /// on a connection-refused page.
    front_ready: Mutex<bool>,
    menu: Mutex<Option<MenuHandles>>,
    /// When the current start attempt began, so a stuck start eventually
    /// reports an error instead of saying "Starting…" indefinitely.
    starting_since: Mutex<Option<Instant>>,
}

impl AppState {
    fn new(cfg: TrayConfig) -> Self {
        Self {
            cfg: Mutex::new(cfg),
            sup: Mutex::new(Supervisor::new()),
            spend: Mutex::new(None),
            front_ready: Mutex::new(false),
            menu: Mutex::new(None),
            starting_since: Mutex::new(None),
        }
    }
}

#[derive(Serialize)]
struct UiState {
    status: Status,
    status_label: String,
    repo_path: Option<String>,
    api_port: u16,
    front_port: u16,
    poll_secs: u64,
    node_path: Option<String>,
    npm_found: bool,
    python_found: bool,
    spend: Option<f64>,
    spend_label: String,
    autostart: bool,
    start_on_launch: bool,
    dashboard_url: String,
    owns_child: bool,
    front_ready: bool,
}

fn status_label(s: &Status, front_ready: bool) -> String {
    match s {
        Status::NeedsSetup(m) => format!("Setup needed: {m}"),
        Status::Stopped => "Stopped".to_string(),
        Status::Starting => "Starting…".to_string(),
        Status::Running if front_ready => "Running".to_string(),
        Status::Running => "Running — dashboard still building".to_string(),
        Status::Attached if front_ready => "Attached to a running server".to_string(),
        Status::Attached => "Attached — dashboard not responding".to_string(),
        Status::Error(m) => format!("Error: {m}"),
    }
}

// The frontend keys its stored token on window.location.hostname, so mixing
// "localhost" and "127.0.0.1" would create two separate token slots. Pin one.
fn dashboard_url(cfg: &TrayConfig) -> String {
    format!("http://127.0.0.1:{}", cfg.front_port)
}

fn snapshot(app: &AppHandle) -> UiState {
    let state = app.state::<AppState>();
    let cfg = state.cfg.lock().unwrap().clone();
    let status = state.sup.lock().unwrap().status.clone();
    let owns_child = state.sup.lock().unwrap().owns_child();
    let spend = *state.spend.lock().unwrap();
    let front_ready = *state.front_ready.lock().unwrap();

    UiState {
        status_label: status_label(&status, front_ready),
        status,
        repo_path: cfg.repo_path.as_ref().map(|p| p.display().to_string()),
        api_port: cfg.api_port,
        front_port: cfg.front_port,
        poll_secs: cfg.poll_secs,
        node_path: cfg.node_path.clone(),
        npm_found: cfg.npm_path.is_some(),
        python_found: cfg.python_path.is_some(),
        spend,
        spend_label: spend
            .map(poller::format_long)
            .unwrap_or_else(|| "Today: —".into()),
        autostart: app.autolaunch().is_enabled().unwrap_or(false),
        start_on_launch: cfg.start_on_launch,
        dashboard_url: dashboard_url(&cfg),
        owns_child,
        front_ready,
    }
}

fn refresh_tray(app: &AppHandle) {
    let state = app.state::<AppState>();
    let status = state.sup.lock().unwrap().status.clone();
    let spend = *state.spend.lock().unwrap();
    let owns = state.sup.lock().unwrap().owns_child();
    let front_ready = *state.front_ready.lock().unwrap();

    let spend_text = spend
        .map(poller::format_long)
        .unwrap_or_else(|| "Today: —".to_string());

    if let Some(menu) = state.menu.lock().unwrap().as_ref() {
        let _ = menu.spend.set_text(&spend_text);
        let _ = menu.status.set_text(status_label(&status, front_ready));
        let _ = menu.toggle.set_text(if owns {
            "Stop services"
        } else {
            "Start services"
        });
        // Never offer to stop a server we did not start — it belongs to
        // whoever launched it.
        let _ = menu
            .toggle
            .set_enabled(!matches!(status, Status::Attached | Status::NeedsSetup(_)));
    }

    if let Some(tray) = app.tray_by_id(TRAY_ID) {
        let short = spend.map(poller::format_short);
        // Title text is macOS-only (Windows: unsupported; Linux: unreliable and
        // needs an icon anyway). Every platform still gets the number from the
        // first menu item, which is why that item is the primary surface.
        #[cfg(target_os = "macos")]
        let _ = tray.set_title(short.clone());
        let tip = match (&status, &short) {
            (Status::Running | Status::Attached, Some(s)) => {
                format!("TokenTelemetry — {s} today (API-equivalent)")
            }
            _ => format!("TokenTelemetry — {}", status_label(&status, front_ready)),
        };
        // Tooltip is unsupported on Linux; harmless no-op there.
        let _ = tray.set_tooltip(Some(&tip));
    }
}

fn open_route(app: &AppHandle, route: &str) {
    let cfg = app.state::<AppState>().cfg.lock().unwrap().clone();
    let url = format!("{}{route}", dashboard_url(&cfg));
    if let Err(e) = app.opener().open_url(url, None::<&str>) {
        eprintln!("tray: could not open browser: {e}");
    }
}

fn show_prefs(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("prefs") {
        let _ = w.show();
        let _ = w.set_focus();
    }
}

fn start_services(app: &AppHandle) {
    let state = app.state::<AppState>();
    let cfg = state.cfg.lock().unwrap().clone();
    let mut sup = state.sup.lock().unwrap();
    match sup.start(&cfg) {
        Ok(()) => {
            *state.starting_since.lock().unwrap() = Some(Instant::now());
        }
        Err(e) => {
            sup.log(format!("start failed: {e}"));
            sup.status = Status::Error(e);
        }
    }
    drop(sup);
    refresh_tray(app);
}

fn stop_services(app: &AppHandle) {
    let state = app.state::<AppState>();
    state.sup.lock().unwrap().stop();
    *state.spend.lock().unwrap() = None;
    *state.starting_since.lock().unwrap() = None;
    refresh_tray(app);
}

// ---------------------------------------------------------------- commands

#[tauri::command]
fn ui_state(app: AppHandle) -> UiState {
    snapshot(&app)
}

#[tauri::command]
fn ui_logs(app: AppHandle) -> Vec<String> {
    app.state::<AppState>().sup.lock().unwrap().recent_logs()
}

#[tauri::command]
async fn pick_repo(app: AppHandle) -> Option<String> {
    let picked = app.dialog().file().blocking_pick_folder()?;
    let path = picked.into_path().ok()?;
    Some(path.display().to_string())
}

#[tauri::command]
fn save_settings(
    app: AppHandle,
    repo_path: Option<String>,
    api_port: u16,
    front_port: u16,
    poll_secs: u64,
    start_on_launch: bool,
) -> Result<UiState, String> {
    if api_port == front_port {
        return Err("the API and dashboard need different ports".into());
    }
    let repo = match repo_path
        .as_deref()
        .map(str::trim)
        .filter(|s| !s.is_empty())
    {
        Some(p) => {
            let path = std::path::PathBuf::from(p);
            TrayConfig::validate_repo(&path)?;
            Some(path)
        }
        None => None,
    };

    {
        let state = app.state::<AppState>();
        let mut cfg = state.cfg.lock().unwrap();
        cfg.repo_path = repo;
        cfg.api_port = api_port;
        cfg.front_port = front_port;
        cfg.poll_secs = poll_secs.clamp(10, 3600);
        cfg.start_on_launch = start_on_launch;
        cfg.save()?;

        let mut sup = state.sup.lock().unwrap();
        if cfg.repo_path.is_none() {
            sup.status = Status::NeedsSetup("no checkout selected".into());
        } else if matches!(sup.status, Status::NeedsSetup(_)) {
            sup.status = Status::Stopped;
        }
    }
    refresh_tray(&app);
    Ok(snapshot(&app))
}

#[tauri::command]
fn redetect(app: AppHandle) -> detect::Interpreters {
    let found = detect::detect();
    let state = app.state::<AppState>();
    let mut cfg = state.cfg.lock().unwrap();
    found.apply_to(&mut cfg);
    let _ = cfg.save();
    found
}

#[tauri::command]
fn set_autostart(app: AppHandle, enabled: bool) -> Result<bool, String> {
    let mgr = app.autolaunch();
    if enabled {
        mgr.enable().map_err(|e| e.to_string())?;
    } else {
        mgr.disable().map_err(|e| e.to_string())?;
    }
    mgr.is_enabled().map_err(|e| e.to_string())
}

#[tauri::command]
fn restart_services(app: AppHandle) {
    stop_services(&app);
    start_services(&app);
}

#[tauri::command]
fn open_dashboard(app: AppHandle) {
    open_route(&app, "/");
}

// ------------------------------------------------------------------- poll

async fn poll_once(app: AppHandle) {
    let cfg = app.state::<AppState>().cfg.lock().unwrap().clone();

    if cfg.repo_path.is_none() {
        return;
    }

    // Surface a child that died on its own rather than showing a stale
    // "Running" until someone opens the menu and wonders.
    {
        let state = app.state::<AppState>();
        let mut sup = state.sup.lock().unwrap();
        if let Some(msg) = sup.poll_child_exit() {
            sup.log(msg);
        }
    }

    let alive = poller::api_alive(cfg.api_port).await;
    {
        let state = app.state::<AppState>();
        let mut sup = state.sup.lock().unwrap();
        let started = *state.starting_since.lock().unwrap();
        sup.status = match (alive, sup.owns_child()) {
            (true, true) => Status::Running,
            // Something answered on the API port that we did not start. Attach
            // to it instead of spawning a second stack on top of it.
            (true, false) => Status::Attached,
            (false, true) => match started {
                Some(t) if t.elapsed() > supervisor::ready_timeout() => {
                    Status::Error("services did not come up in time".into())
                }
                _ => Status::Starting,
            },
            (false, false) => match &sup.status {
                Status::Error(e) => Status::Error(e.clone()),
                Status::NeedsSetup(m) => Status::NeedsSetup(m.clone()),
                _ => Status::Stopped,
            },
        };
        if matches!(sup.status, Status::Running | Status::Attached) {
            *state.starting_since.lock().unwrap() = None;
        }
    }

    if alive {
        let front = poller::frontend_alive(cfg.front_port).await;
        *app.state::<AppState>().front_ready.lock().unwrap() = front;
        match poller::today_spend(cfg.api_port).await {
            Ok(cost) => *app.state::<AppState>().spend.lock().unwrap() = Some(cost),
            Err(e) => {
                app.state::<AppState>().sup.lock().unwrap().log(e);
            }
        }
    } else {
        *app.state::<AppState>().spend.lock().unwrap() = None;
        *app.state::<AppState>().front_ready.lock().unwrap() = false;
    }

    refresh_tray(&app);
}

// ------------------------------------------------------------------- main

fn main() {
    let cfg = TrayConfig::load();

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_autostart::init(
            MacosLauncher::LaunchAgent,
            None,
        ))
        .manage(AppState::new(cfg))
        .invoke_handler(tauri::generate_handler![
            ui_state,
            ui_logs,
            pick_repo,
            save_settings,
            redetect,
            set_autostart,
            restart_services,
            open_dashboard,
        ])
        .setup(|app| {
            // No Dock icon and no app-switcher entry: this is a menu bar app.
            #[cfg(target_os = "macos")]
            app.set_activation_policy(tauri::ActivationPolicy::Accessory);

            let handle = app.handle().clone();
            let state = app.state::<AppState>();

            // Resolve interpreters once if we have never done it, or if the
            // recorded node path has since disappeared (a Homebrew upgrade, an
            // nvm version switch).
            {
                let mut cfg = state.cfg.lock().unwrap();
                let stale = cfg
                    .node_path
                    .as_ref()
                    .map(|p| !std::path::Path::new(p).is_file())
                    .unwrap_or(true);
                if stale {
                    detect::detect().apply_to(&mut cfg);
                    let _ = cfg.save();
                }
            }

            // Clean up after a previous tray process before touching the ports.
            state.sup.lock().unwrap().reap_stale();

            let spend_item = MenuItemBuilder::with_id("spend", "Today: —")
                .enabled(false)
                .build(app)?;
            let status_item = MenuItemBuilder::with_id("status", "Stopped")
                .enabled(false)
                .build(app)?;
            let toggle_item = MenuItemBuilder::with_id("toggle", "Start services").build(app)?;
            let dash = MenuItemBuilder::with_id("open_dash", "Open dashboard").build(app)?;
            let analytics = MenuItemBuilder::with_id("open_analytics", "Analytics").build(app)?;
            let local = MenuItemBuilder::with_id("open_local", "Local models").build(app)?;
            let settings =
                MenuItemBuilder::with_id("open_settings", "Dashboard settings").build(app)?;
            let prefs = MenuItemBuilder::with_id("prefs", "Preferences…").build(app)?;
            let quit = MenuItemBuilder::with_id("quit", "Quit TokenTelemetry").build(app)?;

            let menu = MenuBuilder::new(app)
                .items(&[
                    &spend_item,
                    &status_item,
                    &PredefinedMenuItem::separator(app)?,
                    &dash,
                    &analytics,
                    &local,
                    &settings,
                    &PredefinedMenuItem::separator(app)?,
                    &toggle_item,
                    &prefs,
                    &PredefinedMenuItem::separator(app)?,
                    &quit,
                ])
                .build()?;

            *state.menu.lock().unwrap() = Some(MenuHandles {
                spend: spend_item,
                status: status_item,
                toggle: toggle_item,
            });

            let icon = Image::from_bytes(include_bytes!("../icons/trayTemplate.png"))?;
            let tray_result = TrayIconBuilder::with_id(TRAY_ID)
                .icon(icon)
                .icon_as_template(true)
                .tooltip("TokenTelemetry")
                .menu(&menu)
                .on_menu_event(|app, event| {
                    let app = app.clone();
                    match event.id().as_ref() {
                        "open_dash" => open_route(&app, "/"),
                        "open_analytics" => open_route(&app, "/analytics"),
                        "open_local" => open_route(&app, "/local-models"),
                        "open_settings" => open_route(&app, "/settings"),
                        "prefs" => show_prefs(&app),
                        "toggle" => {
                            let owns = app.state::<AppState>().sup.lock().unwrap().owns_child();
                            if owns {
                                stop_services(&app);
                            } else {
                                start_services(&app);
                            }
                        }
                        "quit" => {
                            stop_services(&app);
                            app.exit(0);
                        }
                        _ => {}
                    }
                })
                .build(app);

            // A stock GNOME desktop has no tray at all without a user-installed
            // AppIndicator extension. Losing the icon is not a reason to stop
            // supervising the server or to refuse to open the dashboard.
            if let Err(e) = tray_result {
                eprintln!("tray: no system tray available ({e}); running without an icon");
                state
                    .sup
                    .lock()
                    .unwrap()
                    .log(format!("no system tray available: {e}"));
                show_prefs(&handle);
            }

            let needs_setup = {
                let cfg = state.cfg.lock().unwrap();
                match cfg.repo() {
                    None => Some("no checkout selected".to_string()),
                    Some(p) => TrayConfig::validate_repo(p).err(),
                }
            };
            if let Some(reason) = needs_setup {
                state.sup.lock().unwrap().status = Status::NeedsSetup(reason);
                show_prefs(&handle);
            } else {
                let (start_on_launch, api_port) = {
                    let cfg = state.cfg.lock().unwrap();
                    (cfg.start_on_launch, cfg.api_port)
                };
                if start_on_launch {
                    let h = handle.clone();
                    tauri::async_runtime::spawn(async move {
                        // Attach rather than spawn if the user already has a
                        // server up (a manual ./start.sh, or a survivor we could
                        // not reap). Starting a second one just fails on the port.
                        if poller::api_alive(api_port).await {
                            let st = h.state::<AppState>();
                            st.sup.lock().unwrap().status = Status::Attached;
                            st.sup
                                .lock()
                                .unwrap()
                                .log("attached to a server that was already running".to_string());
                            refresh_tray(&h);
                        } else {
                            start_services(&h);
                        }
                    });
                }
            }

            let h = handle.clone();
            tauri::async_runtime::spawn(async move {
                loop {
                    poll_once(h.clone()).await;
                    let secs = h
                        .state::<AppState>()
                        .cfg
                        .lock()
                        .unwrap()
                        .poll_secs
                        .clamp(10, 3600);
                    tokio::time::sleep(Duration::from_secs(secs)).await;
                }
            });

            refresh_tray(&handle);
            Ok(())
        })
        .on_window_event(|window, event| {
            // Closing Preferences must not quit a menu bar app.
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .build(tauri::generate_context!())
        .expect("failed to start TokenTelemetry tray")
        .run(|app, event| {
            // Safety net: a quit that did not come through the menu still has
            // to take the services with it.
            if let tauri::RunEvent::Exit = event {
                app.state::<AppState>().sup.lock().unwrap().stop();
            }
        });
}
