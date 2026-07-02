---
type: Harness
title: Cline
description: Two stores; a CLI SQLite db at ~/.cline/data/db/sessions.db and the VS Code extension's taskHistory.json. Added in PR #120.
resource: /backend/test_cline_smallcode.py
tags: [harness, coding-agent, sqlite, vscode]
timestamp: 2026-07-02
---

# Cline

Added in PR #120 (commit 90f7ad0). Two independent stores:

- **CLI:** `~/.cline/data/db/sessions.db` (`CLINE_DIR`, overridable with
  `TT_CLINE_DIR`). Shape verified against real data
  (`backend/testdata/cline_smallcode/cline_cli/`).
- **VS Code extension:** globalStorage
  `saoudrizwan.claude-dev/state/taskHistory.json` (`CLINE_VSCODE_DIR`). Not
  installed on the dev machine when written, so the parser sticks to the
  documented HistoryItem shape only; treat as lower-confidence.

Tests: `backend/test_cline_smallcode.py`. No delegation signal.
