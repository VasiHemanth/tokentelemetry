# Design: `/goal` telemetry

Companion to the `/loop` support already in `backend/main.py`
(`_annotate_loop_lifecycle`, `_grok_loop_detect`, `_cline_loop_specs`). Same
question, different feature: when a user hands an agent an objective and walks
away, what did that cost and how did it end?

Status: plan. Nothing here is implemented yet.

## What `/goal` actually is

`/goal` is not one feature. Four agents ship a command with that name and all
four mean something different by it, with very different amounts of evidence
left on disk. Everything below was verified against local docs bundles, the
Claude Code changelog, and this machine's own session data (read-only).

### Claude Code

Built-in. From `~/.claude/cache/changelog.md`:

> Added `/goal` command: set a completion condition and Claude keeps working
> across turns until it's met. Works in interactive, `-p`, and Remote Control.
> Shows live elapsed/turns/tokens as an overlay panel

Mechanically it arms a session-scoped **Stop hook**. Each time the agent tries
to end its turn, an evaluator checks the condition; if unmet, the stop is
blocked and the agent keeps going. The same changelog records the safety valve:

> Fixed stop hooks that block repeatedly looping forever: the turn now ends with
> a warning after 8 consecutive blocks (override via
> `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`)

The 8-block cap is **not** in the public hooks docs (checked
`code.claude.com/docs/en/hooks`); the changelog is the only source, and local
data agrees (see below). Treat it as a real but version-dependent constant, and
read `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` before assuming 8.

### Codex

The richest of the four, and the only one with a purpose-built store:
`~/.codex/sqlite/goals_1.sqlite`.

```
thread_goals(thread_id, goal_id, objective, status, token_budget,
             tokens_used, time_used_seconds, created_at_ms, updated_at_ms)
thread_goal_continuation_deferrals(thread_id)     -- migration v2 only
```

Codex counts a goal's tokens and wall-clock **itself**. Statuses seen in its
internal prompt: `complete`, `blocked`, plus `paused` observed in the data. The
prompt also instructs the model to report final consumed budget against
`token_budget` when a goal completes.

Two copies of this DB exist on disk and they are **at different migration
levels**, which matters more than it looks:

| Path | Migrations | Tables | Rows |
|---|---|---|---|
| `~/.codex/sqlite/goals_1.sqlite` | v1 | `thread_goals` only | 1 |
| `~/.codex/goals_1.sqlite` | v1, v2 | + `thread_goal_continuation_deferrals` | 0 |

So the populated DB is on the *older* schema and does not have the deferrals
table at all. The reader must pick the DB by row count, and must probe
`sqlite_master` before touching `thread_goal_continuation_deferrals` rather than
assuming the newer schema. Querying it blindly raises
`no such table` (hit while researching this doc).

### Grok Build

From its local docs bundle, `~/.grok/docs/user-guide/04-slash-commands.md`:

> Set, manage, or check an autonomous goal. Grok works toward the objective
> across turns and reports progress.
> Arguments: `<objective>`, `status`, `pause`, `resume`, or `clear`.
> **Availability:** appears only when the goal feature is enabled and the
> `update_goal` tool is in the session toolset.

Progress is reported through an `update_goal` **tool call** carrying
`{"message": "..."}` and, at the end, `{"completed": true, "message": "..."}`.
This is a checkpoint stream, not a stop-blocking condition.

### Antigravity

`/goal` wraps the user's request as a marker rather than driving any machinery.
The transcript carries `<USER_REQUEST>\n/goal <text>/goal\n</USER_REQUEST>`, and
the agent's own context explains it as a task "intended to run for a long time
without user input, e.g. overnight". No status, no completion signal.

### Support matrix

Counts are from this machine, deduped, read-only.

| Agent | Has `/goal` | Mechanism | Durable evidence | Local usage |
|---|---|---|---|---|
| Claude Code | yes | Stop-hook completion condition + evaluator | transcript text only | 15 sessions armed, 30 goals, 17 block events |
| Codex | yes | `thread_goals` SQLite + `update_goal` tool | dedicated DB with native token/time accounting | 1 goal (270,359 tokens, 2,615 s, `paused`) |
| Grok Build | yes (feature-gated) | `update_goal` progress tool | `chat_history.jsonl` tool calls | 88 calls across 24 sessions |
| Antigravity | yes | prompt marker | `transcript.jsonl` user request | ~19 invocations across 10 conversations |
| Gemini CLI, Cursor, Copilot, OpenCode, Qwen, Vibe, Pi, Cline, Hermes, Omnigent | no evidence found | — | — | — |

So: four of roughly fourteen supported agents, not "most". That is still worth
building for, because all four are agents this user actually runs unattended,
and because the Codex row alone shows a single goal burning 270k tokens.

## Why goals cannot reuse the loop schema

`/loop` got one shared shape across agents because a recurring timer really is
the same object everywhere: a cadence, a fire count, a last fire. Goals are not.

