---
type: Harness
title: Vibe
description: Scanned from ~/.vibe; sessions and tokens only, no delegation or per-call tool signal.
resource: /backend/main.py
tags: [harness, coding-agent]
timestamp: 2026-07-02
---

# Vibe

- **Data:** `~/.vibe` (`VIBE_DIR`).
- **Signals:** sessions and token usage.
- **Delegation:** no subagent signal; UI renders "not recorded by vibe".
  No per-call tool signal, so `tool_counts` / `mcp_usage` are absent.
