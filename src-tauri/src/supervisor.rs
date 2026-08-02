//! Spawns and supervises one child: `node <repo>/bin/cli.js`.
//!
//! Deliberately NOT a reimplementation of `ensureBackend`/`ensureFrontend`.
//! `bin/cli.js` already owns venv creation, the SHA-stamped
//! `pip install --require-hashes -r requirements.lock`, `npm ci`, the port
//! pre-flight, and the two real spawns. Duplicating that logic in Rust would
//! give us a second source of truth that drifts. We run it and watch it.

use crate::config::{RuntimeRecord, TrayConfig};
use std::collections::VecDeque;
use std::io::{BufRead, BufReader};
use std::net::{SocketAddr, TcpStream};
use std::path::Path;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

pub const LOG_CAPACITY: usize = 200;

/// How long the frontend gets to answer before we call the start failed.
///
/// `bin/cli.js` budgets 45s, but that number never accounted for `next dev`'s
/// first-route compile on a cold `.next` — only for dependency installs. A cold
/// first run does both, so the tray is more patient than the CLI.
const READY_TIMEOUT: Duration = Duration::from_secs(180);

#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
#[serde(tag = "kind", content = "detail")]
pub enum Status {
    /// No checkout configured yet.
    NeedsSetup(String),
    Stopped,
    Starting,
    /// We own the child process.
    Running,
    /// A TokenTelemetry server was already listening, so we attached to it
    /// instead of starting a second one. Quit will not kill it.
    Attached,
    Error(String),
}

pub struct Supervisor {
    child: Option<Child>,
    pub status: Status,
    pub logs: Arc<Mutex<VecDeque<String>>>,
}

impl Supervisor {
    pub fn new() -> Self {
        Self {
            child: None,
            status: Status::Stopped,
            logs: Arc::new(Mutex::new(VecDeque::with_capacity(LOG_CAPACITY))),
        }
    }

    pub fn owns_child(&self) -> bool {
        self.child.is_some()
    }

    pub fn log(&self, line: impl Into<String>) {
        push_log(&self.logs, line.into());
    }

    pub fn recent_logs(&self) -> Vec<String> {
        self.logs
            .lock()
            .map(|l| l.iter().cloned().collect())
            .unwrap_or_default()
    }

    /// Reap a child left behind by a previous tray process (a crash, a force
    /// quit, a logout that killed us but not our detached child).
    ///
    /// Without this, the next launch finds the ports busy, `bin/cli.js` calls
    /// `process.exit(1)`, and the user sees nothing at all happen.
    pub fn reap_stale(&mut self) {
        let Some(rec) = RuntimeRecord::load() else {
            return;
        };
        if pid_alive(rec.cli_pid) {
            self.log(format!(
                "reaping supervisor pid {} left by a previous run",
                rec.cli_pid
            ));
            terminate(rec.cli_pid);
            // cli.js's SIGTERM handler tears down both children, but it calls
            // process.exit() straight after signalling them with no grace
            // period, so wait on the ports rather than on the pid.
            wait_ports_free(&[rec.api_port, rec.front_port], Duration::from_secs(8));
        }
        RuntimeRecord::clear();
    }

