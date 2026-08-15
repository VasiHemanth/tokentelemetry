---
type: Harness
title: Cursor
description: Agent transcripts under ~/.cursor/projects; subagent spawns are detectable but carry no token usage at all.
resource: /backend/main.py
tags: [harness, coding-agent, delegation]
timestamp: 2026-07-02
---

# Cursor

- **Data:** `~/.cursor/projects/<slug>/agent-transcripts/<sessionId>/`
  (`CURSOR_DIR`), subagents under `.../subagents/<uuid>.jsonl`.
- **Signals:** session transcripts and tool counts.
- **Delegation:** spawn detection only. Subagent files contain plain
  `{role, message}` lines with no usage fields, no model, no meta.json
  (verified in `DESIGN.md`). TokenTelemetry reports spawn count and shows
  tokens/cost as "not recorded by Cursor". Never estimate
  ([honest n/a](../conventions/count-once-invariant.md)).
