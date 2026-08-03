// Keep a login-launched build from flashing a console window on Windows.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod config;
mod detect;
mod panel;
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
    /// Today's cost together with the local date it was measured for.
    ///
    /// The date is not decoration. Without it the last figure of the day
    /// survives midnight and keeps being shown as "Today" until the next
    /// successful poll — and if the backend is down or erroring at that moment,
    /// yesterday's total can sit there labelled as today's indefinitely.
    spend: Mutex<Option<(String, f64)>>,
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

/// The cached figure, but only if it is still for today's local date.
///
/// Reading through this everywhere is what stops a stale total being relabelled
/// "Today" after midnight.
fn spend_for_today(state: &AppState) -> Option<f64> {
    let today = poller::local_today();
    state
        .spend
        .lock()
        .unwrap()
        .as_ref()
        .filter(|(day, _)| *day == today)
        .map(|(_, cost)| *cost)
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
    let spend = spend_for_today(&state);
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
    let spend = spend_for_today(&state);
    let owns = state.sup.lock().unwrap().owns_child();
    let front_ready = *state.front_ready.lock().unwrap();

    let spend_text = spend
        .map(poller::format_long)
        .unwrap_or_else(|| "Today: —".to_string());

    // Clone the handles out and DROP the guard before touching them.
    //
    // set_text/set_enabled dispatch to the main thread and block on a reply.
    // Holding the mutex across that call deadlocks the moment the main thread
    // is itself inside refresh_tray (a menu click) waiting for this same lock:
    // the poll thread waits on the event loop, the event loop waits on the
    // mutex, and neither times out. MenuItem is an Arc newtype, so cloning is
    // cheap and the handles stay valid.
    let handles = state
        .menu
        .lock()
        .unwrap()
        .as_ref()
        .map(|m| (m.spend.clone(), m.status.clone(), m.toggle.clone()));

    if let Some((spend_item, status_item, toggle_item)) = handles {
        let _ = spend_item.set_text(&spend_text);
        let _ = status_item.set_text(status_label(&status, front_ready));
        let _ = toggle_item.set_text(if owns {
            "Stop services"
        } else {
            "Start services"
        });
        // Never offer to stop a server we did not start — it belongs to
        // whoever launched it.
        let _ =
            toggle_item.set_enabled(!matches!(status, Status::Attached | Status::NeedsSetup(_)));
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

    // Clearing the checkout while we own a running child would strand it:
    // start/stop both need the path, so the services would keep running with no
    // way to reach them from the tray.
    if repo.is_none() && app.state::<AppState>().sup.lock().unwrap().owns_child() {
        return Err("stop the services before clearing the checkout folder".into());
    }

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
fn restart_services(app: AppHandle) -> Result<(), String> {
    // Restarting an attached server would stop nothing and then fail the port
    // pre-check, so say why instead of showing a confusing "port in use".
    if matches!(
        app.state::<AppState>().sup.lock().unwrap().status,
        Status::Attached
    ) {
        return Err("this server was started outside the app; stop it where you started it".into());
    }
    stop_services(&app);
    start_services(&app);
    Ok(())
}

/// Everything the dropdown panel renders.
///
/// Two `/analytics` calls, issued only when the panel is actually opened, so
/// the 30s background poll stays exactly as cheap as it was.
#[tauri::command]
async fn panel_data(app: AppHandle) -> Result<panel::PanelData, String> {
    let (api_port, status) = {
        let state = app.state::<AppState>();
        let cfg = state.cfg.lock().unwrap();
        let sup = state.sup.lock().unwrap();
        (cfg.api_port, sup.status.clone())
    };
    if !matches!(status, Status::Running | Status::Attached) {
        return Err(format!(
            "no server to read from ({})",
            status_label(&status, false)
        ));
    }

    let today_local = chrono::Local::now().date_naive();
    let today = today_local.format("%Y-%m-%d").to_string();
    let from = panel::window_start(today_local);

    let today_json = poller::analytics_window(api_port, &today, &today).await?;
    let week_json = poller::analytics_window(api_port, &from, &today).await?;
    Ok(panel::build(&today_json, &week_json, &today))
}

/// Show the panel anchored under the tray icon.
///
/// `rect` is where the OS actually drew the icon, which is the only reliable
/// anchor: the menu bar reflows as other apps come and go.
fn toggle_panel(app: &AppHandle, anchor: Option<(f64, f64, f64)>) {
    let Some(win) = app.get_webview_window("panel") else {
        return;
    };
    if win.is_visible().unwrap_or(false) {
        let _ = win.hide();
        return;
    }
    if let Some((x, y, w)) = anchor {
        if let Ok(size) = win.outer_size() {
            let scale = win.scale_factor().unwrap_or(1.0);
            let width = size.width as f64 / scale;
            // Centre under the icon, then nudge back on-screen if the icon sits
            // near the right edge of the display.
            let left = x + w / 2.0 - width / 2.0;
            let _ = win.set_position(tauri::LogicalPosition::new(left.max(8.0), y + 6.0));
        }
    }
    let _ = win.show();
    let _ = win.set_focus();
}

/// Quit from the Preferences window.
///
/// Without this there is no way out on a desktop with no system tray — stock
/// GNOME without an AppIndicator extension shows no icon at all, and closing
/// the window only hides it.
#[tauri::command]
fn quit_app(app: AppHandle) {
    stop_services(&app);
    app.exit(0);
}

#[tauri::command]
fn open_dashboard(app: AppHandle) {
    open_route(&app, "/");
}

/// Open a dashboard route from the panel.
///
/// The route is matched against a fixed allow-list rather than interpolated, so
/// nothing the webview sends can steer the browser somewhere unintended.
#[tauri::command]
fn open_route_cmd(app: AppHandle, route: String) {
    const ALLOWED: [&str; 5] = ["/", "/analytics", "/local-models", "/settings", "/projects"];
    if let Some(r) = ALLOWED.iter().find(|r| **r == route) {
        open_route(&app, r);
    }
    if let Some(w) = app.get_webview_window("panel") {
        let _ = w.hide();
    }
}

#[tauri::command]
fn show_prefs_cmd(app: AppHandle) {
    if let Some(w) = app.get_webview_window("panel") {
        let _ = w.hide();
    }
    show_prefs(&app);
}

#[tauri::command]
fn hide_panel(app: AppHandle) {
    if let Some(w) = app.get_webview_window("panel") {
        let _ = w.hide();
    }
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
            Ok((day, cost)) => *app.state::<AppState>().spend.lock().unwrap() = Some((day, cost)),
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
        // Must be registered first. Two tray processes would fight over the
        // ports, and the second one's reap_stale() would tear down the first
        // one's perfectly healthy services.
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            show_prefs(app);
        }))
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
            quit_app,
            panel_data,
            open_route_cmd,
            show_prefs_cmd,
            hide_panel,
        ])
        .setup(|app| {
            // No Dock icon and no app-switcher entry: this is a menu bar app.
            #[cfg(target_os = "macos")]
            app.set_activation_policy(tauri::ActivationPolicy::Accessory);

            let handle = app.handle().clone();
            let state = app.state::<AppState>();

            // Does the recorded node path still exist? A Homebrew upgrade or an
            // nvm version switch invalidates it.
            let needs_detect = {
                let cfg = state.cfg.lock().unwrap();
                cfg.node_path
                    .as_ref()
                    .map(|p| !std::path::Path::new(p).is_file())
                    .unwrap_or(true)
            };

            // Clean up after a previous tray process before touching the ports.
            state.sup.lock().unwrap().reap_stale();

            // Re-point the login item at wherever this binary now lives.
            //
            // All three platforms record an ABSOLUTE path when autostart is
            // enabled. Drag the .app from the build folder to /Applications and
            // the recorded path is dangling — but is_enabled() still reports
            // true, so Preferences would claim "launch at login: on" while
            // login silently does nothing. Re-assert on every start.
            {
                let al = handle.autolaunch();
                if al.is_enabled().unwrap_or(false) {
                    let _ = al.disable();
                    if let Err(e) = al.enable() {
                        state
                            .sup
                            .lock()
                            .unwrap()
                            .log(format!("could not refresh launch-at-login: {e}"));
                    }
                }
            }

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

            // macOS template images are pure black plus alpha and get inverted
            // by the system to suit the menu bar. Windows and Linux ignore the
            // template flag entirely, so shipping the same asset there would
            // put a black glyph on a dark taskbar — invisible. Use the full
            // colour icon off macOS.
            #[cfg(target_os = "macos")]
            let icon = Image::from_bytes(include_bytes!("../icons/trayTemplate.png"))?;
            #[cfg(not(target_os = "macos"))]
            let icon = Image::from_bytes(include_bytes!("../icons/32x32.png"))?;

            let tray_result = TrayIconBuilder::with_id(TRAY_ID)
                .icon(icon)
                .icon_as_template(cfg!(target_os = "macos"))
                .tooltip("TokenTelemetry")
                .menu(&menu)
                // Left click opens the panel; the menu moves to right click.
                // Without this the menu swallows the click and the panel can
                // never be reached.
                .show_menu_on_left_click(false)
                .on_tray_icon_event(|tray, event| {
                    if let tauri::tray::TrayIconEvent::Click {
                        button: tauri::tray::MouseButton::Left,
                        button_state: tauri::tray::MouseButtonState::Up,
                        rect,
                        ..
                    } = event
                    {
                        let pos = rect.position.to_logical::<f64>(1.0);
                        let size = rect.size.to_logical::<f64>(1.0);
                        toggle_panel(
                            tray.app_handle(),
                            Some((pos.x, pos.y + size.height, size.width)),
                        );
                    }
                })
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
            if let Some(reason) = &needs_setup {
                state.sup.lock().unwrap().status = Status::NeedsSetup(reason.clone());
                show_prefs(&handle);
            }

            let should_start = needs_setup.is_none() && state.cfg.lock().unwrap().start_on_launch;
            let api_port = state.cfg.lock().unwrap().api_port;

            // Everything slow happens here, off the startup path, so the tray
            // icon appears immediately at login.
            let h = handle.clone();
            tauri::async_runtime::spawn(async move {
                // Probing interpreters runs the user's login shell, up to four
                // times per command with a 6s ceiling each. Blocking setup() on
                // that would leave the menu bar empty for seconds. It runs even
                // when setup is incomplete, so the paths are ready by the time
                // the user picks a folder and hits Start.
                if needs_detect {
                    if let Ok(found) = tauri::async_runtime::spawn_blocking(detect::detect).await {
                        let st = h.state::<AppState>();
                        let mut cfg = st.cfg.lock().unwrap();
                        found.apply_to(&mut cfg);
                        let _ = cfg.save();
                    }
                }
                if !should_start {
                    return;
                }
                // Attach rather than spawn if the user already has a server up
                // (a manual ./start.sh, or a survivor we could not reap).
                // Starting a second one just fails on the port.
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
