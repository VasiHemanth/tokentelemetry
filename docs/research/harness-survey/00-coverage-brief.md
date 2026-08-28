# TokenTelemetry — "already covered" brief (from origin/main, backend/main.py @ 1bb9f47)

TokenTelemetry is a local-first dashboard that scans coding-agent data dirs on the
user's machine (no network) and reports sessions, tokens, cost, power/CO2, projects,
subagent delegation, skills/MCP/plugins inventory, and per-agent summaries.

## Harness roots main.py ALREADY reads
CLAUDE_DIR=~/.claude, ~/.claude.json
CODEX_DIR=~/.codex (+ auth.json auth_mode, config.toml, plugins/cache/)
GEMINI_DIR=~/.gemini ; QWEN_DIR=~/.qwen ; VIBE_DIR=~/.vibe ; CURSOR_DIR=~/.cursor
OLLAMA_DIR=~/.ollama ; HF ~/.cache/huggingface
OPENCODE_DB=~/.local/share/opencode/opencode.db
HERMES_DIR=~/.hermes (state.db, profiles/, kanban.db, cron.db, SOUL.md, MEMORY.md, USER.md)
GROK_DIR=~/.grok/sessions/<enc-cwd>/<uuid>/{summary.json,events.jsonl,updates.jsonl,
  chat_history.jsonl,plan_mode.json,signals.json}
COPILOT_CLI_DIR=~/.copilot/session-state
ANTIGRAVITY: ~/.gemini/{antigravity,antigravity-cli,antigravity-ide}/brain
  + antigravity-cli/conversations/<uuid>.{db,pb} + history.jsonl
CLINE_DIR=~/.cline/data/db/sessions.db + VSCode globalStorage saoudrizwan.claude-dev
VSCODE/CURSOR workspaceStorage (Copilot chat store)
OMNIGENT: ~/.omnigent/chat.db (in-flight branch work)

## File literals already parsed
settings.json, settings.local.json, .mcp.json, mcp.json, CLAUDE.md, AGENTS.md,
transcript.jsonl, transcript_full.jsonl, unified.jsonl, session.jsonl,
session_index.jsonl, task.md, implementation_plan.md, walkthrough.md,
api_conversation_history.json, taskHistory.json, summary.json, events.jsonl,
updates.jsonl, chat_history.jsonl, plan_mode.json, signals.json, history.jsonl,
journal.jsonl, dsh_lifecycle.jsonl, config.toml, config.yaml, profile.yaml,
sessions.db, state.db, kanban.db, cron.db, opencode.db, jobs.json, logs.json,
projects.json, workspace.json, aliases.json, installed_plugins.json, plugin.json,
extensions.json, extension-enablement.json, gemini-extension.json,
qwen-extension.json, gateway_state.json, tokens_cache.json, SKILL.md, SOUL.md,
MEMORY.md, USER.md, .meta.json, .skills_prompt_snapshot.json

## Existing API surface (what the dashboard shows today)
/sessions /sessions/{id} /sessions/{id}/delegation /sessions/{id}/grok-forensics
/sessions/{id}/hermes-overlay /sessions/{id}/subagents/{aid}/trace /sessions/{id}/summary
/agents /projects /analytics /artifacts /budgets /pricing /local-runtime
/config/* (power, billing, retention, summarizer, telemetry, aliases, hidden, agent-features)
/notifications /remote-access /dsh/lifecycle /cache/status
HERMES ONLY has a rich per-agent sub-dashboard:
  /hermes/overview /hermes/sessions /hermes/kanban /hermes/memory /hermes/skills
  /hermes/tools /hermes/soul /hermes/telemetry /hermes/profiles /hermes/cron/*

## THE PRODUCT QUESTION YOU ARE ANSWERING
The user wants: click a coding agent on the dashboard -> see a rich per-agent panel
built from what THAT harness uniquely stores locally. Hermes already has this
(kanban/soul/memory/cron). Generalize it: what is each other harness's equivalent
of "jobs", "schedules", "background tasks", "memory", "todos", "checkpoints",
"plan artifacts", "MCP/tool inventory", "usage/quota state", "config/permissions"?

Known unmined leads (do not re-discover, but verify): Hermes kanban.db task-cost
join, Hermes request dumps, Hermes models_dev_cache pricing, Hermes rotated logs;
Omnigent chat.db.
