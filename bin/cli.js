#!/usr/bin/env node
/**
 * Agent Observability Harness — single cross-platform entry point.
 *
 * One command bootstraps both services on macOS, Linux, and Windows:
 *   - creates the Python venv if missing
 *   - installs backend + frontend deps on first run
 *   - launches FastAPI and Next.js
 *   - shuts both down cleanly on Ctrl+C
 *
 * Thin wrapper scripts (install.sh, start.sh, start.bat) just call into here,
 * so platform-specific bugs can only live in one place.
 */

const { spawn, spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');
const net = require('net');

const rootDir = path.resolve(__dirname, '..');
const backendDir = path.join(rootDir, 'backend');
const frontendDir = path.join(rootDir, 'frontend');
const isWindows = process.platform === 'win32';

const venvDir = path.join(backendDir, 'venv');
const venvPython = isWindows
  ? path.join(venvDir, 'Scripts', 'python.exe')
  : path.join(venvDir, 'bin', 'python3');

function die(msg) {
  console.error('\nERROR: ' + msg + '\n');
  process.exit(1);
}

function run(cmd, args, opts = {}) {
  const res = spawnSync(cmd, args, { stdio: 'inherit', shell: isWindows, ...opts });
  if (res.status !== 0) die(`"${cmd} ${args.join(' ')}" exited with ${res.status}`);
}

function canConnect(host, port, timeoutMs = 300) {
  // Resolves true iff something is listening on host:port (i.e. port is occupied).
  return new Promise((resolve) => {
    const sock = net.createConnection({ host, port });
    let done = false;
    const finish = (v) => { if (!done) { done = true; sock.destroy(); resolve(v); } };
    sock.once('connect', () => finish(true));
    sock.once('error', () => finish(false));
    sock.setTimeout(timeoutMs, () => finish(false));
  });
}

async function isPortFree(port) {
  // A port is busy if either IPv4 loopback or IPv6 loopback accepts a connection.
  // (Bind-probe misses cross-stack conflicts on macOS.)
  const [v4, v6] = await Promise.all([canConnect('127.0.0.1', port), canConnect('::1', port)]);
  return !(v4 || v6);
}

async function ensurePortsFree(ports) {
  const busy = [];
  for (const p of ports) {
    if (!(await isPortFree(p))) busy.push(p);
  }
  if (busy.length === 0) return;
  console.error('\nERROR: required port(s) already in use: ' + busy.join(', '));
  console.error('Stop whatever is listening on those ports and try again.');
  if (process.platform !== 'win32') {
    console.error('Tip: `lsof -iTCP:' + busy[0] + ' -sTCP:LISTEN` shows the culprit.');
  } else {
    console.error('Tip: `netstat -ano | findstr :' + busy[0] + '` shows the culprit PID.');
  }
  process.exit(1);
}

function openBrowser(url) {
  // Platform-native launcher. No npm dep needed.
  if (process.env.AGENT_HARNESS_NO_OPEN) return;
  try {
    if (process.platform === 'darwin') spawn('open', [url], { detached: true, stdio: 'ignore' }).unref();
    else if (isWindows) spawn('cmd', ['/c', 'start', '""', url], { detached: true, stdio: 'ignore' }).unref();
    else spawn('xdg-open', [url], { detached: true, stdio: 'ignore' }).unref();
  } catch (_) { /* non-fatal */ }
}

function waitForHttp(url, timeoutMs = 45_000) {
  // Poll until the dashboard answers with any 2xx/3xx. Returns a Promise<boolean>.
  const start = Date.now();
  return new Promise((resolve) => {
    const tryOnce = () => {
      const req = http.get(url, (res) => {
        res.resume();
        if (res.statusCode && res.statusCode < 500) return resolve(true);
        retry();
      });
      req.on('error', retry);
      req.setTimeout(1500, () => { req.destroy(); retry(); });
    };
    const retry = () => {
      if (Date.now() - start > timeoutMs) return resolve(false);
      setTimeout(tryOnce, 500);
    };
    tryOnce();
  });
}

function which(cmd) {
  const probe = spawnSync(isWindows ? 'where' : 'which', [cmd], { encoding: 'utf8' });
  return probe.status === 0 ? probe.stdout.trim().split(/\r?\n/)[0] : null;
}

function checkNode() {
  const major = parseInt(process.versions.node.split('.')[0], 10);
  if (major < 18) die(`Node.js 18+ required (detected ${process.versions.node}).`);
}

function findPython() {
  // Try python3 first, fall back to python. Windows usually has just `python`.
  for (const cmd of ['python3', 'python']) {
    const p = which(cmd);
    if (!p) continue;
    const probe = spawnSync(cmd, ['-c', 'import sys; print(sys.version_info[:2])'], { encoding: 'utf8' });
    if (probe.status === 0) {
      const m = probe.stdout.match(/\((\d+),\s*(\d+)\)/);
      if (m) {
        const [, maj, min] = m.map(Number);
        if (maj >= 3 && min >= 9) return cmd;
      }
    }
  }
  die('Python 3.9+ is required. Install from https://www.python.org/downloads/ and retry.');
}

function ensureBackend() {
  if (!fs.existsSync(venvDir)) {
    const py = findPython();
    console.log('→ creating Python venv…');
    run(py, ['-m', 'venv', 'venv'], { cwd: backendDir });
  }
  // Always ensure requirements are satisfied. Pip is idempotent and fast when nothing changes.
  console.log('→ installing backend dependencies…');
  run(venvPython, ['-m', 'pip', 'install', '--quiet', '-r', 'requirements.txt'], { cwd: backendDir });
}

function ensureFrontend() {
  if (!which('npm')) die('npm is required but was not found in PATH.');
  if (!fs.existsSync(path.join(frontendDir, 'node_modules'))) {
    console.log('→ installing frontend dependencies (first run can take a minute)…');
    run('npm', ['install'], { cwd: frontendDir });
  }
}

async function start() {
  console.log('\nAgent Observability Harness');
  console.log('---------------------------');
  checkNode();
  ensureBackend();
  ensureFrontend();

  // Fail fast if either required port is taken — otherwise Next bumps to 3001
  // and the auto-opened browser lands on the wrong URL.
  await ensurePortsFree([3000, 8000]);

  console.log('\n→ launching services…');
  const backend = spawn(venvPython, ['main.py'], {
    cwd: backendDir,
    stdio: 'inherit',
    // detached on POSIX gives us a process group we can signal as a unit
    detached: !isWindows,
  });

  const frontend = spawn('npm', ['run', 'dev', '--', '--port', '3000'], {
    cwd: frontendDir,
    stdio: 'inherit',
    shell: true,
    detached: !isWindows,
    env: { ...process.env, PORT: '3000' },
  });

  const dashUrl = 'http://localhost:3000';
  console.log(`\nDashboard:  ${dashUrl}`);
  console.log('API:        http://127.0.0.1:8000');
  console.log('Press Ctrl+C to stop.\n');

  // Auto-launch the dashboard once Next.js is actually responding.
  waitForHttp(dashUrl).then((ok) => {
    if (ok) {
      console.log('→ opening dashboard in your browser…');
      openBrowser(dashUrl);
    }
  });

  let shuttingDown = false;
  const shutdown = (code = 0) => {
    if (shuttingDown) return;
    shuttingDown = true;
    console.log('\n→ stopping services…');
    for (const child of [backend, frontend]) {
      if (!child || child.killed) continue;
      try {
        if (isWindows) {
          // Windows has no SIGTERM → taskkill with /T /F walks the process tree.
          spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F']);
        } else {
          // Signal the whole process group so npm's child node process dies too.
          process.kill(-child.pid, 'SIGTERM');
        }
      } catch (_) { /* already gone */ }
    }
    process.exit(code);
  };

  process.on('SIGINT', () => shutdown(0));
  process.on('SIGTERM', () => shutdown(0));
  backend.on('exit', (code) => shutdown(code || 0));
  frontend.on('exit', (code) => shutdown(code || 0));
}

start();
