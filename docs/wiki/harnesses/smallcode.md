---
type: Harness
title: SmallCode
description: Project-local traces at <project>/.smallcode/traces/<id>.json; the only harness whose data lives in the repo, not the home dir. Added in PR #120.
resource: /backend/test_cline_smallcode.py
tags: [harness, coding-agent, project-local]
timestamp: 2026-07-02
---

# SmallCode

Added in PR #120 (commit 90f7ad0).

- **Data:** PROJECT-LOCAL: `<project>/.smallcode/traces/<id>.json`. Unlike
  every other harness there is no home-dir store, so discovery depends on
  knowing project roots. Verified shape:
  `backend/testdata/cline_smallcode/smallcode/8fadca50.json`.
- **Signals:** per-trace token counts (e.g. `prompt_tokens`).
- Tests: `backend/test_cline_smallcode.py`. No delegation signal.
