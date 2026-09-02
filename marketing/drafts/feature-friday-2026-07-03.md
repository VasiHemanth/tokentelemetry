# Feature Friday — 2026-07-03

> Based on: `git log origin/main --since="7 days ago"` | UPDATE.json (no entry yet for this week's feat — flagged below)
> Shipped this week: 1 feat: commit, 9 docs/chore commits (screenshots, pricing data refresh, wiki/gitignore housekeeping)

**Reviewer note:** Only one user-facing feature shipped this week (Cline + SmallCode agent support, commit `90f7ad0`, merged via PR #120). Everything else was docs polish (config-page screenshots, llms.txt/sitemap sync) or a routine `pricing_data.json` refresh from models.dev — not announcement-worthy on their own. This is a lighter Feature Friday than usual; the thread below is sized accordingly (4 tweets, not 6). UPDATE.json does not yet have a 2026-07-01/02 entry for this feature — worth adding before or alongside this post so the in-app banner matches.

---

## X / Twitter Thread

**Tweet 1 — Hook**

TokenTelemetry now tracks 12 coding agents, up from 10.

This week: Cline and SmallCode join the list — full token, cost, and trace visibility, zero config. 🧵

*[Suggested visual: the Supported Agents docs table with Cline + SmallCode rows highlighted, or a session list showing a Cline session next to a Claude Code one]*

---

**Tweet 2 — Cline**

New: Cline support.

TokenTelemetry reads both the Cline CLI's SQLite store and the VS Code extension's task history, and de-dupes sessions that show up in both — so you don't get double-counted totals if you use Cline from the terminal and the editor.

Subagent spend is tracked separately too, so a parent task's cost isn't inflated by its children's tokens.

*[Suggested visual: a Cline session detail page showing tokens in/out, cache read/write, cost, and model]*

---

**Tweet 3 — SmallCode**

New: SmallCode support.

SmallCode writes its traces per-project (`.smallcode/traces/`) instead of one global folder. TokenTelemetry now picks those up automatically from the project paths it already watches — plus a `TT_SMALLCODE_ROOTS` env var if your traces live somewhere unusual.

*[Suggested visual: a SmallCode session showing prompt/completion tokens and tool-call steps]*

---

**Tweet 4 — Close + install**

If you're mixing agents — Claude Code, Cline, SmallCode, whatever — TokenTelemetry gives you one cost view across all of them. Local, zero-config, free, open source.

```
curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash
```

GitHub → https://github.com/VasiHemanth/tokentelemetry

---

## Discord #announcements Post

**TokenTelemetry — Feature Friday update (2026-07-03)**

Quieter week — one feature shipped, plus a batch of docs cleanup:

**🧩 Cline + SmallCode now supported**
TokenTelemetry tracks 12 coding agents now, up from 10.

- **Cline**: reads both the CLI's SQLite store (`~/.cline/data/db/sessions.db`) and the VS Code extension's `taskHistory.json`, de-duplicating sessions that appear in both. Subagent costs are tracked separately from the parent, so delegation doesn't inflate totals.
- **SmallCode**: discovers `.smallcode/traces/` under your project directories automatically (or set `TT_SMALLCODE_ROOTS` for non-standard locations). Captures prompt/completion tokens, model, and tool-call timing.

Full docs: https://github.com/VasiHemanth/tokentelemetry (see `website/content/docs/supported-agents.mdx`)

**Also this week:** refreshed model pricing data from models.dev, and added screenshots to the summarizer/privacy/history-retention config docs — no behavior changes.

---

Install / update:
```
curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash
```

Full changelog: https://github.com/VasiHemanth/tokentelemetry/commits/main

---

## LinkedIn Post

**TokenTelemetry now covers 12 coding agents**

If your team is standardized on one AI coding agent, cost tracking is easy. If you're not — and increasingly, engineers are mixing Claude Code, Cline, Codex, and others depending on the task — getting one accurate cost picture across all of them is the actual problem.

This week TokenTelemetry added support for two more: **Cline** and **SmallCode**, bringing the total to 12 tracked agents (plus the Hermes autonomous agent).

Cline support reads sessions from both its CLI (SQLite-backed) and its VS Code extension (JSON task history), reconciling the two so a session used from both surfaces doesn't get counted twice. It also separates subagent spend from parent spend, so delegation-heavy workflows still show an accurate cost breakdown instead of an inflated parent total.

SmallCode writes its session traces per-project rather than to a global directory, so TokenTelemetry now discovers them automatically wherever your projects live (with an environment variable escape hatch for unusual setups).

Net effect for teams: whichever agent an engineer reaches for, the cost shows up in the same dashboard, in the same units, next to everything else — no manual reconciliation across five different agents' own usage pages.

TokenTelemetry is open source, 100% local, and installs in one line. No account, no cloud, nothing leaves the machine.

```
curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash
```

→ https://github.com/VasiHemanth/tokentelemetry
