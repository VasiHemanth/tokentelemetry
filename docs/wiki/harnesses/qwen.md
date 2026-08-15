---
type: Harness
title: Qwen CLI
description: Alibaba's coding agent; scanned from ~/.qwen, also usable as a summarizer backend. No delegation signal.
resource: /backend/main.py
tags: [harness, coding-agent, alibaba]
timestamp: 2026-07-02
---

# Qwen CLI

- **Data:** `~/.qwen` (`QWEN_DIR`); extensions inventory at
  `~/.qwen/extensions`.
- **Signals:** tokens, model, tool counts; also a summarizer backend
  (`backend/summarizers/qwen.py`, auth via `qwen auth` / `DASHSCOPE_API_KEY`).
- **Delegation:** no subagent signal; UI renders "not recorded by qwen".
