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
 * The first argument is a verb when it matches one of: dashboard, menubar,
 * desktop, status, stop. Anything else falls through to flag parsing, so
 * `tokentelemetry --port 4000` behaves exactly as it always has. The bare
 * command (no verb) starts the dashboard.
 *
 * Thin wrapper scripts (install.sh, start.sh, start.bat) just call into here,
 * so platform-specific bugs can only live in one place.
 *
 * The parsing/dispatch helpers are exported for `node --test`; the CLI only
 * runs when this file is the entrypoint (require.main === module).
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

// A bad flag. Thrown rather than calling die() so the parse layer is testable;
// main() catches it and prints through die(), preserving the exit behaviour.
class UsageError extends Error {}

// --- Verbs ------------------------------------------------------------------
// The first CLI argument is a verb only when it matches one of these; anything
// else (including the empty case) means "dashboard", so `--port 4000` and a
// stray argument can never silently change what the command does.
const VERBS = ['dashboard', 'menubar', 'desktop', 'status', 'stop'];

function parseInvocation(argv) {
  if (argv.length > 0 && VERBS.includes(argv[0])) {
    return { verb: argv[0], args: argv.slice(1) };
  }
  return { verb: 'dashboard', args: argv };
}

// --- CLI argument parsing -------------------------------------------------
// Accepts --port / --api-port (and -p / -a shorthands), in `--flag value` or
// `--flag=value` form. Anything unknown throws a UsageError. Returns
// { help, options }: help is true when -h/--help was seen (the caller prints
// help and exits 0).
function parseArgs(argv) {
  const out = { frontPort: 3000, apiPort: 8000, host: '127.0.0.1', allowedOrigins: '', authToken: '', insecureNoAuth: false, dataDir: null, noOpen: false };
  const fail = (msg) => { throw new UsageError(msg); };
  const take = (i) => {
    if (i + 1 >= argv.length) fail(`expected a value after ${argv[i]}`);
    return argv[i + 1];
  };
  const setPort = (key, raw) => {
    const n = parseInt(raw, 10);
    if (!Number.isFinite(n) || n < 1 || n > 65535) fail(`invalid port: ${raw}`);
    out[key] = n;
  };
  const setDataDir = (raw) => {
    if (!raw || !raw.trim()) fail('expected a path after --data-dir');
    out.dataDir = raw;
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '-h' || a === '--help') { return { help: true, options: out }; }
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
    else if (a === '--no-open')                { out.noOpen = true; }
    else if (a === '-d' || a === '--data-dir') { setDataDir(take(i)); i++; }
    else if (a.startsWith('--data-dir='))      { setDataDir(a.slice('--data-dir='.length)); }
    else fail(`unknown argument: ${a}\nRun with --help for usage.`);
  }
  return { help: false, options: out };
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
    'Usage: tokentelemetry [command] [options]',
    '',
    'Commands:',
    '  dashboard [options]        Start the dashboard (the default).',
    '  menubar                    Menu bar / system tray panel.',
    '  desktop                    Desktop app.',
    '  status                     Dashboard status (not available yet).',
    '  stop                       Stop the dashboard (not available yet).',
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
    '      --no-open             Do not open the dashboard in a browser. Useful from',
    '                            scripts; AGENT_HARNESS_NO_OPEN still works too.',
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

function runSoft(cmd, args, opts = {}) {
  // Returns the exit status instead of dying, for commands we want to attempt
  // and recover from (pip probes, the ensurepip repair).
  //
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
  return res.status;
}

