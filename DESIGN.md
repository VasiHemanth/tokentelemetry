# Delegation & Ecosystem Telemetry — design notes

Goal: show the TRUE cost of a session including everything it spawned (subagents),
and which skills / MCP servers / subagent types actually earn their keep — without
eroding trust: no silent historical changes, no fake zeros, model-correct pricing,
explicit "n/a" where an agent's logs don't record the signal.

All shapes below were verified against real data on this machine (2026-06-10).

## 1. Verified data shapes

### Claude Code (full support — token rollup possible)

```
~/.claude/projects/<encoded-proj>/<sessionId>/subagents/agent-<agentId>.jsonl
~/.claude/projects/<encoded-proj>/<sessionId>/subagents/agent-<agentId>.meta.json
```

- `meta.json` (present on all 55 local files, but code defensively):
  `{"agentType": "Explore", "description": "...", "toolUseId": "toolu_01RB3..."}`
- The parent transcript contains a matching `tool_use` block: `name: "Agent"`
  (older Claude Code versions used `"Task"` — match both), `id == meta.toolUseId`,
  `input: {description, subagent_type, prompt}`.
- Subagent JSONL lines mirror the main-session schema. Assistant lines carry:
  `isSidechain: true`, `agentId`, `attributionAgent` (agent type),
  `sessionId` (= PARENT session id — fallback linkage if dir name is lost),
  `message.model`, `message.usage` with full cache fields
  (`cache_read_input_tokens`, `cache_creation_input_tokens`,
  `cache_creation.ephemeral_1h_input_tokens`).
- Empirical facts (don't rely on them, but don't over-engineer either):
  one model per file today (but cost per-line by that line's model anyway;
  skip `<synthetic>`); no nested `subagents/` dirs; `usage.iterations` always
  length ≤ 1 (ignore it; read top-level usage only).
- Models seen in subagent files differ from parents: haiku-4-5, sonnet-4-6,
  opus-4-7, opus-4-8. **Costing with the parent's model would be wrong.**
- The session dir also contains `tool-results/` — ignore it.
- Local hidden volume (why this is Phase 1): 55 subagent files / 14 sessions =
  521k in + 402k out + 6.7M cache-write + 87.8M cache-read tokens, currently 0
  in the dashboard.

### Cursor (spawn detection ONLY — no token data)

```
~/.cursor/projects/<slug>/agent-transcripts/<sessionId>/subagents/<uuid>.jsonl
```

- **Subagent files contain NO usage fields at all** (verified: plain
  `{role, message}` lines, no token counts, no model, no meta.json).
- Therefore: report spawn count + transcripts existence; tokens/cost = "not
  recorded by Cursor". Do NOT estimate.

### OpenCode / Hermes (hierarchy via parent id — children are already sessions)

- OpenCode sqlite `session.parent_id`: 5 of 12 local sessions are children.
- Hermes sqlite `sessions.parent_session_id`: 12 of 21 local sessions are children.
- Child usage is ALREADY counted (each child appears as its own session today).
  So: annotate hierarchy (`parent_session_id` on child, `child_session_ids` +
  display-only delegated sums on parent). NEVER add child sums into aggregate
  totals — that would double-count.

### No subagent signal (render explicit "not recorded by <agent>")

codex, gemini, qwen, grok, copilot, vibe, antigravity.

## 2. Token semantics — the count-once invariant

Every token is counted in project/analytics aggregates exactly once.

