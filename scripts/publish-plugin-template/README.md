# TokenTelemetry — Hermes Dashboard Plugin

> A launcher tab inside [Hermes Agent](https://github.com/NousResearch/hermes-agent)'s web dashboard for **[TokenTelemetry](https://tokentelemetry.com)** — local observability for **Hermes Agent AND 9 coding agents** (Claude Code, OpenAI Codex, Gemini CLI, Cursor, GitHub Copilot, Qwen, OpenCode, Vibe, Antigravity).

> ℹ️ This repo is **auto-generated** from the canonical source in [`VasiHemanth/tokentelemetry`](https://github.com/VasiHemanth/tokentelemetry). File issues and PRs upstream.

## What this plugin does

Registers a `TokenTelemetry` tab in your Hermes Dashboard sidebar. Deep-link cards open TT pages in a new browser tab — one port to remember (`:9119`), no context-switching to `:3000`.

Pages reachable from the launcher:

- `/hermes` — overview (sessions, sources, models, cron health)
- `/hermes/skills` — loaded skills with platform conditions
- `/hermes/memory` — `MEMORY.md` and `USER.md` with progress bars
- `/analytics` — tokens, cost, trends **across all agents** (not just Hermes)
- `/projects` — per-project rollups, all agents combined
- `/` — connected agents (coding + autonomous)

## Install

### Prereq: install TokenTelemetry itself

The plugin is a **launcher, not the engine**. You need TokenTelemetry running:

```bash
# macOS / Linux
curl -fsSL https://tokentelemetry.com/install.sh | bash

# Windows
irm https://tokentelemetry.com/install.ps1 | iex
```

Or clone the repo: <https://github.com/VasiHemanth/tokentelemetry>

### Install the plugin

```bash
hermes plugins install VasiHemanth/tokentelemetry-hermes-plugin
hermes dashboard
```

Then open `http://127.0.0.1:9119` and click **TokenTelemetry** in the sidebar.

## What TokenTelemetry covers (so this plugin earns its keep)

TokenTelemetry isn't a Hermes-only tool. It tracks every AI agent you use:

| Agent | What TT shows |
|---|---|
| **Hermes Agent** | Dedicated `/hermes` dashboard — 38 source platforms, gateway health, cron jobs, skills + memory, subagent cards, per-API-call latency |
| Claude Code | Sessions, tool calls, plan-mode capture, costs |
| OpenAI Codex CLI | Sessions, tool calls, costs |
| Gemini CLI | Sessions, costs, tool calls |
| Cursor | Session activity |
| GitHub Copilot | Token / cost tracking |
| Qwen CLI | Sessions, costs |
| OpenCode | Sessions, costs |
| Vibe | Sessions |
| Antigravity | Sessions |

Plus a unified `/analytics` view across all of them.

## Privacy

The plugin is pure-frontend. It reads no Hermes data directly, makes no network requests beyond your local TokenTelemetry instance, and ships no telemetry. Your data never leaves your machine.

## License

MIT — see [LICENSE](LICENSE).

## Links

- **TokenTelemetry homepage**: <https://tokentelemetry.com>
- **TokenTelemetry source**: <https://github.com/VasiHemanth/tokentelemetry>
- **Hermes Agent**: <https://github.com/NousResearch/hermes-agent>

## Feedback

All conversations happen on the canonical repo:

- 💬 **Discussions** (ideas, Q&A, show-and-tell): <https://github.com/VasiHemanth/tokentelemetry/discussions>
- 🐛 **Issues** (bugs, concrete feature requests): <https://github.com/VasiHemanth/tokentelemetry/issues>

## Author

**Hemanth Vasi** · 🐦 [@VasiHemanth](https://twitter.com/VasiHemanth) · 💼 [LinkedIn](https://www.linkedin.com/in/vasi-hemanth/)
