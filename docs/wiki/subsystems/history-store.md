---
type: Subsystem
title: Durable history store
description: SQLite rollup at ~/.tokentelemetry/history.db so analytics survive each agent's transcript pruning; raw facts stored, insights recomputed at read.
resource: /backend/history_store.py
tags: [subsystem, backend, sqlite, analytics]
timestamp: 2026-07-02
---

# Durable history store

Decision: [ADR-0002](../decisions/adr-0002-durable-history.md); design:
`docs/design/durable-history.md`; code `backend/history_store.py`,
retention in `backend/agent_retention.py`.

- **Why:** agents prune their own transcripts (Claude Code and Gemini CLI
  default 30 days), so "this month/year" analytics were structurally
  impossible from live scans alone (issue #83, discussion #27).
- **What:** SQLite at `~/.tokentelemetry/history.db` (honors
  `TOKENTELEMETRY_DATA_DIR`), upserted on every scan from a background
  thread. Analytics = SQL-filtered history merged with the live scan; live
  wins for in-flight sessions.
- **Raw facts only** (tokens, cost, model, tok/s, timestamps, small
  ecosystem JSON); energy/savings/CO2 recomputed at read so
  [power-config](power-cost.md) changes apply retroactively.
- **Tiered retention:** tiny core rollup always kept; full transcript
  archival opt-in per agent and deletable; summaries persist past transcript
  deletion.
- **Limits:** start-from-now (pre-install history is unrecoverable, UI says
  so); summary-only rows have no drill-in; transcript archival resolves paths
  for claude/codex only (`_resolve_transcript_path`).
- Undo: delete `history.db`; agent data is never modified.