    pub fn start(&mut self, cfg: &TrayConfig) -> Result<(), String> {
        if self.child.is_some() {
            return Ok(());
        }
        let repo = cfg
            .repo()
            .ok_or_else(|| "no TokenTelemetry checkout configured".to_string())?;
        TrayConfig::validate_repo(repo)?;

        let node = cfg
            .node_path
            .clone()
            .ok_or_else(|| "node was not found — open Preferences and re-detect".to_string())?;
        if !Path::new(&node).is_file() {
            return Err(format!("node is missing at {node}"));
        }

        // Check the ports BEFORE spawning. cli.js checks them only after its
        // (possibly 15s) dependency installs, then hard-exits — so without this
        // a busy port costs the user the whole install wait for nothing.
        let busy: Vec<u16> = [cfg.api_port, cfg.front_port]
            .into_iter()
            .filter(|p| !port_free(*p))
            .collect();
        if !busy.is_empty() {
            return Err(format!(
                "port(s) already in use: {}",
                busy.iter()
                    .map(u16::to_string)
                    .collect::<Vec<_>>()
                    .join(", ")
            ));
        }

        let mut cmd = Command::new(&node);
        cmd.arg(repo.join("bin").join("cli.js"))
            .arg("--port")
            .arg(cfg.front_port.to_string())
            .arg("--api-port")
            .arg(cfg.api_port.to_string())
            .arg("--host")
            .arg("127.0.0.1")
            .current_dir(repo)
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            // cli.js opens the dashboard itself once Next answers. The tray owns
            // that decision instead — an auto-opened browser tab at every login
            // is not what "starts quietly in the background" means.
            .env("AGENT_HARNESS_NO_OPEN", "1");

        if let Some(path) = augmented_path(cfg) {
            cmd.env("PATH", path);
        }

        configure_process_group(&mut cmd);

        let mut child = cmd
            .spawn()
            .map_err(|e| format!("could not start node: {e}"))?;

        // A Tauri app has no inherited console, so cli.js's stdio has nowhere to
        // go. Pipe both streams into a ring buffer the Preferences window shows.
        for (stream, tag) in [
            (child.stdout.take().map(BufReaderKind::Out), "out"),
            (child.stderr.take().map(BufReaderKind::Err), "err"),
        ] {
            if let Some(stream) = stream {
                let logs = Arc::clone(&self.logs);
                let tag = tag.to_string();
                std::thread::spawn(move || {
                    let reader: Box<dyn BufRead + Send> = match stream {
                        BufReaderKind::Out(s) => Box::new(BufReader::new(s)),
                        BufReaderKind::Err(s) => Box::new(BufReader::new(s)),
                    };
                    for line in reader.lines().map_while(Result::ok) {
                        push_log(&logs, format!("[{tag}] {line}"));
                    }
                });
            }
        }

        let rec = RuntimeRecord {
            cli_pid: child.id(),
            api_port: cfg.api_port,
            front_port: cfg.front_port,
            started_at: chrono::Local::now().timestamp(),
        };
        if let Err(e) = rec.save() {
            self.log(format!("could not record runtime state: {e}"));
        }

        self.log(format!("started supervisor pid {}", child.id()));
        self.child = Some(child);
        self.status = Status::Starting;
        Ok(())
    }

    /// Stop only what we started. An attached server belongs to whoever launched
    /// it (usually the user's own `./start.sh`) and must survive our quit.
    pub fn stop(&mut self) {
        let Some(mut child) = self.child.take() else {
            self.status = Status::Stopped;
            return;
        };
        let pid = child.id();
        let ports = RuntimeRecord::load()
            .map(|r| [r.api_port, r.front_port])
            .unwrap_or([0, 0]);

        self.log(format!("stopping supervisor pid {pid}"));
        // Signal cli.js's own pid, not its process group: it spawns both
        // children detached into *their own* groups, and its SIGTERM handler is
        // the only thing that knows how to reap them.
        terminate(pid);

        let live: Vec<u16> = ports.into_iter().filter(|p| *p != 0).collect();
        if !live.is_empty() && !wait_ports_free(&live, Duration::from_secs(8)) {
            // cli.js exits immediately after signalling, with no SIGKILL
            // escalation, so anything ignoring SIGTERM is orphaned right here.
            self.log("services did not exit in time; escalating".to_string());
            kill_hard(pid);
        }
        let _ = child.wait();
        RuntimeRecord::clear();
        self.status = Status::Stopped;
    }

    /// Notice a child that died on its own so the menu can say so, rather than
    /// showing a stale "Running" forever.
    pub fn poll_child_exit(&mut self) -> Option<String> {
        let child = self.child.as_mut()?;
        match child.try_wait() {
            Ok(Some(code)) => {
                let msg = format!("services exited ({code})");
                self.child = None;
                RuntimeRecord::clear();
                self.status = Status::Error(msg.clone());
                Some(msg)
            }
            _ => None,
        }
    }
}

