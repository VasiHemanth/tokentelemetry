---
type: Harness
title: Gemini CLI (legacy)
description: Google's discontinued CLI agent; still scanned from ~/.gemini but treated as legacy, superseded by Antigravity.
resource: /backend/main.py
tags: [harness, coding-agent, legacy, google]
timestamp: 2026-07-02
---

# Gemini CLI

- **Data:** `~/.gemini` (`GEMINI_DIR`). Note the same directory also hosts
  Antigravity data (`antigravity/brain`, `antigravity-cli`); see
  [Antigravity](antigravity.md).
- **Signals:** tokens, model, tool counts; also a summarizer backend
  (`backend/summarizers/gemini.py`).
- **Delegation:** no subagent signal in its logs; the UI renders
  "not recorded by gemini", never 0.
- **Status:** Google discontinued Gemini CLI on 2026-06-18 in favor of the
  closed-source Antigravity CLI. Keep parsing existing local data (users keep
  history), but treat the harness as legacy: no new feature work, prune
  default was 30 days so most installs age out on their own.