1. **A session holds many goals.** A loop is effectively one per session. Local
   Claude sessions arm goals repeatedly: one session armed five distinct
   conditions, another four. The field must be a **list**, `sess["goals"]`, not
   the singleton `sess["loop"]`.
2. **Terminal state is knowable for exactly one agent.** Codex writes `status`.
   Nobody else does. Claude Code, verified explicitly, emits **no terminal
   event at all**: every hook-related record in a goal session is either "Goal
   set" or "Stop hook feedback". Nothing marks a goal met, cleared, or
   abandoned. 13 of 15 Claude goal sessions recorded zero blocks, meaning the
   only honest reading is "armed, outcome unknown".
3. **"Cost of a goal" means three different things** (see below).

The design therefore is a shared **envelope** plus per-agent **evidence**, with
one annotator branching on `source`, exactly as `_annotate_loop_lifecycle`
already branches on `mode`. What must not ship is a single set of state names
that is truthful for Codex and invented for everyone else.

## Data model

`sess["goals"]: List[Goal]`, each:

```jsonc
{
  "source": "claude" | "codex" | "grok" | "antigravity",
  "goal_id": "588ec6b8-…",      // codex only; else synthesized from (ts, hash)
  "objective": "…",              // truncated to 200 chars, never full text
  "created_at": "2026-06-13T13:08:03.882Z",
  "updated_at": "2026-06-13T14:51:15.254Z",

  "state": "active" | "paused" | "complete" | "blocked" | "armed" | "unknown",
  "state_source": "reported" | "inferred",   // <- the honesty flag

  "evidence": { … per-agent, see below … },

  "tokens": 270359,              // null unless the agent counts it natively
  "duration_seconds": 2615,      // null unless natively counted
  "token_budget": null,
  "cost_basis": "native" | "attributed_turns" | "session"
}
```

`state_source` is the load-bearing field. `reported` means the agent wrote that
status down. `inferred` means TokenTelemetry guessed from breadcrumbs, and the
UI must render it differently (muted, with a tooltip). Only Codex ever produces
`reported`.

Per-agent `evidence`:

- **claude**: `{blocks: int, first_block, last_block, block_bursts: [int],
  cap_hit: bool}`. `cap_hit` is `max(burst) >= 8`, flagged as a heuristic.
- **codex**: `{status_raw, token_budget, deferrals: int | null}`. `deferrals` is
  `null`, not `0`, when the DB predates migration v2 and has no such table.
- **grok**: `{checkpoints: int, first_ts, last_ts, completed: bool}`.
- **antigravity**: `{marker_only: true}`.

Allowed states per agent, enforced in the annotator so a lie is impossible:

| Agent | States it may emit |
|---|---|
| Codex | `active`, `paused`, `complete`, `blocked` (all `reported`) |
| Grok | `complete` when a checkpoint carries `completed:true`, else `active` (`inferred`) |
| Claude | `armed`, `blocked`, `unknown`. **Never `complete`.** |
| Antigravity | `unknown` only |

## Detection

### Claude (`_scan_sessions_sync`, alongside the existing loop parse)

Two markers, both in `type: "user"` records:

- arm: `A session-scoped Stop hook is now active with condition: "<cond>"`,
  paired with the `<command-name>/goal</command-name>` +
  `<local-command-stdout>Goal set: …` record at the same timestamp.
- block: a record containing `Stop hook feedback`.

Two traps, both hit during research:

- **Compaction duplicates.** A compacted transcript replays earlier records, so
  the same arm appears at two line numbers with an identical timestamp. Dedupe
  on `(timestamp, sha1(condition)[:12])`.
- Records whose content is a `tool_result` may quote these strings verbatim (a
  session that greps for them, like the research that produced this doc).
  Skip `tool_result` blocks.

Block bursts: group block events with gaps under 5 minutes. Local data shows one
burst of exactly 8 rapid blocks (15:51:06 to 15:53:39) then a stop, which is the
documented cap firing, and a later burst of 5.

### Codex

Read both candidate paths and use whichever has rows (see the migration-level
table above), via read-only URI and `PRAGMA busy_timeout`, wrapped so a locked,
missing, or older-schema DB yields no goals rather than an error. Join `thread_id` to the Codex session id already
parsed from `~/.codex/sessions/**/rollout-*.jsonl` (the rollout filename
contains the thread id, confirmed: thread `019ebfe9-f0a5-78a3-ba8b-05d68bd72a00`
matches `rollout-2026-06-13T13-07-20-019ebfe9-….jsonl`).

Unlike everything else in the scan, this is **live mutable state**: status moves
`active → paused → complete`. Treat it like loop lifecycle, not like a cached
fact, and re-read per request rather than freezing it into the session cache.

### Grok

`chat_history.jsonl`, `tool_calls[]` entries where `name == "update_goal"`.
Parse `arguments` for `message` and `completed`. Reuse the session/project
resolution `_grok_loop_detect` already does.

