# macOS Menu Bar, Global CLI, and Desktop App

Status: in progress. The global CLI and macOS menu bar are implemented; the Electron
desktop development shell is implemented, while packaged release builds remain deferred.
The work was prompted by wanting plan limits visible in the macOS menu bar without opening
the dashboard, and by the `hermes dashboard` / `hermes desktop` commands working from any
directory.

## Decisions taken before writing this

1. The menu bar app is **standalone and macOS-only**, not a feature of an Electron app.
2. It is written in Python with `rumps` so it can call `QuotaService` directly.
3. The global CLI comes first, because it is small and both other features hang off it.

## Summary of what changes

| Feature | Effort | Depends on |
| --- | --- | --- |
| `tokentelemetry` on PATH with subcommands | Small | Nothing |
| `tokentelemetry menubar` (macOS) | Medium | Subcommands |
| `tokentelemetry desktop` (Electron) | Large | Subcommands. Runnable shell implemented; packaging deferred. |

---

# Part 1: How Hermes does it

Read from a local `hermes-agent` checkout on 2026-08-31.

## `hermes` resolves from any directory

`pyproject.toml:387` declares console scripts:

```toml
[project.scripts]
hermes = "hermes_cli.main:main"
```

pip/uv writes an executable shim into the environment's `bin/`, which is on PATH. Nothing
clever is happening: the command is location-independent because the installer put it
somewhere PATH already points, and the Python package is importable from anywhere.

## `hermes dashboard`

`hermes_cli/main.py:11946`, `cmd_dashboard`. The parts worth copying:

- **`--status` and `--stop`** are handled before any dependency work, so they stay fast and
  work even when the install is half-broken.
- **An already-running dashboard is not an error.** `_dashboard_listening(host, port)` is
  checked first; if something is already serving, it opens the browser at that URL and
  exits 0 rather than failing on a port collision.
- **PIDs are tracked** so a later `hermes update` can kill servers still running old code.
  `hermes_cli/dashboard_procs.py` documents why: a long-lived dashboard keeps the old
  Python backend in memory while the JS bundle on disk is replaced, and the resulting
  frontend/backend mismatch shows up as every API call returning 401.
- **`--no-open`** suppresses the browser launch, which is what makes the command usable
  from scripts and from the desktop app.

## `hermes desktop`

`hermes_cli/main.py:8269`, `cmd_gui`. It resolves `apps/desktop`, decides whether to build
or reuse a packaged app via `_desktop_packaged_executable` (`main.py:6921`, which globs
`release/mac*/Hermes.app/Contents/MacOS/Hermes` and the Windows/Linux equivalents), then
launches Electron with a prepared environment.

The Electron main process then spawns the Python backend as a child:

```
apps/desktop/electron/main.ts:12359
    const backendArgs = ['serve', '--host', '127.0.0.1', '--port', '0']
```

`--port 0` is worth stealing. The desktop app asks the OS for an ephemeral port instead of
guessing one, so it can never collide with a dashboard the user already has open.

## What Hermes does not have

There is no tray or menu bar. `apps/desktop/electron/main.ts` contains no `new Tray(`; the
only `systemPreferences` uses are media-access permission checks. The menu bar work here has
no prior art in that codebase to follow.

## Scale, as a warning

`apps/desktop/electron/main.ts` is **17,621 lines**. That is the cost of Hermes's desktop
app carrying its own renderer, terminal emulator, profile pool, and update machinery.
TokenTelemetry's desktop app should not be sized like that, for reasons in Part 4.3.

---

# Part 2: TokenTelemetry today

## The CLI is already location-independent

This was the surprise. `bin/cli.js:23` resolves everything from the script's own location:

```js
const rootDir = path.resolve(__dirname, '..');
const backendDir = path.join(rootDir, 'backend');
const frontendDir = path.join(rootDir, 'frontend');
```

Node resolves symlinks when computing `__dirname`, so a symlink on PATH still points the
process at the real checkout. Verified rather than assumed, see the Evidence appendix.

