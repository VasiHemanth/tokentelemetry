---
type: Harness
title: Grok Build (xAI)
description: Sessions under ~/.grok/sessions; subagents on by default with rich meta.json spawn records, children are sibling sessions.
resource: /backend/main.py
tags: [harness, coding-agent, delegation, xai]
timestamp: 2026-07-02
---

# Grok Build

- **Data:** `~/.grok/sessions` (`GROK_SESSIONS_DIR`). Per-session
  `signals.json` carries `contextTokensUsed`.
- **Delegation:** subagents ON by default (`--no-subagents` to disable). The
  parent writes `<session>/subagents/<spawn-id>/meta.json` with
  `{subagent_type, description, prompt, status, duration_ms, tool_calls,
  turns, effective_model_id, parent_session_id, child_session_id}`. The child
  is a full sibling session dir, already counted; linkage is annotation-only
  ([count-once](../conventions/count-once-invariant.md)).
  `spawn_subagent` / `get_command_or_subagent_output` show up in
  `events.jsonl`. Verified with grok 0.2.39 (`DESIGN.md`).
- **Quirks:** no per-call tool signal beyond events; `tool_counts` absent.
