# TokenTelemetry

> **Local token + cost monitoring dashboard for AI coding agents — Claude Code, Gemini CLI, Codex, Cursor, GitHub Copilot, OpenCode, and more.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Node.js](https://img.shields.io/badge/Node.js-18%2B-green)](https://nodejs.org)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://www.python.org)
[![Website](https://img.shields.io/badge/Website-tokentelemetry.com-blue)](https://tokentelemetry.com)
[![GitHub Stars](https://img.shields.io/github/stars/VasiHemanth/tokentelemetry?style=social)](https://github.com/VasiHemanth/tokentelemetry)

**TokenTelemetry** is a free, open-source, 100% local observability dashboard that tracks **token usage**, **LLM costs**, **tool calls**, **session traces**, and **reasoning steps** across all your AI coding agents — in one unified place. No signup. No cloud. No telemetry.

🌐 **Website & Docs:** [https://tokentelemetry.com](https://tokentelemetry.com)  
📦 **npm:** `npx tokentelemetry`  
🐙 **GitHub:** [github.com/VasiHemanth/tokentelemetry](https://github.com/VasiHemanth/tokentelemetry)

---

## Why TokenTelemetry?

AI coding agents like Claude Code, Gemini CLI, and Codex are powerful — but they burn through tokens fast. **How many tokens did that refactor cost? Which agent is most efficient? What did it actually do?**

TokenTelemetry answers all of that — locally, instantly, for free.

| Problem | TokenTelemetry Solution |
|---|---|
| "How much did that Claude Code session cost?" | Real-time cost tracking per session/project |
| "What tools did my agent call?" | Full waterfall trace of every tool call |
| "Which model is most token-efficient for my codebase?" | Per-model analytics & comparisons |
| "Did my agent follow its plan?" | Plan-mode capture & display |
| "I use 3 different agents — unified view?" | Multi-agent dashboard in one place |

---

## Supported AI Coding Agents

TokenTelemetry reads session logs from these agents automatically:

| Agent | Status |
|---|---|
| **Claude Code** (Anthropic) | ✅ Fully supported |
| **Gemini CLI** (Google) | ✅ Fully supported |
| **OpenAI Codex CLI** | ✅ Fully supported |
| **Cursor** | ✅ Fully supported |
| **GitHub Copilot** | ✅ Fully supported |
| **OpenCode** | ✅ Fully supported |
| **Qwen** | ✅ Fully supported |
| **Vibe** | ✅ Fully supported |
| **Antigravity** | ✅ Fully supported |

More agents added regularly. [Request support for your agent →](https://github.com/VasiHemanth/tokentelemetry/issues)

---

## Features

- 📊 **Token Usage Dashboard** — real-time tokens in/out per agent, model, and project
- 💰 **Cost Tracking** — see exact LLM API costs per session and cumulative over time
- 🔍 **Session Traces** — waterfall view of prompts, reasoning chains, tool calls, and responses
- 🛠️ **Tool Call Analytics** — which tools your agents call most, success/failure rates
- 📁 **Per-Project Insights** — heatmap, activity timeline, agent leaderboard per codebase
- 🧠 **Plan Capture** — view plan-mode outputs from Claude Code and other agents
- 📈 **Model Analytics** — compare GPT-4o vs Claude 3.5 Sonnet vs Gemini 2.0 Flash efficiency
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

### Option 3: npx (no install)

```bash
npx tokentelemetry
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
  aliases.json    # Rename/merge project folder paths
  hidden.json     # Hide specific projects from dashboard
  VERSION         # Current version
```

All hand-editable JSON — no database, no config GUI needed.

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
A: No. 100% local. It reads log files from your filesystem and serves a local web dashboard. Nothing leaves your machine.

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

---

## Comparisons

| Feature | TokenTelemetry | Langfuse | LangSmith | Helicone |
|---|---|---|---|---|
| 100% Local | ✅ | ❌ | ❌ | ❌ |
| Zero config | ✅ | ❌ | ❌ | ❌ |
| No signup | ✅ | ❌ | ❌ | ❌ |
| Claude Code support | ✅ | Manual | Manual | Manual |
| Gemini CLI support | ✅ | Manual | Manual | ❌ |
| Codex CLI support | ✅ | Manual | Manual | Manual |
| Free | ✅ | Freemium | Freemium | Freemium |
| Open Source | ✅ | ✅ | ❌ | ❌ |

---

## Use Cases

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
💼 [LinkedIn](https://www.linkedin.com/in/vasi-hemanth/)

---

*If you find TokenTelemetry useful, please ⭐ star this repo — it helps others discover it!*