**Nothing about `bin/cli.js` needs to change for it to run from any directory.** The only
missing piece is an install step that puts it on PATH.

## Nothing puts it on PATH

`package.json` already declares the entry point:

```json
"bin": { "tokentelemetry": "./bin/cli.js" }
```

but no installer consumes it. `install.sh` clones the repository and ends with
`exec node bin/cli.js`; `install.ps1` ends the same way. `start.sh` and `start.bat` are
wrappers that `cd` to their own directory first. So the documented way to start
TokenTelemetry is to `cd` into the clone, which is exactly the gap being closed.

## The CLI has no subcommands

`bin/cli.js` parses flags only (`parseArgs`, line 41) and calls a single `start()` (line
418). There is no argument that selects a mode. Adding `dashboard` / `menubar` / `desktop`
means introducing a verb layer that did not exist.

## Behaviours already present and reusable

| Capability | Location | Note |
| --- | --- | --- |
| Platform-native browser launch | `bin/cli.js:189` `openBrowser` | Already handles darwin/win32/linux |
| Suppress that launch | `bin/cli.js:190` | Honours `AGENT_HARNESS_NO_OPEN` |
| Wait for the server to answer | `bin/cli.js:199` `waitForHttp` | Polls for 2xx/3xx |
| Detect a listening port | `bin/cli.js:154` `canConnect` | Checks IPv4 and IPv6 loopback |
| Dependency bootstrap | `bin/cli.js:305,374` | venv and node_modules, with SHA stamps |
| Data directory resolution | `backend/tt_paths.py` | `TOKENTELEMETRY_DATA_DIR`, then `TOKENTELEMETRY_HOME`, then `~/.tokentelemetry` |

## Behaviours that need to change

- **A busy port is currently fatal.** `ensurePortsFree` (`bin/cli.js:173`) prints an error
  and calls `process.exit(1)`. Hermes's behaviour is better for a command people will run
  reflexively from any directory: if TokenTelemetry is already serving on that port, open
  the browser and exit 0. Only a *foreign* process on the port is an error.
- **There is no daemon mode and no PID file.** `start()` runs in the foreground and
  `shutdown()` (`bin/cli.js:562`) kills both children on Ctrl+C. `--status` and `--stop`
  need somewhere to look; a pidfile under `data_dir()` is the natural place.
- **The frontend runs `npm run dev`** (`bin/cli.js:502`), not a production build. Fine for
  the dashboard, but it means the desktop app cannot simply reuse the current launch path.

---

# Part 3: The constraint that shapes the menu bar

Quota data is refreshed **only** by an HTTP request. `QuotaService.collect()` has exactly
two callers, both route handlers:

```
backend/main.py:2989   GET  /quotas          -> collect()
backend/main.py:2995   POST /quotas/refresh  -> collect(force=True)
```

There is no scheduler, no background task, no startup refresh. The persisted snapshot at
`data_dir()/quotas.json` is written by `QuotaService._save()` during a `collect()` and is
otherwise inert.

The consequence for a menu bar app: **reading `quotas.json` is not enough.** With the
backend stopped, the file holds whatever was true when the dashboard was last open, which
could be days old. A menu bar showing a stale "12% used" while the real weekly sits at 95%
is worse than showing nothing, because it is confidently wrong.

Three ways out:

| Option | Fresh? | Cost |
| --- | --- | --- |
| Read `quotas.json` only | No | Silently wrong when the backend is down |
| Require the backend running, poll `/quotas` | Yes | Menu bar useless on its own; must manage a server |
| **Import `QuotaService` and collect in-process** | Yes | Needs the Python environment, macOS-only by choice |

The third is why this app is Python rather than Swift or Electron. It reuses every provider
in `backend/quotas.py` verbatim, shares the same five-minute cache file with the backend so
the two never double-fetch, and needs no server at all.

---

# Part 4: Designs

## 4.1 Global CLI with subcommands

### Shape

