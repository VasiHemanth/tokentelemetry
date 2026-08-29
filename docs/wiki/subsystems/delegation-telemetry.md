---
type: Subsystem
title: Delegation and ecosystem telemetry
description: Per-session subagent, skill, and MCP attribution; capability varies by harness, tokens are never invented, aggregates never double-count.
resource: /DESIGN.md
tags: [subsystem, backend, delegation, analytics]
timestamp: 2026-07-02
---

# Delegation and ecosystem telemetry

Design of record: `DESIGN.md` (pre-ADR, data shapes verified against real
local data 2026-06-10). Implementation `backend/main.py`
(`_claude_subagent_usage()`, `session_delegation()`), tests
`backend/test_delegation.py`.

- Every session carries a `delegation` marker. Capability is per-agent
  (`_DELEGATION_CAPABLE_AGENTS = {claude, cursor, opencode, hermes}`);
  everything else gets `{"supported": false}` and the UI renders
  "not recorded by <agent>", never 0.
- Modes by harness: full token rollup
  ([claude-code](../harnesses/claude-code.md)), spawn-count only
  ([cursor](../harnesses/cursor.md)), parent/child annotation
  ([opencode](../harnesses/opencode.md), [hermes](../harnesses/hermes.md);
  [grok-build](../harnesses/grok-build.md), [codex](../harnesses/codex.md),
  [antigravity](../harnesses/antigravity.md) verified capable, per DESIGN.md
  probes).
- Rich per-session breakdown is a separate overlay endpoint,
  `GET /sessions/{session_id}/delegation?agent=...` (follows the
  hermes-overlay precedent).
- Phase 2 adds `skills_used`, `tool_counts`, `mcp_usage` per session and
  `by_skill` / `by_mcp_server` / `by_subagent_type` + `delegation` buckets to
  `/analytics`; existing aggregate keys stay byte-identical.
- Governing rule: [count-once invariant](../conventions/count-once-invariant.md).
  Claude delegated tokens ARE added to aggregates (they were counted nowhere);
  opencode/hermes children already are sessions, so parent sums are
  display-only.
