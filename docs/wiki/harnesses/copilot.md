---
type: Harness
title: GitHub Copilot CLI
description: Session state under ~/.copilot/session-state; basic token/session signals, no delegation or per-call tool signal.
resource: /backend/main.py
tags: [harness, coding-agent, github]
timestamp: 2026-07-02
---

# GitHub Copilot CLI

- **Data:** `~/.copilot/session-state` (`COPILOT_CLI_DIR`).
- **Signals:** sessions and token usage.
- **Delegation:** no subagent signal; UI renders "not recorded by copilot".
- **Quirks:** no per-call tool signal either, so `tool_counts` / `mcp_usage`
  keys are simply absent for Copilot sessions (`DESIGN.md` Phase 2).
