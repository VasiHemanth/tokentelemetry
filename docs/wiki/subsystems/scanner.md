---
type: Subsystem
title: Session scanner
description: The core pipeline in backend/main.py; live-scans every harness's on-disk logs into a unified session list with a 30s cache and 100-session cap.
resource: /backend/main.py
tags: [subsystem, backend]
timestamp: 2026-07-02
---

# Session scanner

`backend/main.py` (~7k lines) live-scans each harness's data directory into a
unified session shape served by `/sessions` and `/analytics`.

- **Agent roots are module-level constants** (`CLAUDE_DIR`, `CODEX_DIR`,
  `GEMINI_DIR`, `QWEN_DIR`, `VIBE_DIR`, `CURSOR_DIR`, `HERMES_DIR`,
  `GROK_SESSIONS_DIR`, `COPILOT_CLI_DIR`, `ANTIGRAVITY_*_DIR`, `CLINE_DIR`,
  ...) around line 253+. Tests monkeypatch these constants; see
  [scanner tests playbook](../playbooks/write-scanner-tests.md).
- **Caching:** `get_sessions_cached` holds results in RAM for 30s
  (`SESSIONS_TTL_SEC`); list endpoints work over the top-100 sessions.
  Expensive per-session detail lives on separate endpoints (e.g. the
  [delegation overlay](delegation-telemetry.md)).
- **Parsing is tolerant:** per-line JSON parse, partial trailing lines
  skipped (sessions may still be mid-write), usage-less and `<synthetic>`
  lines skipped for cost.
- Durability on top of the live scan comes from the
  [history store](history-store.md); the scan alone dies with each agent's
  own transcript pruning.

Per-harness specifics live on the `harnesses/` pages.
