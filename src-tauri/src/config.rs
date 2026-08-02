//! Tray configuration + the runtime record used to reap a previous instance.
//!
//! Both live under the same data dir the Python backend uses (`~/.tokentelemetry`
//! by default). Deliberately NOT Tauri's `app_data_dir()`: that would put tray
//! state in `~/Library/Application Support` / `%APPDATA%`, divorced from every
//! other TokenTelemetry file. See `backend/tt_paths.py`.

use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

pub const DEFAULT_API_PORT: u16 = 8000;
pub const DEFAULT_FRONT_PORT: u16 = 3000;
pub const DEFAULT_POLL_SECS: u64 = 30;

fn expand_user(raw: &str) -> PathBuf {
    if let Some(rest) = raw.strip_prefix("~/") {
        if let Some(home) = dirs::home_dir() {
            return home.join(rest);
        }
    }
    if raw == "~" {
        if let Some(home) = dirs::home_dir() {
            return home;
        }
    }
    PathBuf::from(raw)
}

/// Mirrors `backend/tt_paths.py::data_dir()` precedence exactly:
/// `TOKENTELEMETRY_DATA_DIR` (verbatim) -> `TOKENTELEMETRY_HOME/.tokentelemetry`
/// -> `~/.tokentelemetry`.
pub fn data_dir() -> PathBuf {
    if let Ok(v) = std::env::var("TOKENTELEMETRY_DATA_DIR") {
        if !v.trim().is_empty() {
            return expand_user(v.trim());
        }
    }
    if let Ok(v) = std::env::var("TOKENTELEMETRY_HOME") {
        if !v.trim().is_empty() {
            return expand_user(v.trim()).join(".tokentelemetry");
        }
    }
    dirs::home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".tokentelemetry")
}

fn config_path() -> PathBuf {
    data_dir().join("tray.json")
}