enum BufReaderKind {
    Out(std::process::ChildStdout),
    Err(std::process::ChildStderr),
}

fn push_log(logs: &Arc<Mutex<VecDeque<String>>>, line: String) {
    if let Ok(mut l) = logs.lock() {
        if l.len() >= LOG_CAPACITY {
            l.pop_front();
        }
        l.push_back(line);
    }
}

/// Prepend the resolved interpreter directories to PATH.
///
/// `bin/cli.js` shells out to `npm` (its frontend spawn uses `shell: true`) and
/// to `python3` when the venv is missing. At login neither is on PATH.
fn augmented_path(cfg: &TrayConfig) -> Option<String> {
    if cfg.extra_path_dirs.is_empty() {
        return None;
    }
    let sep = if cfg!(windows) { ";" } else { ":" };
    let current = std::env::var("PATH").unwrap_or_default();
    let mut parts = cfg.extra_path_dirs.clone();
    if !current.is_empty() {
        parts.push(current);
    }
    Some(parts.join(sep))
}

#[cfg(unix)]
fn configure_process_group(cmd: &mut Command) {
    use std::os::unix::process::CommandExt;
    unsafe {
        cmd.pre_exec(|| {
            // Own session: the child outlives a tray crash so it can be reaped
            // deliberately on the next launch rather than dying mid-write.
            libc::setsid();
            // Linux can additionally guarantee teardown if the tray is SIGKILLed.
            // macOS has no equivalent, which is why reap_stale() exists.
            #[cfg(target_os = "linux")]
            libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGTERM);
            Ok(())
        });
    }
}

#[cfg(windows)]
fn configure_process_group(cmd: &mut Command) {
    use std::os::windows::process::CommandExt;
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    // Without this the user gets a stray console window every login.
    cmd.creation_flags(CREATE_NO_WINDOW);
}

#[cfg(unix)]
pub fn pid_alive(pid: u32) -> bool {
    // Signal 0 performs the permission + existence check without delivering.
    unsafe { libc::kill(pid as i32, 0) == 0 }
}

#[cfg(windows)]
pub fn pid_alive(pid: u32) -> bool {
    Command::new("tasklist")
        .args(["/FI", &format!("PID eq {pid}"), "/NH"])
        .output()
        .map(|o| String::from_utf8_lossy(&o.stdout).contains(&pid.to_string()))
        .unwrap_or(false)
}

#[cfg(unix)]
fn terminate(pid: u32) {
    unsafe {
        libc::kill(pid as i32, libc::SIGTERM);
    }
}

#[cfg(windows)]
fn terminate(pid: u32) {
    // Windows has no SIGTERM. /T walks the tree, matching what cli.js's own
    // shutdown() does on this platform.
    let _ = Command::new("taskkill")
        .args(["/PID", &pid.to_string(), "/T"])
        .output();
}

#[cfg(unix)]
fn kill_hard(pid: u32) {
    unsafe {
        libc::kill(pid as i32, libc::SIGKILL);
    }
}

#[cfg(windows)]
fn kill_hard(pid: u32) {
    let _ = Command::new("taskkill")
        .args(["/PID", &pid.to_string(), "/T", "/F"])
        .output();
}

/// True when nothing is listening. Probes both loopback stacks because a
/// v4-only bind probe misses cross-stack conflicts on macOS — the same reason
/// `bin/cli.js` uses a connect probe rather than a bind probe.
pub fn port_free(port: u16) -> bool {
    for host in ["127.0.0.1", "::1"] {
        let Ok(addr) = format!("{host}:{port}").parse::<SocketAddr>() else {
            continue;
        };
        if TcpStream::connect_timeout(&addr, Duration::from_millis(300)).is_ok() {
            return false;
        }
    }
    true
}

fn wait_ports_free(ports: &[u16], budget: Duration) -> bool {
    let deadline = Instant::now() + budget;
    while Instant::now() < deadline {
        if ports.iter().all(|p| port_free(*p)) {
            return true;
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    ports.iter().all(|p| port_free(*p))
}

pub fn ready_timeout() -> Duration {
    READY_TIMEOUT
}