- **Claude Code**: subagent files are NOT sessions; their usage is counted
  nowhere today. Add as a separate `delegated` bucket on the parent and DO
  include it in aggregates (this is the fix — totals will visibly increase;
  announce in UPDATE.json, don't let users discover it).
- **OpenCode/Hermes**: children ARE sessions; their usage is already in
  aggregates. Parent-side delegated sums are display-only annotations.
- Parent `tokens.{input,output,cached,...}` stay EXACTLY as today. New fields
  only; headline UI shows "X + Y delegated", never a silently merged number.
- Cache semantics match the existing scanner: `cached` = high-water-mark of
  `cache_read_input_tokens` per transcript file; cache_creation cumulative.
  Apply per subagent file, cost via `calculate_cost(model_of_that_file, ...)`.

## 3. Shapes (Phase 1 — IMPLEMENTED on branch worktree-delegation-telemetry)

Every session in `/sessions` carries a `delegation` marker. Capability is
per-agent (`_DELEGATION_CAPABLE_AGENTS = {claude, cursor, opencode, hermes}`);
everything else gets `{"supported": false}` — frontend renders
"not recorded by <agent>", never 0.

```json
claude:           {"supported": true,  "tokens_recorded": true,  "spawn_count": 2, "delegated_total": 82340}
cursor:           {"supported": true,  "tokens_recorded": false, "spawn_count": 4}
opencode/hermes parent: {"supported": true, "tokens_recorded": false, "linked_children": 1}
```

Claude sessions with spawns additionally get `tokens.delegated_input/_output/
_cached/_cache_creation` + top-level `delegated_cost` (existing token fields
untouched). OpenCode/Hermes: `parent_session_id` on children,
`child_session_ids` on parents.

The RICH breakdown lives on a per-session overlay endpoint (the claude detail
endpoint returns a raw event list, so it follows the `/sessions/{id}/hermes-
overlay` precedent): `GET /sessions/{session_id}/delegation?agent=...` →

```json
{
  "supported": true, "tokens_recorded": true, "spawn_count": 2, "cost": 0.245,
  "totals": {"input": 0, "output": 0, "cached": 0, "cache_creation": 0, "cache_creation_1h": 0, "total": 0},
  "subagents": [
    {"agent_id": "aaef9765c0454d680", "agent_type": "Explore",
     "description": "Explore backend request/auth surface",
     "tool_use_id": "toolu_01RB3...", "model": "claude-haiku-4-5-20251001",
     "tokens": {"...": 0}, "cost": 0.12}
  ]
}
```

cursor returns spawn entries with `tokens: null` (never invented); opencode/
hermes return `parent_session_id` + `child_session_ids`; unsupported agents
`{"supported": false}`. Implementation: `_claude_subagent_usage()` +
`session_delegation()` in `backend/main.py`; tests in
`backend/test_delegation.py`.

Phase 2 (per session): `skills_used: [{name, count}]` (from `Skill` tool_use
`input.skill` + `<command-name>` tags in user lines — filter out built-in CLI
commands like /model, /usage which also emit the tag), and
`mcp_usage: {server: {tool: count}}` parsed from `mcp__<server>__<tool>` names
(Grok: `signals.json.toolsUsed[]`; Copilot/Vibe/Antigravity: unsupported).
`/analytics`: `by_skill`, `by_mcp_server`, `by_subagent_type`.

## 4. Edge cases

- meta.json missing/corrupt → agent_type "unknown", still sum usage.
- Subagent file still being written (background agent) → per-line tolerant JSON
  parse (same as existing scanner), partial last line skipped.
- `<synthetic>` model lines and usage-less lines → skip for cost, don't crash.
- Possible future nesting (subagent spawning subagents) → at minimum don't
  recurse infinitely; either one level (today's reality) or bounded recursion.
- Session resumed/compacted: subagent dir name == original sessionId; the
  `sessionId` field inside subagent lines is the authoritative parent link.
- Scanner perf: the per-session subdir check is one `is_dir()` stat for the
  top-100 sessions; full subagent read happens in the list scan only as a cheap
  sum (55 small files locally — fine), detail endpoint does the rich version.
  Respect the existing sessions cache (`get_sessions_cached`) and 100-cap.
- Tests: scanner paths are module-level constants (`CLAUDE_DIR = HOME/".claude"`)
  — fixtures must monkeypatch the constant (see existing test files for the
  pattern) and build a tmp tree with parent jsonl + subagents/.

## 5. Order of work

1. **Phase 1 backend** — Claude Code subagent scan (rollup + detail), Cursor
   spawn-count only, OpenCode/Hermes parent/child markers. Fixture tests.
   Primary token fields untouched.
2. **Phase 2 backend** — skills + MCP usage extraction, analytics `by_*`,
   count-once enforcement in aggregates.
3. **Phase 3 frontend** — Delegated-work card on session detail (linked to the
   spawning Agent/Task tool call in the trace), Tools panel split (direct vs
   MCP grouped by server), analytics charts, usage overlays on the /config
   inventory ("installed but never used" is an insight), honest n/a states.
4. **UPDATE.json + browser verification** — feat: commits require an
   UPDATE.json entry (pre-push hook); the entry should explicitly say totals
   now include previously hidden subagent usage.
