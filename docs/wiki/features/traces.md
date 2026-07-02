---
type: Feature
title: Session traces
description: Per-session drill-in; tool calls, reasoning steps, artifacts, delegated-work cards, skills and MCP usage.
resource: /website/content/docs/features/traces.mdx
tags: [feature, sessions, traces]
timestamp: 2026-07-02
---

# Session traces

`/sessions` list and `/sessions/[id]` detail.

- Detail shows the event trace: tool calls (direct vs MCP grouped by
  server), reasoning steps, and artifacts (images/files; loaded with
  `?token=` under [remote auth](../subsystems/remote-auth.md)).
- Delegated-work card links subagent spawns to the spawning `Agent`/`Task`
  tool call; tokens shown per subagent where the harness records them
  ([delegation telemetry](../subsystems/delegation-telemetry.md)).
- Sessions whose transcript the agent already pruned appear in aggregates but
  without drill-in (summary-only rows,
  [history store](../subsystems/history-store.md)).
- AI summaries per session via [summarization](summarization.md).