Do **not** count `updates.jsonl` `params.update._meta."x.ai/tool"` mentions:
those are the tool being announced, not invoked. This distinction cut 1,808
candidate files down to 88 real calls.

### Antigravity

`~/.gemini/antigravity-cli/brain/<id>/.system_generated/logs/transcript.jsonl`,
regex `<USER_REQUEST>\s*/goal`. `transcript.jsonl` and `transcript_full.jsonl`
duplicate each other; read one. Note `~/.gemini/everything-claude-code/` is a
checked-out third-party repo about Claude Code and is pure noise for any Gemini
or Antigravity scan; exclude it.

## Cost semantics, and the double-counting trap

Three different meanings, and the UI must label which one it is showing.

- **Codex, `cost_basis: "native"`.** `tokens_used` and `time_used_seconds` come
  from Codex. Authoritative. But the same tokens are already inside the thread's
  session total that TokenTelemetry reports, so the goal figure is a **share of**
  the session, never an addition to it. Render as "270,359 of the session's N".
- **Claude, `cost_basis: "attributed_turns"`.** The only incremental number
  available: usage of assistant turns that exist *because* a stop was blocked,
  i.e. turns between a `Stop hook feedback` record and the next stop attempt.
  This is the direct analog of the existing `loop_usage` fire-response span in
  the loop parser, and should reuse that span technique.
- **Grok / Antigravity, `cost_basis: "session"`.** No per-goal boundary exists.
  Show the session cost and say so. Never present it as incremental.

Any rollup that sums "goal cost" across agents is meaningless and should not be
built. Aggregate within a `cost_basis`, not across.

## Surfaces

Deliberately smaller than the loop UI, because for two of four agents there is
little to say.

1. **Session trace page**: a `GoalCard` next to the existing `LoopCard`, one
   card per goal in `sess["goals"]`. Objective, state chip (muted when
   `inferred`), and whichever of tokens/duration/blocks/checkpoints exists.
   Absent fields are omitted, not zero-filled.
2. **Analytics**: extend the existing loops section rather than adding a page.
   A goals table: agent, objective, state, cost basis, cost. Sorted by tokens
   where known.
3. **Project Config tab**: goal count per project, mirroring the loop cards.

No "next fire" analog exists: goals are not scheduled.

## Caching

`sess["goals"]` splits along the same line the loop code already established:

- Cacheable raw facts: objective, created_at, block/checkpoint counts, evidence.
  Add `"goals"` to `_CLAUDE_CACHE_FIELDS` and bump `CACHE_VERSION`.
- Never cached: Codex `status` (live DB), and any `state` derived from it.

Claude goal state, unlike loop state, does **not** age with wall-clock time.
There is no recurring fire to go stale, so `armed` stays `armed`. That means no
per-request recomputation for Claude, which is simpler than loops.

## Tests (`backend/test_goals.py`, mirroring `test_loops.py`)

1. Claude: arm parsed; condition truncated; duplicate arm across a compaction
   boundary collapses to one goal.
2. Claude: `tool_result` records quoting the markers produce zero goals.
3. Claude: block bursts grouped; `cap_hit` true at 8, false at 7.
4. Claude: state never `complete`, for any input.
5. Codex: row maps to a goal; `state_source == "reported"`; missing DB yields
   `[]`; locked DB yields `[]` and does not raise.
6. Codex: the DB with rows wins over the empty one regardless of which path it
   sits at, and a v1 DB (no `thread_goal_continuation_deferrals`) yields
   `deferrals: null` instead of raising.
7. Grok: toolset announcements in `updates.jsonl` produce zero goals; only real
   `tool_calls` count.
8. Grok: `completed:true` checkpoint yields `complete`, otherwise `active`.
9. Antigravity: marker parsed once despite `transcript`/`transcript_full`
   duplication.
10. Multi-goal session returns goals in creation order.
11. No agent emits a state outside its allowed set.

## Phasing

- **Phase 1 (highest value per unit work): Codex.** The data is already
  structured, already includes tokens and duration, and needs no inference. One
  reader plus the `GoalCard`.
- **Phase 2: Claude.** Most sessions, least evidence. Ships the `armed` /
  `blocked` / `unknown` honesty model and the attributed-turn cost.
- **Phase 3: Grok, then Antigravity.** Checkpoints, then the bare marker.

Rough effort: phase 1 half a day, phase 2 a day (the turn-attribution span is
the fiddly part), phase 3 half a day.

## Open questions

1. Does `/goal` in Claude Code write anything outside the transcript in newer
   versions? Verified today that it does not (no goal files, no DB under
   `~/.claude`), but the changelog mentions a live overlay with turns and
   tokens, so a future version may persist it. Re-check before phase 2.
2. Codex `token_budget` was null in the only local sample. Confirm the field
   populates when a budget is set explicitly, before building budget-vs-used UI.
3. Is Grok's goal feature on by default now, or still gated on the toolset flag?
   Affects how many users would see anything.