```
tokentelemetry                    # unchanged: start the dashboard
tokentelemetry dashboard [flags]  # explicit form of the above
tokentelemetry menubar            # macOS only
tokentelemetry desktop            # later
tokentelemetry status
tokentelemetry stop
```

The bare form keeps starting the dashboard. Every existing flag keeps working, so
`start.sh --port 4000` and every README line stay correct. A first argument is treated as a
verb only when it matches a known one; anything else falls through to flag parsing, so a
stray argument cannot silently change what the command does.

### Getting onto PATH

The installer writes a shim rather than relying on `npm link`, for one reason: npm's global
directory is Node-version-specific under nvm, so a user who switches Node versions loses the
command with no obvious explanation. A shim in a stable location survives that.

- macOS/Linux: `~/.local/bin/tokentelemetry`, a two-line `exec node <clone>/bin/cli.js "$@"`.
  `install.sh` creates it and warns if `~/.local/bin` is not on PATH.
- Windows: `install.ps1` writes `tokentelemetry.cmd` alongside a `.ps1`, into a directory it
  adds to the user PATH. A `.cmd` is what makes the bare name work from both PowerShell and
  `cmd.exe` even when the execution policy refuses unsigned `.ps1` files.

### Already-running detection

`status` and `stop` read a pidfile at `data_dir()/dashboard.pid` holding the pids and ports
of the running pair. `dashboard` checks it first:

- pidfile present, process alive, port answering: open the browser, exit 0.
- pidfile stale (process gone): delete it and start normally.
- port busy but not ours: the current error, which is still correct.

### Off-platform behaviour

`tokentelemetry menubar` on Windows or Linux prints one line saying the menu bar app is
macOS-only and exits non-zero. It must not surface an ImportError about `rumps`.

## 4.2 macOS menu bar app

### Placement

`backend/menubar/` (Python, alongside the code it imports) rather than a separate top-level
tree. It is not a second application; it is a second front end onto `quotas.py`.

### Runtime

`rumps` for the status item. One dependency, added to a `requirements-macos.txt` so a Linux
or Windows install never tries to resolve it.

### What it shows

The title carries the worst window across every signed-in provider, matching the sidebar
gauge exactly: `worstWindow()` in `frontend/src/lib/quotas.ts` and `worst_window` here must
agree, so the number in the menu bar is the number in the dashboard.

```
  ◔ 89%              <- title: worst window, tinted at 75 / 90
  ──────────────────
  Codex        Plus
    Session          Limit reached
    Weekly           16% used
  Claude Code   Pro
    Session          73% used
    Weekly           89% used
  ──────────────────
  14 agents with no live quota
  ──────────────────
  Open dashboard
  Refresh now
  Launch at login    ✓
  Quit
```

Thresholds are the existing 75 and 90 from `backend/harness_panels/base.py`
(`QUOTA_WARN_AT`, `QUOTA_CRITICAL_AT`) and `frontend/src/lib/quotas.ts`. A fourth copy of
those constants is a mistake waiting to happen; the Python ones are imported, not restated.

macOS menu bar titles are monochrome by default, so severity is carried by a symbol plus the
number rather than colour alone. `Open dashboard` shells out to the same CLI, which means it
inherits the already-running detection from 4.1 for free.

### Refresh cadence

A `rumps.Timer` calling `QuotaService.collect()`. `collect()` already honours the
five-minute `FRESHNESS` window and returns the cached snapshot when it is still warm, so the
timer can run more often than the network does. Polling every 60 seconds costs one file read
in the common case.

The menu bar and the backend can both be running. They share `data_dir()/quotas.json` and
`QuotaService` already writes atomically (`_save()` writes a `.tmp` and calls `replace`), so
the concurrent case is a read of one or the other version, never a torn file.

### Launch at login

A LaunchAgent plist at `~/Library/LaunchAgents/com.tokentelemetry.menubar.plist`, written
and removed by the menu item. Not installed by default: a tool that adds itself to login
items without being asked is a tool people uninstall.

### Testing

