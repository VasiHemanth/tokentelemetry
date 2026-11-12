# Waste detection (evaluation Tier 1)

Status: in progress. ADR: [0006](../adr/0006-waste-signals-from-transcript-extraction.md).

TokenTelemetry evaluates real sessions with no ground truth. The plan has four
tiers: efficiency signals (Tier 1), friction signals from the human's reaction
(Tier 2), outcome signals per use case (Tier 3), and a local model-graded judge
(Tier 4). Tiers 1 and 2 are the same code for every user and agent. This
document covers Tier 1 only, built on data the app already reads. No SDK, no
plugin, no new evaluator.

## Why a separate extraction pass

The session list scan keeps rollups. Only Claude Code records tool errors
there, and no agent records tool arguments, so retry loops and repeated file
reads cannot be computed from `/sessions`. The on-demand transcript parse
behind `GET /sessions/{id}` does expose tool names, arguments and results for
most agents. Tier 1 therefore runs a per-session extraction over that parse
and caches the result.

## Privacy

The cache holds counts and labels. It never holds prompt text, tool output,
command strings or file contents. File paths are used in memory to detect
re-reads and are not persisted.

## Signals (per session)

| Field | Meaning |
|---|---|
| `user_turns` | Real user messages (tool-result echoes and system reminders excluded). |
| `tool_calls` | Tool invocations. |
| `tool_errors` | Tool results carrying an explicit error flag or status. Substring matching on output text is not used: it produces false positives. |
| `retry_calls` | Extra calls inside runs of 3 or more consecutive identical calls (same tool, same argument hash). A run of 5 counts 4. Status-polling tools that are meant to be called repeatedly (for example Codex `write_stdin`) are excluded. |
| `reread_calls` | Read-type calls on a path and range already read in the session with no edit to that path in between. Reading one large file in chunks does not count. Edits made through a shell command are not seen, so this can overcount. |
| `edit_calls` | Edit/write-type tool calls. |
| `cache_hit_pct` | cached / (input + cached) from the session token rollup. |
| `context_growth` | Mean prompt size per assistant turn (cached and uncached input together) in the last quarter of the session divided by the first quarter. Null when per-turn usage is not recorded or the session has fewer than 8 turns. |

A signal an agent's transcript cannot support is `null`, never `0`. The
response carries a per-agent capability map so the UI can say "not recorded
by this agent" instead of implying a clean result.

## Flags

Thresholds live in one dict in `backend/waste.py` and are returned in the
response.

| Flag | Rule |
|---|---|
| `tool_failures` | `tool_calls >= 10` and `tool_errors / tool_calls >= 0.20` |
| `retry_loop` | `retry_calls >= 3` |
| `rereads` | `reread_calls >= 5` |
| `context_bloat` | `context_growth >= 5.0` |
| `low_cache` | input + cached >= 200k and `cache_hit_pct < 30` on an agent that reports cache reads |
| `no_artifact` | `tool_calls >= 30`, cost above zero, no edit calls, no artifacts or published artifacts, and cost at or above the median session cost |

`no_artifact` is the "dead end" signal. It is deliberately conservative
because a research or question-answering session legitimately produces no
edits. Tier 3 intent classification will tighten it.

## What the view does not claim

There is no "task" boundary in the data, so "per task" metrics use the
session and the user turn as units. The view reports flagged spend (the cost
of sessions with at least one flag), not "wasted dollars": attributing a
dollar amount to a single failed call is not defensible from this data.

## Endpoint

`GET /waste?from=&to=&agents=&projects=` (same parameter names as `/analytics`)

```jsonc
{
  "summary": {
    "sessions": 0, "analysed": 0, "pending": 0, "failed": 0,   // failed are included in analysed
    "total_cost": 0.0, "flagged_sessions": 0, "flagged_cost": 0.0,
    "tool_calls": 0, "tool_errors": 0, "failure_rate": 0.0,   // 0 to 1, over sessions that can record errors; null if none can
    "retry_calls": 0, "reread_calls": 0, "no_artifact_sessions": 0,
    "cost_per_session": 0.0, "turns_per_session": 0.0, "cost_per_turn": 0.0
  },
  "by_agent": [{
    "agent": "claude", "sessions": 0, "analysed": 0, "cost": 0.0,
    "flagged_sessions": 0, "flagged_cost": 0.0,
    "failure_rate": null, "retry_calls": null, "reread_calls": null,
    "cost_per_session": 0.0, "turns_per_session": null,
    "capabilities": {"tool_errors": true, "retries": true, "rereads": true,
                     "turns": true, "context_growth": true, "cache": true}
  }],
  "by_flag": [{"flag": "retry_loop", "sessions": 0, "cost": 0.0}],
  "sessions": [{            // flagged sessions, highest cost first, max 100
    "id": "", "agent": "", "project": "", "timestamp": "", "display": "",
    "model": "", "cost": 0.0, "tokens_total": 0,
    "user_turns": 0, "tool_calls": 0, "tool_errors": null,
    "retry_calls": null, "reread_calls": null, "edit_calls": null,
    "cache_hit_pct": null, "context_growth": null,
    "flags": ["retry_loop"]
  }],
  "thresholds": {}
}
```

`analysed` and `pending` exist because extraction is incremental. The endpoint
never blocks on parsing transcripts: it aggregates whatever is cached and a
background worker fills in the rest, newest sessions first. The page polls at
a multi-minute interval and shows coverage.

## Known limits

- The endpoint reads the live scan only. Sessions whose source files are gone
  remain in `/analytics` through the history store but are absent here.
- A session whose extraction fails is marked failed and retried only when the
  session changes or the extraction version is bumped.
- Thresholds were set against one machine's history (about 1,100 sessions).
  At a growth threshold of 3.0, `context_bloat` flagged 30% of the sessions it
  could measure, which is normal long-session behaviour, so it was raised to
  5.0 (about the 90th percentile). Expect to retune these with wider data.
- Stub sessions and sessions with neither tokens nor tool calls are excluded.
