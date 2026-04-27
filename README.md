# tokentelemetry

A local, read-only observability dashboard for your coding agents.

It reads session logs from **Claude Code**, **Codex**, **Gemini CLI**, **Antigravity**, **Qwen**, **Vibe**, **Cursor**, **GitHub Copilot**, and **OpenCode** — then shows you tokens, traces, tool usage, plans, and per-project activity in one place.

Runs 100% on your machine. No signup, no telemetry, no cloud.

🌐 **Website:** https://tokentelemetry.com

---

## Requirements

- **Node.js 18+**
- **Python 3.9+**
- **git**

Any one or more of the supported agents already in use (otherwise there's nothing to watch).

---

## Quick start

### Clone

```bash
git clone https://github.com/VasiHemanth/tokentelemetry.git
cd tokentelemetry
```

### Run

One command, both services, browser opens automatically:

**macOS / Linux**
```bash
./start.sh
```

**Windows**
```cmd
start.bat
```

Or directly:
```bash
node bin/cli.js
```

The first run creates a Python virtualenv, installs backend + frontend dependencies, then launches:

- Dashboard → http://localhost:3000
- API → http://127.0.0.1:8000

Press `Ctrl+C` to stop both.

### Running again (after first install)

The one-line installer clones the repo into a `tokentelemetry/` folder. Next time you want the dashboard, just re-enter that folder and start it:

**macOS / Linux**
```bash
cd tokentelemetry
./start.sh
```

**Windows**
```powershell
cd tokentelemetry
start.bat
```

Or cross-platform:
```bash
node bin/cli.js
```

> **Tip:** Press `Ctrl+C` to stop both the backend and frontend at any time.

---

## What you'll see

- **Dashboard** — connected agents, recent activity, model distribution.
- **Projects** — one card per working directory; click in for per-project insights (heatmap, tool usage, agent leaderboard, plans).
- **Session trace** — per-session waterfall with user prompts, reasoning, tool calls, and assistant responses. Markdown / raw toggle on every response.
- **Analytics** — cumulative tokens per agent, per model, over time.
- **Plans** — captured plan-mode outputs from every agent that supports it.

---

## Configuration

A single hidden directory holds all TokenTelemetry state:

```
~/.tokentelemetry/
  aliases.json   # merge two project paths into one
  hidden.json    # projects you've hidden from the dashboard
  VERSION
```

Everything in there is hand-editable JSON. Nothing inside `~/.claude`, `~/.codex`, `~/.gemini`, etc. is ever modified.

### Example: collapse a renamed folder

If you renamed `~/Documents/old-name` to `~/Documents/new-name`, old sessions still point at the old path. Merge them:

```json
{
  "/Users/you/Documents/old-name": "/Users/you/Documents/new-name"
}
```

Restart the backend (or hit `POST /cache/invalidate`). Both sets of sessions now group under one project.

---

## Troubleshooting

**Port 3000 or 8000 already in use.**
`bin/cli.js` fails fast with the port number. Stop the other process and retry.
- macOS / Linux: `lsof -iTCP:3000 -sTCP:LISTEN`
- Windows: `netstat -ano | findstr :3000`

**Python version issues.**
The CLI probes `python3` then `python`. If both fail, install Python 3.9+ from https://www.python.org/downloads/.

**Dashboard shows no sessions.**
`GET http://127.0.0.1:8000/sessions` — if that returns `[]`, none of the supported agent log directories exist on your machine yet. Run any agent once, then refresh.

---

## Project layout

```
backend/         FastAPI app — scans agent log dirs, serves /sessions, /projects, /analytics
  main.py
  harness_config.py
  requirements.txt
frontend/        Next.js 16 dashboard
bin/cli.js       Single cross-platform launcher
install.sh       One-line installer shim
start.sh         POSIX launcher shim
start.bat        Windows launcher shim
```

All three launcher scripts delegate to `bin/cli.js`. Cross-platform bugs have exactly one place to live.

---

## License

MIT.

---

## Author

**Hemanth Vasi** — [LinkedIn](https://www.linkedin.com/in/vasi-hemanth/)
