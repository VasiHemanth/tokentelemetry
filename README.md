# Token Telemetry (TokenTelemetry)

> **Local observability for AI coding agents AND autonomous agents — Claude Code, Codex, Gemini CLI, Cursor, Copilot, Qwen, OpenCode, Vibe, Antigravity, Grok Build, _and_ Nous Research's Hermes Agent.**

**Token Telemetry** (one word: **TokenTelemetry**) — free, open-source, 100% local.

> ☤ **New:** Dedicated **[Hermes Agent](#hermes-agent-autonomous-observability)** dashboard — autonomous-agent observability across 38 platforms (CLI, Telegram, Discord, cron, webhook, …).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Node.js](https://img.shields.io/badge/Node.js-18%2B-green)](https://nodejs.org)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://www.python.org)
[![Website](https://img.shields.io/badge/Website-tokentelemetry.com-blue)](https://tokentelemetry.com)
[![GitHub Stars](https://img.shields.io/github/stars/VasiHemanth/tokentelemetry?style=social)](https://github.com/VasiHemanth/tokentelemetry)

**TokenTelemetry** is a free, open-source, 100% local observability dashboard that tracks **token usage**, **LLM costs**, **tool calls**, **session traces**, and **reasoning steps** across all your AI coding agents — in one unified place. No signup. No cloud. No telemetry.

🌐 **Website & Docs:** [https://tokentelemetry.com](https://tokentelemetry.com)  
🖥️ **macOS/Linux:** `curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash`
🧰 **Windows:** `irm https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.ps1 | iex`
🐙 **GitHub:** [github.com/VasiHemanth/tokentelemetry](https://github.com/VasiHemanth/tokentelemetry)

---

## Why TokenTelemetry?

AI coding agents like Claude Code, Gemini CLI, and Codex are powerful — but they burn through tokens fast. **How many tokens did that refactor cost? Which agent is most efficient? What did it actually do?**

TokenTelemetry answers all of that — locally, instantly, for free.

| Problem                                                | TokenTelemetry Solution                     |
| ------------------------------------------------------ | ------------------------------------------- |
| "How much did that Claude Code session cost?"          | Real-time cost tracking per session/project |
| "What tools did my agent call?"                        | Full waterfall trace of every tool call     |
| "Which model is most token-efficient for my codebase?" | Per-model analytics & comparisons           |
| "Did my agent follow its plan?"                        | Plan-mode capture & display                 |
| "I use 3 different agents — unified view?"             | Multi-agent dashboard in one place          |

---

## Supported Agents

TokenTelemetry reads session logs from these agents automatically.

### Coding agents

| Agent                       | Status             |
| --------------------------- | ------------------ |
| **Claude Code** (Anthropic) | ✅ Fully supported |
| **Gemini CLI** (Google)     | ✅ Fully supported |
| **OpenAI Codex CLI**        | ✅ Fully supported |
| **Cursor**                  | ✅ Fully supported |
| **GitHub Copilot**          | ✅ Fully supported |
| **OpenCode**                | ✅ Fully supported |
| **Qwen**                    | ✅ Fully supported |
| **Vibe**                    | ✅ Fully supported |
| **Antigravity**             | ✅ Fully supported |
| **Grok Build** (xAI)        | ✅ Fully supported |

### Autonomous agents

| Agent                            | Status                                                                                  |
| -------------------------------- | --------------------------------------------------------------------------------------- |
| **Hermes Agent** (Nous Research) | ✅ [Fully supported with a dedicated dashboard](#hermes-agent-autonomous-observability) |

More agents added regularly. [Request support for your agent →](https://github.com/VasiHemanth/tokentelemetry/issues)

---

## Hermes Agent: autonomous observability

Hermes Agent isn't a coding agent — it runs across CLI, messaging platforms (Telegram, Discord, Slack, Feishu, …), scheduled jobs, and webhooks. It gets its own surface at **`/hermes`** with:

- **38 source platforms** — every value Hermes emits in `sessions.source`
- **Per-API-call latency + cache hit %** parsed from `agent.log`
- **Inline `delegate_task` subagent cards** with summary, tokens, duration
- **Skills + memory pages**, **cron health**, **gateway health**, **cost anomaly detection**
- **Provider-aware pricing** — same model priced correctly across direct / OpenRouter / Together / Fireworks

Run TokenTelemetry on the same host as Hermes — we read `$HERMES_HOME` (or `~/.hermes/` if unset) locally, no remote-DB mode yet.

### Hermes Dashboard plugin (`:9119` → `:3000`)

If you run Hermes's own web dashboard (`hermes dashboard`, port `9119`), install the plugin so TokenTelemetry shows up as a tab inside it — one port to remember, deep-link cards to every TT page.

**Standalone install** (recommended — uses Hermes's own plugin manager):

```bash
hermes plugins install VasiHemanth/tokentelemetry-hermes-plugin
hermes dashboard
```

**From this repo** (canonical source, useful if you're hacking on the plugin):

```bash
./scripts/install-hermes-plugin.sh
hermes dashboard
```

The launcher tab works for every TT page, not just `/hermes` — Analytics, Projects, and All Agents views all open from inside Hermes Dashboard. Pure-frontend, no extra backend, no network access beyond your local TT. See [`plugin/hermes-dashboard/README.md`](plugin/hermes-dashboard/README.md) for details.

---

## Features

- ☤ **Hermes Agent dashboard** — autonomous-agent observability at `/hermes` (38 source platforms, gateway health, cron jobs, skills, memory, subagent cards — see the [section above](#hermes-agent-autonomous-observability))
- 📊 **Token Usage Dashboard** — real-time tokens in/out per agent, model, and project
- 💰 **Cost Tracking** — see exact LLM API costs per session and cumulative over time
- 🔍 **Session Traces** — waterfall view of prompts, reasoning chains, tool calls, and responses
- 🛠️ **Tool Call Analytics** — which tools your agents call most, success/failure rates
- 📁 **Per-Project Insights** — heatmap, activity timeline, agent leaderboard per codebase
- 🧠 **Plan Capture** — view plan-mode outputs from Claude Code and other agents
- 📈 **Model Analytics** — compare GPT-5.4 vs Claude 4.6 Sonnet vs Gemini 3.1 Flash efficiency
- ⚡ **Efficiency Scoring** — 0–100 score per session measuring how productively tokens were spent *(Intelligence Layer)*
- 🦨 **AI Smell Detection** — rule-based warnings for context rot, loop traps, tool thrash, high error rate, and massive sessions *(Intelligence Layer)*
- 🔥 **Burn Rate Forecasting** — daily token trends projected to month-end with plan limit alerts *(Intelligence Layer)*
- 🧬 **Prompt DNA** — correlates prompt structure (file refs, length, vagueness, task type) against efficiency scores to show what makes sessions good or bad *(Intelligence Layer)*
- 🏆 **Multi-Model Comparison** — side-by-side efficiency ranking of every model you've used, with avg/p75/best scores and task-type filter pills *(Intelligence Layer)*
- 🔒 **100% Local** — all data stays on your machine, zero cloud dependency
- ⚡ **Zero Config** — auto-detects agents from their default log locations
- 🆓 **Free & Open Source** — MIT licensed, forever free

---

## Intelligence Layer

> **Branch:** `tokentelemetry-intelligence-layer` — pure computation on top of existing session data. No new required dependencies.

Three analytical capabilities that turn raw token counts into actionable insight:

---

### ⚡ Agent Efficiency Score

Every session now carries a **0–100 score** measuring how productively tokens were spent:

```
score = output_ratio × error_penalty × turn_penalty × 100
```

| Factor | Formula | Rationale |
|--------|---------|-----------|
| `output_ratio` | output tokens ÷ total tokens | More output per token = more productive work |
| `error_penalty` | 1 ÷ (1 + errors × 0.15) | Tool failures waste tokens |
| `turn_penalty` | 1 ÷ (1 + log(turns) × 0.18) | Fewer turns = clearer prompts |

**Labels:** `good` (≥ 70) · `fair` (40–69) · `poor` (< 40)

**In the UI:** a colour-coded `⚡ Score` badge appears on every row in the Recent Activity table — green, amber, or red at a glance.

**API:**
```
GET /sessions          → each session now includes: efficiency, efficiency_label
GET /efficiency        → all sessions sorted best-first (great for leaderboards)
GET /efficiency?project=/path/to/repo   → filtered by project
```

---

### 🦨 AI Smell Detection

Rule-based detection of **5 anti-patterns** that indicate wasted tokens or a stuck agent:

| Smell | Trigger | Severity |
|-------|---------|----------|
| `context_rot` | Session > 200 turns | warning (> 400 turns → critical) |
| `loop_trap` | Same tool called with identical input ≥ 8 times in a row | critical |
| `tool_thrash` | Same file read ≥ 25 times across a session | warning |
| `high_error_rate` | Errors > 20% of turns | warning (> 40% → critical) |
| `massive_session` | Total tokens > 2 M | warning (> 5 M → critical) |

Each smell is a structured dict `{ type, title, detail, severity }` — the `detail` field explains what happened and what to do about it.

**In the UI:** an `⚠` icon appears on session rows that have at least one smell — orange for warnings, red for critical. Hovering shows the count and worst severity.

**API:**
```
GET /smells             → sessions with at least one smell (all projects)
GET /smells?project=/path/to/repo   → filtered by project
```

Each entry:
```json
{
  "session_id": "abc123",
  "agent": "claude",
  "project": "/Users/me/myapp",
  "timestamp": "2026-06-09T14:30:00Z",
  "efficiency": 42.3,
  "smells": [
    {
      "type": "context_rot",
      "title": "Context rot (247 turns)",
      "detail": "This session ran for 247 turns. Context quality typically degrades past 200 turns — consider breaking long tasks into focused sub-sessions.",
      "severity": "warning"
    }
  ]
}
```

---

### 🔥 Burn Rate Forecasting

Linear projection of your token consumption toward your subscription's monthly limit:

- **Daily buckets** — aggregates total tokens per calendar day over the last 60 days
- **7-day average** used for projection (recent pace, not historical average)
- **Trend detection** — compares last 7 days vs prior 7 days → `accelerating` / `steady` / `slowing`
- **Days-until-limit** — how many days at current pace before hitting your plan quota

**Supported plans:**

| Plan | Monthly token limit |
|------|-------------------|
| `claude_pro` | 500 M |
| `claude_max` | 2 B |
| `codex_plus` | 200 M |
| `copilot` | 100 M |
| `api_unlimited` | No limit |

**In the UI:** a **Burn Rate** card in the dashboard sidebar shows your daily rate, projected month-end total, a colour-coded progress bar (green → amber → red as you approach the limit), and an urgency alert when you're ≤ 7 days from hitting the cap.

**API:**
```
GET /forecast                       → forecast at default plan (claude_pro)
GET /forecast?plan=claude_max       → forecast against Claude Max 2B limit
```

Response:
```json
{
  "daily_avg_7d": 18500000,
  "daily_avg_30d": 14200000,
  "projected_month": 412000000,
  "used_this_month": 227000000,
  "days_until_limit": 14,
  "trend": "accelerating",
  "trend_pct": 30.2,
  "limit": 500000000,
  "plan": "claude_pro",
  "buckets_30d": { "2026-06-01": 15200000, "2026-06-02": 19400000, "..." : "..." }
}
```

---

### 🧬 Prompt DNA

Extracts **10 structural features** from each session's first message and computes Pearson correlation against efficiency scores, revealing which prompt habits make sessions succeed or fail.

**Features extracted per prompt:**

| Feature | Description |
|---------|-------------|
| `msg_length` | Character count |
| `word_count` | Approximate word count |
| `has_file_ref` | References a file path or @ mention |
| `has_code_block` | Contains a triple-backtick block |
| `has_markdown` | Uses `#` headers or `- / *` bullets |
| `has_numbered_steps` | Uses `1.` / `2.` numbered lists |
| `has_question` | Prompt ends with `?` |
| `is_vague` | < 60 chars, no file ref, no code |
| `is_detailed` | > 300 characters |
| `has_context_link` | References previous session / last time / continue |

**Task classification:** `fix` · `build` · `refactor` · `analyze` · `test` · `deploy` · `other` (regex-matched, first match wins).

**In the UI:** a **Prompt DNA** card in the right sidebar shows the top 2 positive and top 2 negative correlates with r-values and one-line insights, plus a mini bar chart breaking down average efficiency by task type.

**API:**
```
GET /insights/prompt-dna    → full correlation analysis over all sessions
```

Response:
```json
{
  "sessions_analysed": 14,
  "sessions_skipped": 24,
  "correlations": [
    {
      "feature": "is_vague",
      "label": "Vague / short prompt",
      "r": -0.871,
      "direction": "negative",
      "insight": "Sessions with 'vague / short prompt' score 53.6 pts lower on average (13.7 vs 67.3)."
    }
  ],
  "by_task_type": {
    "other":   { "avg_efficiency": 69.7, "count": 8 },
    "build":   { "avg_efficiency": 20.6, "count": 4 }
  },
  "top_positive": [...],
  "top_negative": [...]
}
```

---

### 🏆 Multi-Model Comparison

Side-by-side efficiency ranking of every model you've used, filterable by task type.

**Stats per model:**

| Stat | Description |
|------|-------------|
| `avg_efficiency` | Mean efficiency score across sessions |
| `median_efficiency` | Median (robust to outliers) |
| `p75_efficiency` | 75th percentile — typical good session for this model |
| `best_efficiency` | Highest single session score |
| `avg_tokens` | Average tokens per session |
| `task_breakdown` | Per-task-type count and avg efficiency |

**In the UI:** a full-width **Model comparison** section below the main grid shows ranked model rows with dual efficiency bars (avg + p75) and colour-coded task breakdown pills. Task type filter pills (All / build / refactor / analyze / other) refetch instantly.

**API:**
```
GET /insights/model-comparison                      → all task types
GET /insights/model-comparison?task_type=build      → build tasks only
GET /insights/model-comparison?task_type=refactor   → refactor tasks only
```

Response:
```json
{
  "task_type_filter": null,
  "models_compared": 3,
  "sessions_used": 13,
  "sessions_skipped": 25,
  "models": [
    {
      "model": "claude-sonnet-4-6",
      "agent": "claude",
      "session_count": 5,
      "avg_efficiency": 68.4,
      "median_efficiency": 73.6,
      "p75_efficiency": 76.6,
      "best_efficiency": 80.4,
      "total_tokens": 13258141,
      "avg_tokens": 2651628,
      "task_breakdown": {
        "other": { "count": 5, "avg_efficiency": 68.4 }
      }
    }
  ],
  "task_types_available": ["build", "refactor", "analyze", "other"]
}
```

---

### Implementation notes

All five features live in standalone Python modules — no changes to existing data collection or parsing logic:

| Module | Responsibility |
|--------|---------------|
| `backend/scoring.py` | Efficiency score computation |
| `backend/smells.py` | Smell rule evaluation |
| `backend/forecast.py` | Daily bucketing + linear projection |
| `backend/prompt_analysis.py` | Feature extraction + Pearson correlation |
| `backend/model_comparison.py` | Per-model efficiency stats + task breakdown |

**No new required dependencies.** Everything uses Python stdlib (`math`, `datetime`, `collections`, `re`). Ollama, scipy, numpy — none needed.

Smells and efficiency scores are computed in-memory after the session cache is built, so they add no I/O overhead. Forecast runs over the already-loaded session list.

---

## Quick Start

### Option 1: One-line installer (recommended)

**macOS / Linux:**

```bash
curl -fsSL https://tokentelemetry.com/install.sh | bash
```

**Windows (PowerShell):**

```powershell
irm https://tokentelemetry.com/install.ps1 | iex
```

### Option 2: Clone & run

```bash
git clone https://github.com/VasiHemanth/tokentelemetry.git
cd tokentelemetry
./start.sh        # macOS/Linux
# start.bat       # Windows
# node bin/cli.js # cross-platform
```

Then open: **http://localhost:3000**

---

## What You'll See

### Dashboard

Connected agents, recent activity feed, model distribution pie chart, token burn rate.

### Projects View

Per-project heatmap, tool usage breakdown, agent leaderboard, session timeline.

### Session Trace

Full waterfall: system prompt → reasoning → tool calls → responses → final output. See exactly what your agent was thinking.

### Analytics

Cumulative token & cost graphs per agent/model over time. Compare efficiency across models.

### Plans

Captured plan-mode outputs from Claude Code's `/plan` command and equivalent in other agents.

---

## Requirements

- **Node.js 18+**
- **Python 3.9+**
- **git**
- Any supported AI coding agent already installed (Claude Code, Gemini CLI, Codex, etc.)

---

## Configuration

TokenTelemetry stores lightweight state in `~/.tokentelemetry/`:

```
~/.tokentelemetry/
  aliases.json       # Rename/merge project folder paths
  hidden.json        # Hide specific projects from dashboard
  preferences.json   # App preferences (e.g. update check on/off)
  billing.json       # Per-agent billing-mode overrides
  power.json         # Local-model power & electricity settings
  VERSION            # Current version
```

All hand-editable JSON — no database, no config GUI needed.

### Choosing where data is stored

Prefer to keep your system drive clear, or isolate dev-tool state on a secondary
drive? Point TokenTelemetry's data directory anywhere:

- **Launcher flag** — `start.sh --data-dir /mnt/d/tt-data` (or `-d`). The folder
  is created on first write.
- **Environment** — set `TOKENTELEMETRY_DATA_DIR=/mnt/d/tt-data` before
  launching. Used verbatim — that exact folder becomes the store (no
  `.tokentelemetry` suffix appended). An explicit `--data-dir` flag wins over it.

> **Windows cmd.exe tip:** If using quotes around the path, avoid a trailing backslash (e.g. `--data-dir "D:\tt\"`) as `\"` escapes the quote in `cmd.exe`. Use forward slashes or omit the trailing slash instead.

Everything — aliases, hidden projects, preferences, billing/power overrides,
summaries cache, the update-check stamp — moves together, so a single setting
relocates *all* state. The default remains `~/.tokentelemetry/`.

### Update check

TokenTelemetry does **not** collect or transmit your logs, sessions, tokens, or
costs — those never leave your machine. The one outbound call it makes is an
**optional update check**: about once an hour the dashboard fetches the latest
version and curated release notes from GitHub, so you know when new features
land. It sends no usage data — only a version request, which (like any web
request) exposes your IP and the app name to GitHub.

Turn it off either way:

- **In the app** — Settings → *Updates & privacy* → toggle off *Check for updates*.
- **Via environment** — set `TT_NO_UPDATE_CHECK=1` before launching. This wins
  over the in-app toggle, so admins can enforce it (e.g. in air-gapped or
  egress-monitored environments).

---

## Remote Access

TokenTelemetry is **local-first** and binds to `127.0.0.1` by default so that your agent logs, prompts, and costs never leave the machine. Remote access is an opt-in feature with clear security boundaries (loopback is always exempt; non-loopback requests require a token).

### Direct remote / tailnet / LAN access

Use the built-in flags when you can reach the machine directly (tailnet, LAN, or a VPS with ports open):

```bash
./start.sh --host 0.0.0.0 \
  --allowed-origins your-laptop.tailnet.ts.net,192.168.1.42 \
  --port 3000 --api-port 8000
```

- `--host 0.0.0.0` (or a concrete IP) makes the backend listen on all interfaces.
- `--allowed-origins` configures CORS on the backend and allowed dev origins for Next.js.
- On a non-loopback `--host`, a random token is **auto-generated and printed once** (unless you pass `--auth-token` or `--insecure-no-auth`).
- The launcher prints a connect URL (`http://.../?token=...`) and the dashboard shows a "Connect a device" panel with a QR code.
- Your own browser on the server machine (loopback) never needs the token. Remote clients send it as `Authorization: Bearer <token>` (or `?token=...` for images and artifacts).

**Security note:** Only use `--insecure-no-auth` on a fully trusted private network. See the warning printed by the launcher and run `./start.sh --help` for the full flag reference and examples.

When you load the dashboard from the remote address (e.g. the Network URL printed by Next.js), the frontend automatically derives the backend URL from `window.location` + the API port, so everything just works.

### SSH tunnel access (VPS / "only SSH exposed" / no port changes)

This pattern is common when your agents (and their logs) run on a remote VPS or server and you only have SSH access, or you prefer to keep the dashboard bound to localhost on the remote side.

**On the remote machine** (where the agent logs live — this is required because TokenTelemetry reads files locally):

```bash
NEXT_PUBLIC_API_BASE=http://localhost:8000 ./start.sh
```

The `NEXT_PUBLIC_API_BASE` override tells the frontend to always talk to the backend at that address (instead of deriving it from the browser's window.location). It is inherited by the Next.js dev server.

**On your laptop:**

```bash
ssh -N -L 3000:127.0.0.1:3000 -L 8000:127.0.0.1:8000 user@remote-host
```

Then open **http://localhost:3000** on your laptop.

Both the UI and all data fetches are forwarded over the single SSH connection. The old single-port example (`-L 3000:...` only) produced a page skeleton with no data because the frontend would try to reach the backend on the laptop's localhost instead of the remote.

This method requires no firewall changes on the remote machine and reuses your existing SSH authentication.

---

## Project Structure

```
tokentelemetry/
  backend/        FastAPI app (Python) — reads agent logs, serves REST API
  frontend/       Next.js 16 dashboard — React UI
  bin/cli.js      Cross-platform launcher
  install.sh      One-line installer (macOS/Linux)
  install.ps1     One-line installer (Windows)
```

---

## FAQ

**Q: Does TokenTelemetry send any data to the cloud?**  
A: No usage data, ever. It reads log files from your filesystem and serves a local web dashboard — your logs, sessions, tokens, and costs never leave your machine. The only outbound call is an optional update check that fetches the latest version and release notes from GitHub (no usage data sent); disable it in Settings → *Updates & privacy* or with `TT_NO_UPDATE_CHECK=1`. See [Update check](#update-check).

**Q: How does it track Claude Code token usage?**  
A: Claude Code writes JSONL session logs to `~/.claude/`. TokenTelemetry watches those files and parses token counts, tool calls, and reasoning in real time.

**Q: Does it work with multiple agents at the same time?**  
A: Yes. It detects all supported agents and shows them in a unified dashboard. You can filter by agent, model, or project.

**Q: Is there a cost to use TokenTelemetry?**  
A: No. It is free and open-source under the MIT license.

**Q: How is TokenTelemetry different from Langfuse, LangSmith, or Helicone?**  
A: Those tools require you to instrument your code, create an account, and send data to their cloud. TokenTelemetry is 100% local, zero-config, and works by reading the log files your agents already write — no SDK, no API key, no cloud.

**Q: Can I monitor Gemini CLI token usage?**  
A: Yes. TokenTelemetry supports Gemini CLI and shows token counts, costs, and session traces for Google's Gemini models (Gemini 2.0 Flash, Gemini 1.5 Pro, etc.).

**Q: Does it support Cursor or GitHub Copilot?**  
A: Yes. Cursor and GitHub Copilot sessions are detected and tracked.

### Hermes Agent FAQ

**Q: Is there any other observability tool for Hermes Agent?**  
A: Not really. Hermes ships its own `/usage` + `/insights` and a bundled Langfuse plugin, but no third-party tool treats it as a first-class agent with a dedicated dashboard. Tracking: [`NousResearch/hermes-agent#6642`](https://github.com/NousResearch/hermes-agent/issues/6642).

**Q: Will it work for my Hermes bot on a VPS?**  
A: Yes — run TokenTelemetry on the same host (it reads local files). See the **[Remote Access](#remote-access)** section above for the two supported methods:

- Direct exposure with `--host 0.0.0.0` + token (recommended when the network allows it).
- SSH tunnel with the correct dual-port forward (`-L 3000:... -L 8000:...`) plus `NEXT_PUBLIC_API_BASE` on the remote (the previously documented single-port command produced a blank dashboard).

**Q: Is "Hermes Agent" the same as the Hermes-3 LLMs?**  
A: No. Hermes Agent is the [open-source agent framework](https://github.com/NousResearch/hermes-agent); Hermes-3 is a family of fine-tuned models. TokenTelemetry observes the agent — it can be running any model.

---

## Comparisons

| Feature             | TokenTelemetry | Langfuse | LangSmith | Helicone |
| ------------------- | -------------- | -------- | --------- | -------- |
| 100% Local          | ✅             | ❌       | ❌        | ❌       |
| Zero config         | ✅             | ❌       | ❌        | ❌       |
| No signup           | ✅             | ❌       | ❌        | ❌       |
| Claude Code support | ✅             | Manual   | Manual    | Manual   |
| Gemini CLI support  | ✅             | Manual   | Manual    | ❌       |
| Codex CLI support   | ✅             | Manual   | Manual    | Manual   |
| Free                | ✅             | Freemium | Freemium  | Freemium |
| Open Source         | ✅             | ✅       | ❌        | ❌       |

### Hermes Agent observability landscape

There's no other third-party tool built specifically for Hermes Agent.

| Option                              | Hermes-aware? | Local? | Dedicated UI? |
| ----------------------------------- | ------------- | ------ | ------------- |
| Hermes's own `/usage` + `/insights` | ✅            | ✅     | Aggregates only |
| Bundled Langfuse plugin             | ❌ generic    | Either | Langfuse-shaped |
| Manual `state.db` / `agent.log` parsing | DIY      | ✅     | Build it yourself |
| Langfuse / LangSmith / Helicone     | ❌ generic    | ❌     | LLM-shaped |
| **TokenTelemetry**                  | ✅            | ✅     | `/hermes` dashboard |

Know of another? [Open an issue](https://github.com/VasiHemanth/tokentelemetry/issues) and we'll update this.

---

## Use Cases

- **Hermes Agent operators** running a Telegram / Discord / cron bot on a VPS — see costs per platform, gateway health, cron-run history, skills + memory state, all in one place
- **Individual developers** who want to understand how much their AI coding sessions cost
- **Teams** comparing Claude Code vs Gemini CLI vs Codex efficiency
- **Researchers** studying LLM agent behavior, tool call patterns, and reasoning chains
- **Engineering managers** tracking AI tooling ROI across projects
- **Prompt engineers** optimizing prompts by seeing exact token breakdowns

---

## Troubleshooting

**Port conflicts:** Check/kill processes on ports 3000 and 8000.  
**Python not found:** Install Python 3.9+ and ensure it's in your PATH.  
**No sessions showing:** Run an agent (Claude Code, Gemini CLI, etc.) first — TokenTelemetry needs existing log files.  
**Windows issues:** Run PowerShell as Administrator for the installer.

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

```bash
git clone https://github.com/VasiHemanth/tokentelemetry.git
cd tokentelemetry
# Make your changes
git checkout -b feat/your-feature
git commit -m "feat: your feature"
git push origin feat/your-feature
# Open a Pull Request
```

Want to add support for a new agent? [Open an issue](https://github.com/VasiHemanth/tokentelemetry/issues) with the agent name and log format.

---

## Related Projects & Keywords

`claude-code token usage` · `gemini cli cost tracking` · `codex token monitor` · `AI agent observability` · `LLM token dashboard` · `coding agent analytics` · `local LLM monitoring` · `token cost calculator` · `AI coding tool metrics` · `claude code session viewer` · `openai codex usage` · `cursor ide analytics` · `github copilot usage tracker` · `LLM observability tool` · `AI agent telemetry` · `token usage dashboard open source`

---

## License

[MIT](LICENSE) © 2024 [Hemanth Vasi](https://github.com/VasiHemanth)

---

## Author

**Hemanth Vasi**  
🌐 [tokentelemetry.com](https://tokentelemetry.com)  
🐙 [github.com/VasiHemanth](https://github.com/VasiHemanth)  
🐦 [@VasiHemanth on X](https://twitter.com/VasiHemanth)  
💼 [LinkedIn](https://www.linkedin.com/in/vasi-hemanth/)

## Feedback

Have an idea, found a bug, or just want to share how you're using TokenTelemetry? Two ways in:

- 💬 **[GitHub Discussions](https://github.com/VasiHemanth/tokentelemetry/discussions)** — ideas, Q&A, show-and-tell
- 🐛 **[Issues](https://github.com/VasiHemanth/tokentelemetry/issues)** — bugs and concrete feature requests

There's also a feedback button inside the app (bottom-right of every page).

---

_If you find TokenTelemetry useful, please ⭐ star this repo — it helps others discover it!_
