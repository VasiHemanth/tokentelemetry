# ADR-0002: Durable SQLite rollup for analytics history

- **Status:** Accepted
- **Date:** 2026-06-13
- **Deciders:** VasiHemanth
- **Related:** issue #83, discussion #27, [design doc](../design/durable-history.md)

## Context

TokenTelemetry was a pure live-scanner: every `/analytics` and `/sessions` request
re-read the coding agents' on-disk transcripts and kept the result only in a 30-second
in-RAM cache (`SESSIONS_TTL_SEC`, `get_sessions_cached` in `backend/main.py`). Nothing
was persisted.

But agents prune their own transcripts on a schedule — Claude Code deletes
`~/.claude/projects/**/*.jsonl` after `cleanupPeriodDays` (default **30**), Gemini CLI
defaults to 30 days, others vary. So the date-range filtering users asked for (issue
#83: "this month/this year"; discussion #27: ranges finer/longer than the 7-day floor)
was *structurally impossible* — a "this year" view could only ever show what each agent
still had on disk. A constraint reinforced by [[local-first-no-user-network]]: the fix
must work entirely on the user's machine, no external storage.

## Decision

We will give TokenTelemetry its own **durable local SQLite store** at
`~/.tokentelemetry/history.db` (honouring `TOKENTELEMETRY_DATA_DIR`), upserted on every
scan from a background thread. Analytics reads the store (full history, filtered in SQL)
**merged with** the live scan (freshest in-flight sessions, live wins). We store **raw
facts** (tokens, cost, model, tok/s, timestamps + a small ecosystem JSON) and recompute
derived insights (energy/savings/CO₂) at read time, so power-config changes apply
retroactively.

Storage is **tiered** so users control disk: a tiny **core rollup** is always kept;
**full transcripts** are opt-in per agent and deletable; generated **summaries** persist
even after a transcript is deleted.

## Alternatives considered

- **Keep live-scanning only** — simplest, but the feature is impossible (history dies
  with the agents' pruning). Rejected.
- **Archive every full transcript by default** — durable, but heavy on disk and copies
  data the user didn't ask us to keep. Rejected as the default; offered as an opt-in tier.
- **Store derived insights (energy/cost) directly** — would freeze them against the
  power config at write time, so later config changes wouldn't apply. Rejected in favour
  of storing raw facts and recomputing at read.
- **Load all history into Python per request** — the obvious latency trap. Rejected in
  favour of SQL-side date/allow-list filtering on indexed `last_ts`.

## Consequences

- ✅ Analytics history survives agent pruning; date/granularity/agent/model filters work
  over the full retained range (issue #83, discussion #27).
- ✅ Historical-only windows are served entirely from SQLite — often *faster* than the
  old always-scan path; only windows reaching "today" merge the live scan.
- ✅ Raw-fact storage means power-config changes retroactively re-price old sessions.
- ⚠️ **Start-from-now:** we can only capture sessions present on disk at first run;
  already-pruned history is unrecoverable. The analytics UI states this explicitly.
- ⚠️ **Summary-only rows:** once an agent prunes a transcript (and the user didn't opt
  into archiving), the session shows in aggregates but has no transcript drill-in.
- ⚠️ Transcript archival currently resolves single-file transcripts for **claude/codex**
  only (`_resolve_transcript_path`); other agents are rollup-only until extended
  (tracked on the board).
- 🔁 To undo: revert the feature PR. `history.db` is self-contained under the data dir
  and can simply be deleted; no agent data is ever modified.
