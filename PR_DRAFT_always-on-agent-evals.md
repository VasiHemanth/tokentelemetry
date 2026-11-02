# Always-on agent evals: wake/silence, schedule drift, inter-agent calls (record-only)

## Why
For proactive / cron / peer-triggered agents the eval unit is the whole trace: wake, act, stay silent, or escalate. This PR adds the smallest additive schema to record those decisions so they can later be scored (code checks + LLM-as-judge, annotation queues). First harnesses: **Grok loops, Claude `/loop`, Antigravity**, all **record-only**.

## What
- `backend/agent_evals.py` (new): `EvalEvent` (schema_version 1) with kinds
  - `wake_decision` — decision wake|silence, trigger cron|event|peer|user, reason?, confidence?, label?, turn_event_index?
  - `schedule_fire` — loop_id/job_id, cadence, expected_at, actual_at, drift_s, missed, human_present (30-min no-human window)
  - `agent_call` — parent/child session, msg_id, channel subagent|peer|a2a, resolved, latency_ms
  - Derivation from existing `sess["loop"]` and `session_links` edges; precision/recall + drift p50/p95 summary.
  - Config `evalRecordOnly` (default **true**) in `<data_dir>/evals.json`; `feeds_automation()` gate. Distinct from frontend `TraceSpan.recordOnly`.
- `backend/history_store.py`: migration `user_version=5` → `CREATE TABLE IF NOT EXISTS eval_events(agent, session_id, id, ts, kind, json, PRIMARY KEY(agent,id))` + index; `upsert_eval_events` / `query_eval_events`.
- `backend/main.py`: `GET /evals/events?kind=&session_id=&agent=`, `GET /evals/summary`, `POST /evals/label`, `GET|POST /config/evals`.
- Frontend: `src/lib/evals.ts` types; `TraceSpan.turnKind` gains `"wake"` and optional `TraceSpan.eval`. No adapter changes.

## Not changed
`scan_cache.CACHE_VERSION`, session parser required fields, notifications. Nothing in this PR notifies or scores automatically.

## Privacy
Eval rows hold ids, timestamps, enums and labels only. An allow-list scrub drops prompt previews, cwd/paths, and message bodies (tested). No network calls.

## Known gaps
- No harness records wake/silence today → only `derived` *wake* stubs for observed loop fires; silences need a harness hook (`recorded`) or human labels.
- Drift is computed for the last fire only (`created_at + iterations*cadence` vs `last_fired`); Grok's `last_fired` approximates last activity.
- Antigravity has no loop/cron data in its transcripts → nothing derived yet; recorded events accepted.
- `human_present` uses `last_user_ts` if a session has it, otherwise false.

## Tests
`pytest backend/test_agent_evals.py` — 8 tests: drift + wake stub, missed fire, cancelled loop, harness filter, privacy scrub, subagent/peer calls, precision/recall, config default/persist, v4→v5 migration + idempotent upsert. `test_history_store.py`, `test_loops.py` pass. `tsc --noEmit` clean. Pre-existing flaky mtime tests in `test_delegation.py` fail on `main` too.

## Needs verification on a real machine
Run against real Grok scheduler tasks, Claude `/loop` CronCreate sessions, and Antigravity sessions; check `/evals/summary` drift values look sane.