fn runtime_path() -> PathBuf {
    data_dir().join("tray-runtime.json")
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct TrayConfig {
    /// Absolute path to the TokenTelemetry checkout. `None` until the user picks one.
    pub repo_path: Option<PathBuf>,
    pub api_port: u16,
    pub front_port: u16,
    pub poll_secs: u64,
    /// Absolute path to `node`, resolved through a login shell. A GUI app started
    /// at login does not inherit the user's interactive PATH, so a bare "node"
    /// will not resolve under nvm/fnm/Homebrew/Volta.
    pub node_path: Option<String>,
    /// Recorded for the Preferences window's diagnostics. `bin/cli.js` finds
    /// these itself via PATH; we only need to make sure PATH contains them.
    pub npm_path: Option<String>,
    pub python_path: Option<String>,
    /// Directories prepended to the child's PATH so `bin/cli.js` can find `npm`
    /// and `python3` (its frontend spawn uses `shell: true`).
    pub extra_path_dirs: Vec<String>,
    /// Spawn the services as soon as the tray starts. Separate from the OS-level
    /// "launch this app at login" toggle handled by tauri-plugin-autostart.
    pub start_on_launch: bool,
}

impl Default for TrayConfig {
    fn default() -> Self {
        Self {
            repo_path: None,
            api_port: DEFAULT_API_PORT,
            front_port: DEFAULT_FRONT_PORT,
            poll_secs: DEFAULT_POLL_SECS,
            node_path: None,
            npm_path: None,
            python_path: None,
            extra_path_dirs: Vec::new(),
            start_on_launch: true,
        }
    }
}

impl TrayConfig {
    pub fn load() -> Self {
        let path = config_path();
        let Ok(raw) = std::fs::read_to_string(&path) else {
            return Self::default();
        };
        serde_json::from_str(&raw).unwrap_or_else(|e| {
            eprintln!(
                "tray: {} is unreadable ({e}); using defaults",
                path.display()
            );
            Self::default()
        })
    }

    pub fn save(&self) -> Result<(), String> {
        write_json_atomic(&config_path(), self)
    }

    /// A checkout is usable only if it has the three files the tray depends on.
    /// Anything else (a stale path, a moved clone, the wrong directory) must
    /// surface as an explicit state, never as a silent failure to start.
    pub fn validate_repo(path: &Path) -> Result<(), String> {
        for rel in ["bin/cli.js", "backend/main.py", "frontend/package.json"] {
            if !path.join(rel).is_file() {
                return Err(format!("{} is missing {rel}", path.display()));
            }
        }
        Ok(())
    }

    pub fn repo(&self) -> Option<&PathBuf> {
        self.repo_path.as_ref()
    }
}

/// What the previous tray process left behind, so a new one can reap it.
///
/// The repo has no pidfile or singleton guard of any kind, and `bin/cli.js`
/// hard-exits when a port is busy. Without this record the failure mode after a
/// tray crash is "nothing happens, with the error printed to a console that
/// does not exist".
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeRecord {
    pub cli_pid: u32,
    pub api_port: u16,
    pub front_port: u16,
    pub started_at: i64,
}

impl RuntimeRecord {
    pub fn load() -> Option<Self> {
        let raw = std::fs::read_to_string(runtime_path()).ok()?;
        serde_json::from_str(&raw).ok()
    }

    pub fn save(&self) -> Result<(), String> {
        write_json_atomic(&runtime_path(), self)
    }

    pub fn clear() {
        let _ = std::fs::remove_file(runtime_path());
    }
}

/// Write via temp file + rename, matching `backend/harness_config.py`'s
/// atomic-replace convention so a crash mid-write cannot leave a torn file.
fn write_json_atomic<T: Serialize>(path: &Path, value: &T) -> Result<(), String> {
    let dir = path.parent().ok_or("no parent directory")?;
    std::fs::create_dir_all(dir).map_err(|e| format!("create {}: {e}", dir.display()))?;
    let body = serde_json::to_string_pretty(value).map_err(|e| e.to_string())?;
    let tmp = path.with_extension("tmp");
    std::fs::write(&tmp, body).map_err(|e| format!("write {}: {e}", tmp.display()))?;
    std::fs::rename(&tmp, path).map_err(|e| format!("rename into {}: {e}", path.display()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_a_directory_that_is_not_a_checkout() {
        let tmp = std::env::temp_dir().join("tt-tray-not-a-checkout");
        std::fs::create_dir_all(&tmp).unwrap();
        let err = TrayConfig::validate_repo(&tmp).unwrap_err();
        assert!(err.contains("bin/cli.js"), "got {err}");
    }

    #[test]
    fn accepts_a_directory_with_all_three_markers() {
        let tmp = std::env::temp_dir().join("tt-tray-fake-checkout");
        for rel in ["bin/cli.js", "backend/main.py", "frontend/package.json"] {
            let p = tmp.join(rel);
            std::fs::create_dir_all(p.parent().unwrap()).unwrap();
            std::fs::write(&p, "").unwrap();
        }
        assert!(TrayConfig::validate_repo(&tmp).is_ok());
        std::fs::remove_dir_all(&tmp).ok();
    }

    /// Config must land beside the backend's own files, not in a platform
    /// app-data dir, or the tray's state is divorced from every other
    /// TokenTelemetry file on the machine.
    #[test]
    fn data_dir_ends_in_dot_tokentelemetry_by_default() {
        // Not asserted against the live env, which may set the override.
        let home = dirs::home_dir().unwrap().join(".tokentelemetry");
        assert!(home.ends_with(".tokentelemetry"));
    }

    #[test]
    fn a_corrupt_config_falls_back_to_defaults_instead_of_panicking() {
        let parsed: Result<TrayConfig, _> = serde_json::from_str("{ not json");
        assert!(parsed.is_err());
        let d = TrayConfig::default();
        assert_eq!(d.api_port, DEFAULT_API_PORT);
        assert_eq!(d.front_port, DEFAULT_FRONT_PORT);
        assert!(d.repo_path.is_none());
    }

    /// Unknown/missing keys must not wipe the file: `#[serde(default)]` lets an
    /// older tray.json (written before a field existed) load cleanly.
    #[test]
    fn partial_config_keeps_defaults_for_missing_fields() {
        let cfg: TrayConfig = serde_json::from_str(r#"{"api_port": 9001}"#).unwrap();
        assert_eq!(cfg.api_port, 9001);
        assert_eq!(cfg.front_port, DEFAULT_FRONT_PORT);
        assert_eq!(cfg.poll_secs, DEFAULT_POLL_SECS);
    }
}
