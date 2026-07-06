---
type: Analysis
status: proposed
title: Multi-harness session mining for the plugin
description: How to extend the plugin's session_scan beyond Claude Code to every harness TokenTelemetry parses, with a per-harness feasibility matrix and three build options.
tags: [plugin, session-scan, harnesses, brain-compile, session-miner]
timestamp: 2026-07-06
resource: backend/main.py
---

# Multi-harness session mining for the plugin

Saved from a maintainer chat, 2026-07-06. The plugin's `session_scan.py` only
mines Claude Code sessions, while TokenTelemetry itself parses ~13 agent
sources. This analysis maps the gap and ranks the ways to close it.

## Current state

`tokentelemetry-plugin/scripts/session_scan.py` is Claude-only by
construction: the projects root is hardcoded to `~/.claude/projects`, the
event shape assumed is Claude's JSONL (`message.content[].tool_use`,
`message.usage`), and `--harness` literally rejects any value but `claude`
("other harnesses are behind a future flag per design"). Its consumers are
the `session-miner` subagent (brain-compile topic seeding) and skillsmith's
structural mining. Its privacy boundary: structural signals only — tool
counts, file paths from tool inputs, error flags, loop signatures, token
totals; never message text, never Bash command strings.

## What TokenTelemetry already knows (backend/main.py)

All parsing lives in `_scan_sessions_sync` (~1,300 lines) plus per-agent
detail parsers (~900 lines). Per harness, the three facts that decide
minability: where sessions live, how a session is tied to a project, and
whether the log carries tool-level file paths.

| harness | store | project attribution | mineable signals |
|---|---|---|---|
| claude | `~/.claude/projects/<enc>/*.jsonl` | encoded dir + `cwd` | full (done today) |
| codex | `~/.codex/sessions/**/rollout-*.jsonl` | `cwd` in rollout meta | tokens + tool mix; path signals sparse (tools are shell commands, whose strings the privacy rule excludes) |
| qwen | `~/.qwen/projects/**/chats/*.jsonl` | per-project tree | tool calls present; layout closest to Claude's |
| opencode | SQLite `session`/`message`/`part` | `session.directory` column | full (`part` rows typed `tool`) |
| antigravity | `~/.gemini/antigravity/brain/` + `antigravity-cli/conversations/<id>.db` | brain metadata / CLI db | full via the CLI SQLite (richer than brain markdown) |
| cline | `~/.cline/data/db/sessions.db` + VS Code globalStorage JSON | db fields | tool calls present |
| smallcode | `<project>/.smallcode/traces/*.json` | project-local by definition | full (`steps[]` with `tool_call`) |
| copilot-cli | `~/.copilot/session-state/<id>/events.jsonl` | session-state metadata | tool events (`toolInvocation`) |
| grok | `~/.grok/sessions/<id>/` (events + chat history) | session metadata | `tool_calls` in chat history |
| vibe | `~/.vibe/logs/session/*.json` | file metadata | messages with roles; moderate |
| hermes | `~/.hermes` SQLite (pre-aggregated tokens) | db fields | tokens reliable; `tool_calls` JSON in messages |
| cursor | `~/.cursor/projects/**/agent-transcripts/<sid>/<sid>.jsonl` | per-project tree | transcripts exist but no usage data; paths-only at best |
| gemini | `~/.gemini/tmp/<sha256(cwd)>/chats/*.json` | sha256 reverse map | legacy — CLI discontinued 2026-06-18; skip |

Omnigent is planned for TT but not yet in `main.py`; when it lands, the same
question recurs (read-only `~/.omnigent/chat.db` scan).

## Constraint that shapes everything

The privacy boundary must hold per adapter, and it bites differently per
harness. Claude's file tools put paths in structured inputs; Codex's tool
stream is mostly shell strings, which the rule forbids reading, so a Codex
adapter honestly yields tokens and tool mix but few path signals. Signals
must degrade gracefully rather than tempt an adapter into parsing command
text.

## Options

1. **A — adapter registry inside `session_scan.py`.** One locate+parse
   adapter per harness, capability-tagged (`full` / `tokens-only` /
   `paths-only`), `--harness all` as the new default, aggregate keyed by
   harness. Stdlib-only holds (`sqlite3` is stdlib; every store is a file or
   SQLite db). Cost: re-states parsing knowledge TT's backend already has,
   and format drift must now be caught twice.
2. **B — ask the TT backend.** New `/sessions/signals?project=` endpoint
   computing the same signal shape with the existing parsers; the plugin
   queries it and falls back to the local Claude scan. No duplication, but
   brain-compile then needs a running backend, and the plugin's scripts stop
   being self-contained.
3. **C — shared parser library.** Extract per-harness session reading from
   `main.py` into a package both the backend and the plugin use. Cleanest
   end state; largest refactor of a monolith a solo maintainer ships from.

## Recommendation

A now, C later, B never as a dependency (fine as a bonus fast-path). Mining
runs once per compile and offline; a compile-time server dependency is the
wrong trade. Build A in evidence-value order — codex, opencode,
antigravity-cli, qwen, cline, smallcode — then copilot-cli, grok, vibe,
hermes (tokens-only); cursor paths-only if at all; gemini skipped as legacy.
Each adapter ships with a sanitized fixture log and a conformance test so
format drift surfaces in CI, not in a silent empty scan.

Add a new-agent playbook to the plugin docs: when TT gains an agent source,
the adapter checklist is (1) store path + env override, (2) project
attribution rule, (3) tool stream location and whether paths are structured
inputs or strings, (4) token fields, (5) fixture + test. That makes "new
coding agent added, scan its sessions too" a bounded task instead of a
re-exploration.

## Follow-ups

- Decide option (maintainer call), then implement adapters in priority order.
- Fold the harness matrix above into the plugin's AUTHORING docs as the
  playbook seed.
- Revisit when Omnigent lands in TT.

## Related

- [Prove the brain saves tokens](../ideas/prove-brain-token-savings.md):
  session evidence quality directly feeds brain-compile topic seeding.
- The plugin design doc (`docs/design/tokentelemetry-plugin.md`) fixed the
  structural-only privacy rule this analysis keeps load-bearing.
