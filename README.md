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
- 🔒 **100% Local** — all data stays on your machine, zero cloud dependency
- ⚡ **Zero Config** — auto-detects agents from their default log locations
- 🆓 **Free & Open Source** — MIT licensed, forever free

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
  VERSION            # Current version
```

All hand-editable JSON — no database, no config GUI needed.

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
A: Yes — run TokenTelemetry on the same host (it reads local files), then `ssh -L 3000:localhost:3000 your-vps` to view from your laptop.

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