`rumps` cannot run headless, so the split matters. All of the logic (worst-window selection,
title formatting, threshold colouring, menu construction as data) lives in a plain module
with no `rumps` import and is unit-tested like everything else in `backend/`. The `rumps`
layer is a thin renderer over that structure.

## 4.3 Electron desktop app

The first implementation is a small Electron shell. `tokentelemetry desktop` launches
Electron, which owns a FastAPI child and a separate Next development server. Both are bound
and addressed as `localhost` on ephemeral ports, avoiding collisions with an already-running
browser dashboard. The desktop server uses `frontend/.next-desktop`, so it never takes the
ordinary dashboard's `.next` lock. Closing the Electron app terminates both child process
groups. The renderer is sandboxed with Node integration disabled and context isolation on.

The menu-bar app stays standalone; its **Open dashboard** action launches this desktop shell
instead of opening a browser.

### It is much smaller here than in Hermes

`frontend/` has no API routes and every piece of data arrives from FastAPI through
client-side fetch. For a packaged desktop build,
`next.config.ts` can move from `output: "standalone"` to `output: "export"`, producing static
files that Electron loads directly with no Node server in the app at all.

That removes most of what makes Hermes's `main.ts` 17,621 lines. A first version is a
`BrowserWindow`, a spawned backend child, and a health check.

### Sketch

1. `tokentelemetry desktop` resolves a packaged app (the `_desktop_packaged_executable`
   pattern from `hermes_cli/main.py:6921`) and launches it, or builds first.
2. Electron main spawns `backend/main.py --host localhost --port <ephemeral>`, waits for
   health, then loads the renderer at `http://localhost:<ephemeral>`.
3. The window loads the static export with the port injected.
4. electron-builder produces a `.dmg`.

### Open question

The tray belongs here for Windows and Linux, at which point there are two menu bar
implementations. That is acceptable if the shared logic module from 4.2 is what both render,
and a mistake if the Electron one re-derives anything.

---

# Evidence appendix

## The CLI already works from any directory

A symlink to `bin/cli.js` was placed on PATH and invoked from `/tmp`:

```
$ cd /tmp && PATH="<shimdir>:$PATH" tokentelemetry --help
Usage: tokentelemetry [options]
...
exit=0
```

And separately, confirming why: a symlinked Node script reports the **real** directory, so
`path.resolve(__dirname, '..')` finds the checkout rather than the shim directory.

```
  __dirname      : <clone>/repo          <- real location
  process.argv[1]: <shimdir>/ttlink      <- symlink location
  process.cwd()  : /                     <- where it was invoked
```

## Quota data does not refresh on its own

`grep` for callers of the quota service in `backend/main.py` returns the two route handlers
and nothing else, and the file contains no scheduler, background task, or startup hook that
touches it.

---

# Risks

| Risk | Mitigation |
| --- | --- |
| nvm users lose the command after switching Node versions | Install a shim into a stable directory rather than npm's global bin |
| PowerShell execution policy blocks a `.ps1` shim | Ship a `.cmd` shim as well; it is what the bare name resolves to in both shells |
| Menu bar shows stale numbers | It calls `collect()` itself rather than reading the cache file |
| Menu bar and dashboard disagree | Both derive the worst window the same way and share one cache file |
| Thresholds drift across four surfaces | Python surfaces import from `harness_panels.base`; the frontend keeps its own pair, pinned by a test |
| `rumps` breaks a Linux or Windows install | macOS-only requirements file; the subcommand refuses to run off-platform |

# Acceptance criteria

1. `tokentelemetry` runs from any directory on macOS, Linux, PowerShell, and `cmd.exe`,
   with every existing flag behaving as it does today.
2. Running `dashboard` when one is already serving opens the browser instead of failing.
3. `status` and `stop` work without starting anything.
4. The menu bar reports correct numbers with the backend stopped, and its worst window
   matches the dashboard's sidebar gauge.
5. `menubar` off macOS prints one clear line and exits non-zero.
6. Menu bar logic is unit-tested without importing `rumps`.
