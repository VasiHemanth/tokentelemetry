---
type: Playbook
title: Add a new harness
description: Steps to support a new agent; verify real data shapes first, add scanner constants and parser, fixture tests, honest capability flags, docs.
tags: [playbook, harness, scanner]
timestamp: 2026-07-02
---

# Add a new harness

Reference examples: PR #120 (Cline + SmallCode), `DESIGN.md` probe notes.

1. **Verify the real data shape first.** Run the agent locally (headless
   probes work; see DESIGN.md's grok/codex/agy method), find its store
   (JSONL, JSON, or SQLite), and commit a small verified sample under
   `backend/testdata/<harness>/`. Don't code against documentation alone;
   when forced to (Cline's VS Code store), say so in comments and tests.
2. **Scanner:** add the data-dir as a module-level constant in
   `backend/main.py` (env-overridable if users relocate it, like
   `TT_CLINE_DIR` / `HERMES_HOME`), plus the parse into the unified session
   shape. Tolerant per-line parsing; skip usage-less lines.
3. **Capability flags:** only claim signals the logs actually record.
   Delegation support goes in `_DELEGATION_CAPABLE_AGENTS`; anything absent
   renders "not recorded by <agent>"
   ([count-once / honest n/a](../conventions/count-once-invariant.md)).
4. **Tests:** fixture tests monkeypatching the dir constants
   ([scanner tests](write-scanner-tests.md)).
5. **Pricing:** ensure the models it emits exist in
   `backend/pricing_data.json` ([pricing](../subsystems/pricing.md)).
6. **Frontend:** register the agent in `frontend/src/lib/agents.ts`.
7. **Docs + ship:** update README + `llms.txt` agent lists and counts,
   `website/content/docs/supported-agents.mdx`, a `harnesses/` wiki page,
   and follow [ship-a-feature](ship-a-feature.md) (a new harness is a
   `feat:`, so UPDATE.json).
