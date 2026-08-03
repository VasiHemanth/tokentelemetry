//! Finding `node`, `npm` and `python3` from a GUI process.
//!
//! This is the single most likely thing to break in this app. A launch-at-login
//! GUI process inherits a minimal PATH (`/usr/bin:/bin:/usr/sbin:/sbin` on
//! macOS) — not the user's shell PATH. Anything installed via nvm, fnm, Volta,
//! Homebrew, or pyenv is invisible. It works perfectly under `tauri dev` from a
//! terminal and fails on the first real login, which is why interpreters are
//! resolved to absolute paths once and persisted.

use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

/// Interactive shells can block on a prompt or a slow rc file. Never wait forever.
const PROBE_TIMEOUT: Duration = Duration::from_secs(6);

#[derive(Debug, Default, Clone, serde::Serialize)]
pub struct Interpreters {
    pub node: Option<String>,
    pub npm: Option<String>,
    pub python: Option<String>,
    /// Read from the same login shell, for the same reason: a value the user
    /// exported in their rc file is invisible to a process started at login.
    pub data_dir: Option<String>,
    pub home: Option<String>,
}

impl Interpreters {
    /// Directories to prepend to the child's PATH, de-duplicated.
    pub fn path_dirs(&self) -> Vec<String> {
        let mut dirs: Vec<String> = Vec::new();
        for exe in [&self.node, &self.npm, &self.python] {
            let Some(exe) = exe else { continue };
            let Some(parent) = PathBuf::from(exe).parent().map(PathBuf::from) else {
                continue;
            };
            let dir = parent.to_string_lossy().to_string();
            if !dirs.contains(&dir) {
                dirs.push(dir);
            }
        }
        dirs
    }

    pub fn apply_to(&self, cfg: &mut crate::config::TrayConfig) {
        cfg.node_path = self.node.clone();
        cfg.npm_path = self.npm.clone();
        cfg.python_path = self.python.clone();
        cfg.extra_path_dirs = self.path_dirs();
        // Only overwrite when the shell actually told us something, so a value
        // typed into Preferences is not wiped by a later re-detect.
        if self.data_dir.is_some() {
            cfg.data_dir_override = self.data_dir.clone();
        }
        if self.home.is_some() {
            cfg.home_override = self.home.clone();
        }
    }
}

pub fn detect() -> Interpreters {
    Interpreters {
        node: which("node"),
        npm: which("npm"),
        python: which("python3").or_else(|| which("python")),
        data_dir: login_env("TOKENTELEMETRY_DATA_DIR"),
        home: login_env("TOKENTELEMETRY_HOME"),
    }
}

/// Read one environment variable as the user's login shell sees it.
#[cfg(unix)]
fn login_env(name: &str) -> Option<String> {
    if let Ok(v) = std::env::var(name) {
        if !v.trim().is_empty() {
            return Some(v);
        }
    }
    let shell = std::env::var("SHELL").unwrap_or_else(|_| "/bin/sh".to_string());
    let script = format!("printenv {name}");
    for args in [vec!["-lic", script.as_str()], vec!["-lc", script.as_str()]] {
        if let Some(out) = run_capture(&shell, &args) {
            let value = out.lines().map(str::trim).find(|l| !l.is_empty());
            if let Some(v) = value {
                return Some(v.to_string());
            }
        }
    }
    None
}

#[cfg(windows)]
fn login_env(name: &str) -> Option<String> {
    // Windows does not strip the environment for login-started apps.
    std::env::var(name).ok().filter(|v| !v.trim().is_empty())
}

/// Resolve a command the way the user's terminal would.
///
/// Order matters: a login+interactive shell first (nvm and friends are almost
/// always set up in `.zshrc`/`.bashrc`, which only an interactive shell reads),
/// then login-only, then a plain lookup for the case where we already inherited
/// a usable PATH.
#[cfg(unix)]
fn which(cmd: &str) -> Option<String> {
    let shell = std::env::var("SHELL").unwrap_or_else(|_| "/bin/sh".to_string());
    let script = format!("command -v {cmd} 2>/dev/null");

    for args in [
        vec!["-lic", script.as_str()],
        vec!["-lc", script.as_str()],
        vec!["-c", script.as_str()],
    ] {
        if let Some(found) = first_existing_line(run_capture(&shell, &args)) {
            return Some(found);
        }
    }
    // $SHELL is not necessarily POSIX. csh/tcsh reject `-lic` outright and have
    // no `command -v`, so every attempt above returns nothing for those users.
    // /bin/sh always understands this.
    if let Some(found) = first_existing_line(run_capture("/bin/sh", &["-lc", script.as_str()])) {
        return Some(found);
    }
    for probe in ["/usr/bin/which", "/bin/which"] {
        if let Some(found) = first_existing_line(run_capture(probe, &[cmd])) {
            return Some(found);
        }
    }
    None
}

#[cfg(windows)]
fn which(cmd: &str) -> Option<String> {
    // `where` already searches the user's PATH as the session sees it; Windows
    // does not strip PATH for login-started apps the way macOS does.
    first_existing_line(run_capture("where", &[cmd]))
}

/// Takes the first line that names a file that actually exists. `which` can
/// print shell-function noise, and `where` prints every match.
fn first_existing_line(out: Option<String>) -> Option<String> {
    out?.lines()
        .map(str::trim)
        .find(|l| !l.is_empty() && PathBuf::from(l).is_file())
        .map(str::to_string)
}

fn run_capture(program: &str, args: &[&str]) -> Option<String> {
    let mut cmd = Command::new(program);
    cmd.args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    // No console flash: the release build has no console to inherit.
    crate::supervisor::no_window(&mut cmd);
    let mut child = cmd.spawn().ok()?;

    let deadline = Instant::now() + PROBE_TIMEOUT;
    loop {
        match child.try_wait() {
            Ok(Some(_)) => break,
            Ok(None) => {
                if Instant::now() >= deadline {
                    let _ = child.kill();
                    let _ = child.wait();
                    return None;
                }
                std::thread::sleep(Duration::from_millis(50));
            }
            Err(_) => return None,
        }
    }
    let out = child.wait_with_output().ok()?;
    Some(String::from_utf8_lossy(&out.stdout).to_string())
}