function run(cmd, args, opts = {}) {
  const status = runSoft(cmd, args, opts);
  if (status !== 0) die(`"${cmd} ${args.join(' ')}" exited with ${status}`);
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

// True unless the caller passed --no-open or AGENT_HARNESS_NO_OPEN is set.
// Split out so the suppression logic is unit-testable without spawning.
function shouldOpenBrowser(options) {
  if (options && options.noOpen) return false;
  if (process.env.AGENT_HARNESS_NO_OPEN) return false;
  return true;
}

function openBrowser(url, options) {
  // Platform-native launcher. No npm dep needed.
  if (!shouldOpenBrowser(options)) return;
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
  const [major, minor] = process.versions.node.split('.').map(Number);
  if (major < 20 || (major === 20 && minor < 9)) {
    die(`Node.js 20.9+ required (detected ${process.versions.node}).`);
  }
}

function checkDesktopNode() {
  const [major, minor] = process.versions.node.split('.').map(Number);
  // Electron's current installer requires this newer Node line. Keep the
  // ordinary dashboard's existing Node 20.9 floor unchanged.
  if (major < 22 || (major === 22 && minor < 12)) {
    die(`TokenTelemetry Desktop requires Node.js 22.12+ (detected ${process.versions.node}).`);
  }
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

function pythonSeries() {
  // "3.10" for the venv interpreter (or the system one, if there's no venv yet).
  // Used to name the right distro package in the pip-bootstrap hint. No shell,
  // so paths with spaces are safe on every platform.
  const cmd = fs.existsSync(venvPython) ? venvPython : 'python3';
  const probe = spawnSync(cmd, ['-c', 'import sys; print("%d.%d" % sys.version_info[:2])'], { encoding: 'utf8' });
  return probe.status === 0 ? probe.stdout.trim() : '';
}

function pipBootstrapHint() {
  if (isWindows) {
    return 'Reinstall Python from https://www.python.org/downloads/ with the "pip" component\nselected, then delete backend\\venv and run this again.';
  }
  if (process.platform === 'darwin') {
    return 'Install a Python that bundles pip (e.g. `brew install python`), then delete\nbackend/venv and run this again.';
  }
  const series = pythonSeries();
  return [
    "Python couldn't bootstrap pip into the venv. On Debian/Ubuntu that step ships",
    'in a separate package:',
    `  sudo apt install python${series || '3'}-venv`,
    '  sudo dnf install python3-pip        # Fedora/RHEL',
    'Then delete backend/venv and run this again.',
  ].join('\n');
}

function findUv() {
  // Opportunistic only: uv builds the venv itself instead of going through the
  // stdlib venv module, so it never touches ensurepip, and it installs an order
  // of magnitude faster. We never install it — if it isn't already on PATH we
  // use python/pip exactly as before, so uv is a speed-up, not a prerequisite.
  // TT_NO_UV=1 forces the pip path.
  if (process.env.TT_NO_UV === '1') return null;
  if (!which('uv')) return null;
  return runSoft('uv', ['--version'], { stdio: 'ignore' }) === 0 ? 'uv' : null;
}

function venvPipWorks() {
  if (!fs.existsSync(venvPython)) return false;
  return runSoft(venvPython, ['-m', 'pip', '--version'], { stdio: 'ignore' }) === 0;
}

function ensureVenvPip() {
  if (venvPipWorks()) return;
  // The venv directory and its interpreter can both exist while pip does not:
  // `python -m venv` bootstraps pip through ensurepip as its final step, and on
  // Debian/Ubuntu that step is what fails when python3-venv isn't installed.
  // The half-built tree is left behind, so the next launch skips creation and
  // dies with "No module named pip" (issue #267). Repair it from the wheels
  // bundled with the stdlib — offline, no PyPI round-trip.
  console.log('→ venv has no pip, bootstrapping it…');
  runSoft(venvPython, ['-m', 'ensurepip', '--upgrade']);
  if (venvPipWorks()) return;
  die('the Python venv at backend/venv has no working pip.\n' + pipBootstrapHint());
}

function ensureBackend() {
  const uv = findUv();
  // Check for the interpreter rather than the directory: an interrupted or
  // failed `python -m venv` leaves a directory behind with nothing runnable in
  // it. Re-running venv creation over an existing directory fills in what's
  // missing, so there's nothing to delete here.
  if (!fs.existsSync(venvPython)) {
    const py = findPython();
    console.log(uv ? '→ creating Python venv (uv)…' : '→ creating Python venv…');
    // Pin uv to the same interpreter the pip path would have used, so `uv` on
    // PATH changes the speed of the bootstrap and nothing else. The resolved
    // path matters: given the bare name `python3`, uv prefers its own managed
    // CPython over the one on PATH, which would quietly build the venv on a
    // different Python than every previous release. An absolute path also means
    // uv has nothing to go and download. --seed puts pip inside the venv: uv
    // leaves it out by default, and without it a user who later drops uv gets a
    // venv this script can't install into.
    let created = uv
      ? runSoft(uv, ['venv', 'venv', '--seed', '--python', which(py) || py], { cwd: backendDir })
      : runSoft(py, ['-m', 'venv', 'venv'], { cwd: backendDir });
    if (uv && created !== 0) {
      // A uv old enough not to know one of these flags shouldn't cost anyone
      // their install. Unlike a retry of the same command this is a different
      // tool, which can genuinely succeed where the first one didn't.
      console.log('→ uv could not create the venv, falling back to python -m venv…');
      created = runSoft(py, ['-m', 'venv', 'venv'], { cwd: backendDir });
    }
    if (created !== 0 || !fs.existsSync(venvPython)) {
      die('could not create the Python venv at backend/venv.\n' + pipBootstrapHint());
    }
  }
  // Skip pip install when requirements haven't changed since last install.
  // Previously this ran every launch (hitting PyPI ~6× per hour for someone
  // restarting often), which is both slow and ironic for a "100% local" tool.
  const reqPath = path.join(backendDir, 'requirements.txt');
  const lockPath = path.join(backendDir, 'requirements.lock');
  const stampPath = path.join(venvDir, '.requirements.sha');
  // Prefer the hash-pinned lock: `--require-hashes` makes pip verify every
  // download (including transitive deps) against a hash recorded here, so a
  // registry compromise between installs can't silently swap in a malicious
  // package. Fall back to the human-edited requirements.txt when no lock is
  // present (older checkout predating this change) so those users aren't
  // broken.
  const useLock = fs.existsSync(lockPath) && /--hash=/.test(fs.readFileSync(lockPath, 'utf8'));
  const installFrom = useLock ? lockPath : reqPath;
  let cachedSha = null;
  try { cachedSha = fs.readFileSync(stampPath, 'utf8').trim(); } catch {}
  const currentSha = require('crypto').createHash('sha1').update(fs.readFileSync(installFrom)).digest('hex');
  if (cachedSha === currentSha) return;
  const reqFile = useLock ? 'requirements.lock' : 'requirements.txt';
  const hashFlags = useLock ? ['--require-hashes'] : [];
  if (uv) {
    // uv reads the same pip-style lock and enforces the same hashes. --python
    // targets our venv explicitly rather than whatever VIRTUAL_ENV points at.
    console.log('→ installing backend dependencies (uv)…');
    if (runSoft(uv, ['pip', 'install', '--quiet', '--python', venvPython, ...hashFlags, '-r', reqFile], { cwd: backendDir }) !== 0) {
      die(`installing backend dependencies with uv failed (see above).\nRe-run with TT_NO_UV=1 to install ${reqFile} with pip instead.`);
    }
  } else {
    // Only probe pip on the install path. The stamp lives inside the venv, so a
    // matching stamp means this venv already completed an install with a working
    // pip — no need to pay a Python startup on every launch.
    ensureVenvPip();
    console.log('→ installing backend dependencies…');
    run(venvPython, ['-m', 'pip', 'install', '--quiet', ...hashFlags, '-r', reqFile], { cwd: backendDir });
  }
  try { fs.writeFileSync(stampPath, currentSha); } catch {}
}

function ensureFrontend() {
  if (!which('npm')) die('npm is required but was not found in PATH.');
  // Reinstall when the declared dependencies changed since the last install —
  // not just when node_modules is missing. A bare existence check let stale
  // installs linger: users who installed before a new dependency was declared
  // (e.g. qrcode.react, issue #92) kept an old node_modules and hit
  // "Module not found" at runtime. Mirrors ensureBackend()'s SHA stamp, which
  // hashes the file it actually installs from. A missing stamp (old install
  // predating this check) hashes to a mismatch, so affected users self-heal on
  // their next launch.
  const nmDir = path.join(frontendDir, 'node_modules');
  const pkgPath = path.join(frontendDir, 'package.json');
  const lockPath = path.join(frontendDir, 'package-lock.json');
  const stampPath = path.join(nmDir, '.package-json.sha');
  // Hash the lockfile too, because `npm ci` below installs exactly what the lock
  // pins — the lock, not package.json, decides what lands in node_modules.
  // Stamping package.json alone meant a lockfile-only change was invisible here:
  // a transitive security bump moves the lock while every declared range stays
  // put, so existing installs kept the vulnerable versions until package.json
  // happened to change for some unrelated reason. package.json stays in the
  // hash to cover the `npm install` fallback path when no lock is present.
  const stampInputs = fs.existsSync(lockPath) ? [pkgPath, lockPath] : [pkgPath];
  const hash = require('crypto').createHash('sha1');
  for (const input of stampInputs) hash.update(fs.readFileSync(input));
  const currentSha = hash.digest('hex');
  let cachedSha = null;
  try { cachedSha = fs.readFileSync(stampPath, 'utf8').trim(); } catch {}
  if (fs.existsSync(nmDir) && cachedSha === currentSha) return;
  console.log(fs.existsSync(nmDir)
    ? '→ frontend dependencies changed; updating…'
    : '→ installing frontend dependencies (first run can take a minute)…');
  // Prefer `npm ci` — it installs exactly what package-lock.json pins (supply-chain
  // hardening: a compromised registry can't slip a newer, malicious version past a
  // committed lockfile) and is faster since it skips dependency resolution. Older
  // checkouts predating the committed lockfile (or a repo where it was deleted)
  // fall back to `npm install` so those users aren't broken.
  if (fs.existsSync(lockPath)) {
    run('npm', ['ci'], { cwd: frontendDir });
  } else {
    run('npm', ['install'], { cwd: frontendDir });
  }
  try { fs.writeFileSync(stampPath, currentSha); } catch {}
}

async function start(options) {
  const { frontPort, apiPort, host, allowedOrigins, authToken, insecureNoAuth, dataDir } = options;

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

  // Next dev otherwise listens on every interface even when the API is
  // loopback-only. Bind both services to the same explicit host so the default
  // launch is actually localhost-only and remote mode stays opt-in.
  const npmCommand = isWindows ? 'npm.cmd' : 'npm';
  const frontend = spawn(npmCommand, ['run', 'dev', '--', '--hostname', host, '--port', String(frontPort)], {
    cwd: frontendDir,
    stdio: 'inherit',
    // Windows: .cmd files cannot be spawned directly (EINVAL); shell:true routes
    // through cmd.exe. Local patch 2026-09-04 (upstream bug, see nodejs/node#59210).
    shell: isWindows,
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
      openBrowser(dashUrl, options);
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

// --- Subcommand messages ----------------------------------------------------
// The desktop shell owns local backend/frontend processes and always addresses
// them through localhost. 127.0.0.1 remains only a legacy CLI bind default.

function menubarMessage() {
  return 'Starting the TokenTelemetry menu bar…';
}

function desktopMessage() { return 'Starting TokenTelemetry Desktop…'; }

function statusMessage() {
  return 'tokentelemetry status is not implemented yet.';
}

function stopMessage() {
  return 'tokentelemetry stop is not implemented yet.';
}

// --- Menu bar / system tray ---------------------------------------------------
// The menu bar panel is the desktop app started tray-only: same Electron
// process as `tokentelemetry desktop`, minus the dashboard window. It renders
// the app's own /menubar page, so the panel and the dashboard's plan-limits
// section cannot drift, and it works anywhere Electron has a tray rather than
// on macOS alone. The earlier rumps implementation is still in backend/menubar/
// but is no longer wired to a command; retiring it is a separate change.

function menubarEnv(dataDir, env = process.env) {
  const base = dataDir ? { ...env, TOKENTELEMETRY_DATA_DIR: dataDir } : env;
  // desktop/main.cjs reads this and skips creating the dashboard window.
  return { ...base, TT_TRAY_ONLY: '1' };
}

function startMenubar(options = {}) {
  checkNode();
  checkDesktopNode();
  ensureBackend();
  ensureFrontend();
  const electron = ensureDesktopElectron();
  const { command, args, shell } = desktopSpawnCommand(
    electron, path.join(rootDir, 'desktop', 'main.cjs'));
  const child = spawn(command, args, {
    cwd: rootDir,
    detached: !isWindows,
    stdio: 'ignore',
    shell,
    env: menubarEnv(options.dataDir),
  });
  child.unref();
  return 0;
}

function electronExecutable(root = rootDir, platform = process.platform) {
  return path.join(root, 'node_modules', '.bin', platform === 'win32' ? 'electron.cmd' : 'electron');
}

function ensureDesktopElectron() {
  const executable = electronExecutable();
  if (fs.existsSync(executable)) return executable;
  if (!which('npm')) die('npm is required to install TokenTelemetry Desktop.');
  console.log('→ installing TokenTelemetry Desktop…');
  run('npm', ['install', '--no-audit', '--no-fund'], { cwd: rootDir });
  if (!fs.existsSync(executable)) {
    die('TokenTelemetry Desktop did not install correctly. Re-run `npm install` in the TokenTelemetry checkout.');
  }
  return executable;
}

function desktopEnv(dataDir, env = process.env) {
  return dataDir ? { ...env, TOKENTELEMETRY_DATA_DIR: dataDir } : env;
}

// Node cannot spawn a .cmd directly with shell:false on Windows — it throws
// EINVAL (nodejs/node#59210), and electronExecutable() resolves to electron.cmd
// there. Routing through cmd.exe fixes that, but Node does NOT quote the file or
// its arguments when shell is true: it simply joins them with spaces. Both of
// these are absolute paths under the install directory, which routinely contains
// a space ("C:\Users\dev\My Documents\..."), so they are quoted explicitly here.
// Quoting on POSIX would make the quotes part of the filename, so it is
// Windows-only, and the spawn stays shell-free everywhere else.
function desktopSpawnCommand(electron, scriptPath, platform = process.platform) {
  if (platform !== 'win32') return { command: electron, args: [scriptPath], shell: false };
  return { command: `"${electron}"`, args: [`"${scriptPath}"`], shell: true };
}

function startDesktop(options = {}) {
  checkNode();
  checkDesktopNode();
  ensureBackend();
  ensureFrontend();
  const electron = ensureDesktopElectron();
  const { command, args, shell } = desktopSpawnCommand(
    electron, path.join(rootDir, 'desktop', 'main.cjs'));
  const child = spawn(command, args, {
    cwd: rootDir,
    detached: !isWindows,
    stdio: 'ignore',
    shell,
    env: desktopEnv(options.dataDir),
  });
  child.unref();
  return 0;
}

function cmdMenubar(options = {}) {
  console.log(menubarMessage());
  return startMenubar(options);
}

function cmdDesktop(options = {}) {
  return startDesktop(options);
}

function cmdStatus() {
  console.error(statusMessage());
  return 1;
}

function cmdStop() {
  console.error(stopMessage());
  return 1;
}

// --- Dispatch + entrypoint ---------------------------------------------------
async function main(argv = process.argv.slice(2)) {
  const { verb, args } = parseInvocation(argv);
  let parsed;
  try {
    parsed = parseArgs(args);
  } catch (err) {
    if (err instanceof UsageError) die(err.message);
    throw err;
  }
  if (parsed.help) {
    printHelp();
    return 0;
  }
  switch (verb) {
    case 'menubar': return cmdMenubar(parsed.options);
    case 'desktop': return cmdDesktop(parsed.options);
    case 'status': return cmdStatus();
    case 'stop': return cmdStop();
    case 'dashboard':
    default:
      // The bare command and `dashboard` are the same path. start() never
      // returns until the user stops it, so no exit code follows this await.
      await start(parsed.options);
      return undefined;
  }
}

if (require.main === module) {
  main().then((code) => {
    if (typeof code === 'number') process.exit(code);
  }).catch((err) => {
    console.error(err && err.stack ? err.stack : String(err));
    process.exit(1);
  });
}

module.exports = {
  VERBS,
  UsageError,
  parseInvocation,
  parseArgs,
  printHelp,
  shouldOpenBrowser,
  openBrowser,
  checkDesktopNode,
  start,
  main,
  cmdMenubar,
  cmdDesktop,
  cmdStatus,
  cmdStop,
  menubarMessage,
  desktopMessage,
  statusMessage,
  stopMessage,
  menubarEnv,
  startMenubar,
  electronExecutable,
  desktopEnv,
  desktopSpawnCommand,
  startDesktop,
};
