#!/usr/bin/env node
/**
 * TokenTelemetry — single cross-platform entry point.
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
const crypto = require('crypto');
const os = require('os');

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

// --- CLI argument parsing -------------------------------------------------
// Accepts --port / --api-port (and -p / -a shorthands), in `--flag value` or
// `--flag=value` form. Anything unknown triggers the help text.
function parseArgs(argv) {
  const out = { frontPort: 3000, apiPort: 8000, host: '127.0.0.1', allowedOrigins: '', authToken: '', insecureNoAuth: false, dataDir: null };
  const take = (i) => {
    if (i + 1 >= argv.length) die(`expected a value after ${argv[i]}`);
    return argv[i + 1];
  };
  const setPort = (key, raw) => {
    const n = parseInt(raw, 10);
    if (!Number.isFinite(n) || n < 1 || n > 65535) die(`invalid port: ${raw}`);
    out[key] = n;
  };
  const setDataDir = (raw) => {
    if (!raw || !raw.trim()) die('expected a path after --data-dir');
    out.dataDir = raw;
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '-h' || a === '--help') { printHelp(); process.exit(0); }
    else if (a === '-p' || a === '--port')     { setPort('frontPort', take(i)); i++; }
    else if (a.startsWith('--port='))          { setPort('frontPort', a.slice('--port='.length)); }
    else if (a === '-a' || a === '--api-port') { setPort('apiPort',   take(i)); i++; }
    else if (a.startsWith('--api-port='))      { setPort('apiPort',   a.slice('--api-port='.length)); }
    else if (a === '--host')                   { out.host = take(i); i++; }
    else if (a.startsWith('--host='))          { out.host = a.slice('--host='.length); }
    else if (a === '--allowed-origins')        { out.allowedOrigins = take(i); i++; }
    else if (a.startsWith('--allowed-origins=')) { out.allowedOrigins = a.slice('--allowed-origins='.length); }
    else if (a === '--auth-token')             { out.authToken = take(i); i++; }
    else if (a.startsWith('--auth-token='))    { out.authToken = a.slice('--auth-token='.length); }
    else if (a === '--insecure-no-auth')       { out.insecureNoAuth = true; }
    else if (a === '-d' || a === '--data-dir') { setDataDir(take(i)); i++; }
    else if (a.startsWith('--data-dir='))      { setDataDir(a.slice('--data-dir='.length)); }
    else die(`unknown argument: ${a}\nRun with --help for usage.`);
  }
  return out;
}

// Pick a concrete, reachable address for the connect/QR URL. 0.0.0.0 is a bind
// wildcard, not a destination, so we can't hand it to a phone. Preference:
//   1. an explicit non-wildcard --host (the operator named it),
//   2. the first --allowed-origins entry (they told us how they'll reach it),
//   3. the primary non-internal IPv4 of this box (best-effort autodetect).
// Returns '' if nothing concrete is available.
function pickConnectHost(host, allowedOrigins) {
  if (host && !['0.0.0.0', '127.0.0.1', 'localhost'].includes(host)) return host;
  const first = (allowedOrigins || '').split(',').map((s) => s.trim()).filter(Boolean)[0];
  if (first) return first;
  for (const addrs of Object.values(os.networkInterfaces())) {
    for (const a of addrs || []) {
      if (a.family === 'IPv4' && !a.internal) return a.address;
    }
  }
  return '';
}

function printHelp() {
  console.log([
    'Usage: tokentelemetry [options]',
    '',
    'Options:',
    '  -p, --port <N>            Frontend (Next.js) port. Default 3000.',
    '  -a, --api-port <N>        Backend (FastAPI) port. Default 8000.',
    '  -d, --data-dir <P>        Where TokenTelemetry stores its config + state.',
    '                            Default ~/.tokentelemetry (sets TOKENTELEMETRY_DATA_DIR).',
    '      --host <ADDR>         Backend bind address. Default 127.0.0.1 (loopback).',
    '                            Use 0.0.0.0 (or an interface IP) to expose remotely.',
    '      --allowed-origins <L> Comma-separated hosts allowed to load the dashboard',
    '                            from another machine (CORS + Next dev origins).',
    '      --auth-token <T>      Access token required for remote requests. If a',
    '                            non-loopback --host is used and this is omitted, a',
    '                            random token is generated and printed once.',
    '      --insecure-no-auth    Disable the remote access token entirely. Only safe',
    '                            on a fully trusted private network (e.g. a tailnet).',
    '  -h, --help               Show this help.',
    '',
    'Examples:',
    '  start.sh                                 # 3000 / 8000, localhost only',
    '  start.sh --port 4000 --api-port 9000     # custom both',
    '  start.sh -p 4000                         # frontend on 4000, backend stays 8000',
    '  start.sh --host 0.0.0.0 \\               # expose on a tailnet/LAN (token auto-gen)',
    '    --allowed-origins box.tailnet.ts.net,100.64.0.1',
    '  start.sh --data-dir /mnt/d/tt-data       # store config + state on D:',
  ].join('\n'));
}

function run(cmd, args, opts = {}) {
  // On Windows we spawn through the shell so PATH-resolved commands (`py`, the
  // python launcher, etc.) work — but cmd.exe re-parses the line and does NOT
  // quote for us. When the repo lives in a path with spaces (e.g.
  // D:\Project Files\…\backend\venv\Scripts\python.exe) the command breaks at
  // the first space ("'D:\Project ' is not recognized…"). Quote the command and
  // any arg containing whitespace or a shell metachar. No-op on macOS/Linux,
  // where shell is off and the args are passed through verbatim.
  const useShell = isWindows;
  const quote = (s) => {
    s = String(s);
    return useShell && /[\s"&|<>^()]/.test(s) ? `"${s.replace(/"/g, '\\"')}"` : s;
  };
  const res = spawnSync(
    useShell ? quote(cmd) : cmd,
    useShell ? args.map(quote) : args,
    { stdio: 'inherit', shell: useShell, ...opts },
  );
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
  // Skip pip install when requirements.txt hasn't changed since last install.
  // Previously this ran every launch (hitting PyPI ~6× per hour for someone
  // restarting often), which is both slow and ironic for a "100% local" tool.
  const reqPath = path.join(backendDir, 'requirements.txt');
  const stampPath = path.join(venvDir, '.requirements.sha');
  let cachedSha = null;
  try { cachedSha = fs.readFileSync(stampPath, 'utf8').trim(); } catch {}
  const currentSha = require('crypto').createHash('sha1').update(fs.readFileSync(reqPath)).digest('hex');
  if (cachedSha === currentSha) return;
  console.log('→ installing backend dependencies…');
  run(venvPython, ['-m', 'pip', 'install', '--quiet', '-r', 'requirements.txt'], { cwd: backendDir });
  try { fs.writeFileSync(stampPath, currentSha); } catch {}
}

function ensureFrontend() {
  if (!which('npm')) die('npm is required but was not found in PATH.');
  // Reinstall when package.json changed since the last install — not just when
  // node_modules is missing. A bare existence check let stale installs linger:
  // users who installed before a new dependency was declared (e.g. qrcode.react,
  // issue #92) kept an old node_modules and hit "Module not found" at runtime.
  // Mirrors ensureBackend()'s requirements.txt SHA stamp. A missing stamp (old
  // install predating this check) hashes to a mismatch, so affected users
  // self-heal on their next launch.
  const nmDir = path.join(frontendDir, 'node_modules');
  const pkgPath = path.join(frontendDir, 'package.json');
  const stampPath = path.join(nmDir, '.package-json.sha');
  const currentSha = require('crypto').createHash('sha1').update(fs.readFileSync(pkgPath)).digest('hex');
  let cachedSha = null;
  try { cachedSha = fs.readFileSync(stampPath, 'utf8').trim(); } catch {}
  if (fs.existsSync(nmDir) && cachedSha === currentSha) return;
  console.log(fs.existsSync(nmDir)
    ? '→ frontend dependencies changed; updating…'
    : '→ installing frontend dependencies (first run can take a minute)…');
  run('npm', ['install'], { cwd: frontendDir });
  try { fs.writeFileSync(stampPath, currentSha); } catch {}
}

async function start() {
  const { frontPort, apiPort, host, allowedOrigins, authToken, insecureNoAuth, dataDir } = parseArgs(process.argv.slice(2));

  // --data-dir is just a friendly front-end for TOKENTELEMETRY_DATA_DIR, which
  // the Python backend reads (tt_paths.data_dir). An explicit flag wins over an
  // env var the user may already have exported.
  const backendEnv = dataDir
    ? { ...process.env, TOKENTELEMETRY_DATA_DIR: dataDir }
    : process.env;

  console.log('\nTokenTelemetry');
  console.log('--------------');
  checkNode();
  ensureBackend();
  ensureFrontend();

  // Fail fast if either required port is taken — otherwise Next bumps to N+1
  // and the auto-opened browser lands on the wrong URL.
  await ensurePortsFree([frontPort, apiPort]);

  // Loopback binds display as "localhost"; a specific interface IP shows as-is.
  const displayHost = (host === '0.0.0.0' || host === '127.0.0.1') ? 'localhost' : host;

  // A concrete (non-wildcard, non-loopback) bind address is itself an origin the
  // browser loads from, so fold it into the allow-list — `--host <ip>` then just
  // works without also repeating the ip in --allowed-origins. 0.0.0.0 has no
  // single hostname to derive, so that case still needs --allowed-origins.
  const hostIsConcrete = host && !['0.0.0.0', '127.0.0.1', 'localhost'].includes(host);
  const allowed = [allowedOrigins, hostIsConcrete ? host : ''].filter(Boolean).join(',');

  // Remote access auth. A non-loopback bind exposes an otherwise unauthenticated
  // API to the network — CORS does NOT stop direct (non-browser) clients — so we
  // require an access token for *remote* requests (loopback is always exempt, so
  // the operator's own browser on the box stays frictionless). Secure by default:
  // a token is auto-generated when none is supplied, unless --insecure-no-auth is
  // passed (for a fully trusted private network). The token is handed ONLY to the
  // backend — never to the frontend env — so it never lands in the client bundle.
  const hostIsRemote = host && !['127.0.0.1', 'localhost'].includes(host);
  let authMode = 'off';      // 'off' | 'token' | 'insecure'
  let resolvedToken = '';
  if (hostIsRemote) {
    if (insecureNoAuth) {
      authMode = 'insecure';
    } else {
      // Honor an explicitly supplied token (flag wins over env, mirroring the
      // TT_HOST / TT_API_PORT convention); otherwise mint a fresh random one.
      resolvedToken = (authToken || process.env.TT_AUTH_TOKEN || '').trim()
        || crypto.randomBytes(24).toString('base64url');
      authMode = 'token';
    }
  }

  // Scan-to-open URL for the "connect a device" QR. Needs a concrete reachable
  // address (0.0.0.0 isn't one): prefer an explicit --host, else the first
  // --allowed-origins entry, else the box's primary LAN IPv4. The token rides
  // in the URL as a one-time bootstrap; the frontend stores it and strips it
  // from the address bar on load (see frontend/src/lib/api.ts).
  const connectHost = pickConnectHost(host, allowedOrigins);
  const connectUrl = (authMode === 'token' && connectHost)
    ? `http://${connectHost}:${frontPort}/?token=${encodeURIComponent(resolvedToken)}`
    : '';

  console.log('\n→ launching services…');
  const backend = spawn(venvPython, ['main.py', '--port', String(apiPort), '--host', host], {
    cwd: backendDir,
    stdio: 'inherit',
    // detached on POSIX gives us a process group we can signal as a unit
    detached: !isWindows,
    // backendEnv carries TOKENTELEMETRY_DATA_DIR when --data-dir is set.
    // TT_ALLOWED_ORIGINS opts extra hosts into the backend's CORS allowlist.
    // TT_AUTH_TOKEN (when set) turns on the remote-access gate; empty == off.
    // TT_REMOTE_CONNECT_URL backs the loopback-only /remote-access (QR) endpoint.
    env: {
      ...backendEnv,
      TT_ALLOWED_ORIGINS: allowed,
      TT_AUTH_TOKEN: resolvedToken,
      TT_REMOTE_CONNECT_URL: connectUrl,
    },
  });

  const frontend = spawn('npm', ['run', 'dev', '--', '--port', String(frontPort)], {
    cwd: frontendDir,
    stdio: 'inherit',
    shell: true,
    detached: !isWindows,
    // The frontend derives its API base from window.location at runtime (see
    // frontend/src/lib/api.ts), so it only needs the API *port* — the host
    // follows whatever address the dashboard was opened on (localhost, LAN IP,
    // tailnet, …). TT_ALLOWED_ORIGINS feeds Next's allowedDevOrigins so the dev
    // server serves its chunks to those non-localhost origins.
    env: {
      ...process.env,
      PORT: String(frontPort),
      NEXT_PUBLIC_API_PORT: String(apiPort),
      TT_ALLOWED_ORIGINS: allowed,
    },
  });

  const dashUrl = `http://${displayHost}:${frontPort}`;
  console.log(`\nDashboard:  ${dashUrl}`);
  console.log(`API:        http://${displayHost}:${apiPort}`);

  try {
    const resolvedDataDir = require('child_process').spawnSync(venvPython, ['-c', 'from tt_paths import data_dir; print(data_dir())'], { cwd: backendDir, encoding: 'utf8', env: backendEnv }).stdout.trim();
    if (resolvedDataDir) console.log(`Data dir:   ${resolvedDataDir}`);
  } catch (_) {
    if (dataDir) console.log(`Data dir:   ${dataDir}`);
  }

  if (authMode === 'token') {
    console.log('\n──────────────────────────────────────────────────────────');
    console.log('Remote access is ON. Other devices must enter this token:');
    console.log(`\n    ${resolvedToken}\n`);
    if (connectUrl) {
      console.log('Or skip the typing — open this link (or scan its QR from the');
      console.log('dashboard’s "Connect a device" panel) on the other device:');
      console.log(`\n    ${connectUrl}\n`);
    } else {
      console.log('Open the dashboard from another device and paste it when');
      console.log('prompted. (Your browser on this machine is exempt.)\n');
    }
    console.log('The token is shown once — re-run to rotate it.');
    console.log('──────────────────────────────────────────────────────────');
  } else if (authMode === 'insecure') {
    console.log('\n⚠  WARNING: --insecure-no-auth — the dashboard is exposed to the');
    console.log('   network with NO access token. Anyone who can reach this host can');
    console.log('   read your data and change settings. Only use this on a fully');
    console.log('   trusted private network (e.g. a tailnet).');
  }
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
