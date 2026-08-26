# Coding-harness data survey

A store-by-store map of every coding-agent data directory on a developer machine,
graded against what `backend/main.py` already reads (as of `origin/main` @ `1bb9f47`).

The question behind it: when a user clicks a coding agent on the TokenTelemetry
dashboard, what can we show them about that agent specifically? Hermes already has
a rich sub-dashboard (`/hermes/kanban`, `/hermes/soul`, `/hermes/memory`,
`/hermes/cron/*`). No other agent does. This survey is the input to generalising it.

Published as an artifact: https://claude.ai/code/artifact/01fc2766-890d-4ad5-a6fc-47ea0f2431e6

## Files

| File | Covers |
|---|---|
| `00-coverage-brief.md` | What main.py already reads — the baseline every finding is graded against |
| `harness-claude.md` | `~/.claude`, `~/.claude.json`, `~/.claudecode` |
| `harness-codex-copilot-cline.md` | `~/.codex`, `~/.copilot`, `~/.cline` |
| `harness-gemini-antigravity.md` | `~/.gemini` + all Antigravity surfaces, plus OpenCode / Hermes / Omnigent |
| `harness-grok-qwen-vibe-openclaw.md` | `~/.grok`, `~/.qwen`, `~/.vibe`, `~/.openclaw` |
| `harness-cursor-vscode.md` | `~/.cursor`, Cursor IDE app store, VS Code, IDE-fork sweep |
| `harness-longtail.md` | `.pi`, `.prime`, `.dsh`, `.kimi`, `.reins`, `.agents`, `.headroom`, `.browseros`, `.promptfoo`, `.mcp-auth` |
| `harness-runtimes.md` | `~/.ollama`, `~/.lmstudio`, `~/.cache/huggingface`, `~/.tokentelemetry` |

Each file follows one template: directory map, store inventory table with a
NEW / PARTIAL / COVERED grade, schemas with values elided, dashboard candidates
ranked by value × ease, cross-harness parallels, and gotchas.

## Method

Eight parallel surveys, each given the coverage brief plus two hard constraints:

1. **Never read credential values.** These directories hold live OAuth tokens,
   API keys, and an SSH private key. Report key names and file existence only.
   Never quote user prompts, page DOM, or file snapshots.
2. **Cap the traversal.** `~/.ollama` is 149 GB, `~/.lmstudio` 18 GB,
   `~/.hermes` 156k files, `~/.claude` 182k files. `du -sh dir/*` before
   descending; hard-exclude blob and weight stores.

Findings were graded against a grep of the harness constants, file literals, and
API routes in `backend/main.py`, so "NEW" means genuinely unread rather than
merely undocumented.

## Headline results

- **20 harnesses** found. All 17 agents in `website/content/docs/supported-agents.mdx`
  are already scanned for sessions — including `pi`, `prime` and `dsh`, which are
  registered in `frontend/src/lib/agents.ts`. What is unmined for those three is their
  *config and side stores*, not the agents themselves.
- **150 stores graded NEW.** Derived by counting NEW-graded rows in the store-inventory
  tables: `grep -cE '^\| .*NEW'` over the seven survey files gives
  14 + 17 + 18 + 0 + 41 + 15 + 45. The gemini/antigravity file records its findings in
  prose rather than a table, so the true figure is somewhat higher. The highest-value
  ones are listed in the artifact's "Top 12 finds".
- **Three corrections to existing assumptions:**
  - `~/.opencode` contains no user data at all (install dir); data is in
    `~/.local/share/opencode/`.
  - `~/.vibe` is Mistral's Vibe CLI, not vibe-kanban.
  - `~/.antigravity` and `~/.antigravity-ide` (1.1 GB) are VS Code extension
    folders, not agent data. A third real Antigravity store exists at
    `~/Library/Application Support/Antigravity` and has not been surveyed.
- **Two independent cost oracles** exist on disk for validating TT's own maths:
  Hermes `session_model_usage.actual_cost_usd` and Copilot
  `assistant_usage_events.total_nano_aiu`.

## Scope for the build

Only the 17 agents in `website/content/docs/supported-agents.mdx` are in scope for
per-agent panels. Omnigent, Kimi, OpenClaw, BrowserOS, promptfoo, reins and headroom are
surveyed here but out of scope — the findings stay for later. Ollama and LM Studio get
no agent tile; their findings enrich the existing `/local-models` page.

UI mockup: https://claude.ai/code/artifact/7f2c624c-f009-461d-8390-b16988e3b56b

### Two in-scope agents surveyed after the fact

- **Muse** — `~/.local/share/muse` (2.6 MB). `session-index.db` carries a rich
  `sessions` table: `layout, workspace_root, workspace_key, provider_id, model_id,
  git_branch, title, first_user_prompt, prompt_count, status, status_rank,
  source_fingerprint, latest_segment_terminated`. Plus `model-catalog/`,
  `feature-config/`, `skills/bundled/`, `plugins/cache/`, `tui-history.jsonl`.
- **SmallCode** — project-local, not in `$HOME`:
  `<repo>/.smallcode/traces/<name>-<hash>.json`.

## Caveats

Single-machine snapshot, 2026-08-27. Several schemas are real but unpopulated here
(Cursor `scored_commits`, Copilot `checkpoints`, Codex `thread_goals`,
BrowserOS tables) — a scanner must treat "installed, zero rows" as its own state,
distinct from "not installed". Usage-dependent stores reflect this user's habits,
not the products' capabilities.
