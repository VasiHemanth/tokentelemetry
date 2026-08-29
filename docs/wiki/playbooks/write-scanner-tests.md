---
type: Playbook
title: Write scanner tests
description: Fixture pattern for backend tests; monkeypatch the module-level dir constants and build a tmp tree mirroring the harness's real layout.
tags: [playbook, testing, backend]
timestamp: 2026-07-02
---

# Write scanner tests

Scanner paths are module-level constants (`CLAUDE_DIR = HOME / ".claude"`
etc. in `backend/main.py`), so fixtures must **monkeypatch the constant**
and build a tmp tree that mirrors the harness's real layout (parent
transcript + `subagents/` subdir, SQLite db file, etc.).

- Copy the pattern from an existing test: `backend/test_delegation.py`
  (JSONL trees), `backend/test_cline_smallcode.py` (SQLite + JSON stores,
  builder helpers), `backend/test_tt_paths.py` (data-dir resolution).
- Base fixtures on verified real shapes committed under `backend/testdata/`.
- Cover the tolerant-parse edges: partial trailing line, usage-less lines,
  `<synthetic>` model, missing/corrupt meta.json (falls back to
  `agent_type: "unknown"` but still sums usage).
- Run: `pytest backend/<file> -q` (deps: `backend/requirements.txt`).
