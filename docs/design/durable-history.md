# Design: Durable history + date/range analytics filters

Implements issue #83 and discussion #27. Decision recorded in
[ADR-0002](../adr/0002-durable-history-rollup.md).

## Goal

Let analytics be filtered by date range / granularity / agent / model, and make
that history survive after coding agents prune their own transcripts.

## Architecture

```
_scan_sessions_sync() ──► live session list ──► 30s RAM cache (unchanged)
                                  │
                  (background thread, fire-and-forget)
                                  ▼
              history_store.upsert_sessions() + mark_absent()
                                  ▼
                    ~/.tokentelemetry/history.db
                  (sessions / transcripts / summaries)

GET /analytics?from&to&granularity&agents&models&projects
    stored = history_store.query(...)        # full history, filtered in SQL
    + live  (only if window reaches today)   # merged by (agent,id), live wins
    → existing aggregation loop (granularity-bucketed, insights recomputed)
    → response + coverage{}
```

## Components

### `backend/history_store.py`
Self-contained SQLite layer at `tt_paths.data_dir()/history.db` (WAL, lazy
create, `PRAGMA user_version` migrations, short-lived connections). Reads never
raise; a store failure never breaks a request.

- **`sessions`** (core rollup, PK `(agent, id)`): agent, id, project, model,
  provider, endpoint, billing_mode, first/last_ts (UTC ISO), input/output/cached/
  total, cost, tok_per_sec, `ecosystem_json` (skills/MCP/delegation/subagent/parent),
  first/last_seen_at, `source_present`, `transcript_archived`, `summary_present`.
- **`transcripts`** (tier 2): zlib-compressed blob + bytes + archived_at.
- **`summaries`** (tier 3): summary text + created_at.
- API: `upsert_sessions` (idempotent by PK — a growing session updates one row),
  `mark_absent` (flags pruned rows `source_present=0`, never deletes), `query`
  (date range + IN-list filters applied in SQL on indexed `last_ts`; returns
  *session-shaped dicts*), `coverage`, `storage_stats`, and transcript/summary
  get/put/delete helpers.

### `backend/agent_retention.py`
Per-agent transcript-retention metadata (Claude 30d via real `cleanupPeriodDays`,
Gemini/Qwen 30d, Codex/DB-backed agents = no auto-cleanup) + archive opt-in flags
persisted to `retention.json`. `archive_enabled(agent)` gates tier-2 archival.

### `backend/main.py`
- `get_sessions_cached` fires `_persist_history_async(data)` after each scan
  (upsert + mark_absent + opt-in transcript archival for claude/codex).
- `/analytics` rewritten: new query params, DB∪live merge, `_bucket_key` for
  day/week/month, `coverage` in the response. Default (no params) = prior behaviour.
- Endpoints: `GET/POST /config/retention`, `DELETE /history/transcripts`.

### Frontend
- `app/analytics/page.tsx`: date presets (7d/30d/month/year/all/custom),
  granularity toggle, agent/model multi-select chips, data-availability notice.
  Filters are server-driven via the `useResource` query string.
- `app/settings/page.tsx` + `components/settings/RetentionSettings.tsx` +
  `lib/retention.ts`: "Agent history & retention" section — per-agent retention,
  archive toggle, storage readout, delete-transcripts (keeps core stats).

## Key invariants
- **Live wins** over stored for sessions still on disk (freshest tokens).
- **Store raw, derive at read** — energy/savings/CO₂ recomputed from current power config.
- **Never delete the rollup** — only `source_present` flips; transcripts/summaries
  are the only user-deletable tiers.

## Tests
`backend/test_history_store.py`, `backend/test_agent_retention.py` (pytest-free,
run directly). Cover upsert idempotency, absent-marking, tier-2 delete preserving
rollup+summary, SQL filters, bucketing, and retention accuracy.

## Out of scope (tracked on the board)
Backfilling pruned data (impossible); per-profile views (`profile` is hermes-only);
CSV/Sheets export; transcript archival for agents beyond claude/codex.
