# Chat with sessions and projects

Status: step 1 shipped (custom prompt on a session summary). Steps 2 and 3 are
proposed.

## Why

A user who works across several coding agents discusses ideas in many sessions.
Claude Code can recall an earlier session from a later one, but only inside its
own history. TokenTelemetry already reads sessions from every supported agent, so
it can answer questions across agents: "where did we decide on the caching
approach?" without the user remembering which agent or day it was.

## Existing pieces

- `backend/summarizers/` runs one prompt through the user's chosen backend: an
  installed coding CLI (claude, codex, gemini, qwen, kimi, antigravity), ollama,
  or any OpenAI-compatible endpoint. No keys are shipped.
- `backend/summaries.py` condenses a trace into a small brief and caches results
  in `summaries.db`.
- Adapters accept a single prompt string. There is no separate system-prompt
  field, so a "system prompt" is a preamble inside that string.

## Steps

| Step | What | Needs |
| --- | --- | --- |
| 1. Custom prompt | Next to "Generate summary", a free-text prompt (with presets) runs over one session. Answers are cached per session and prompt. | Nothing new. Shipped. |
| 2. Session chat | Multi-turn chat about one session. History is kept client-side and replayed each turn. | A transcript retrieval step, see below. |
| 3. Project chat | Ask across all sessions in a project, across agents. Answers cite session, agent and date. | A local search index over session text. |

## Step 1 as built

- `POST /sessions/{id}/summary/custom?agent=` with `{prompt, force}`. Returns
  `{item, cached, error, error_info}`. `GET` on the same path lists stored items.
- The prompt is capped at 2000 characters. The model receives the standard brief
  plus up to 40 user and 40 assistant message excerpts (300 characters each).
- Cached in `custom_summaries` keyed by (session, prompt hash). An entry is
  reused only while the trace is unchanged, same rule as the standard summary.
- Errors go through `summarizers/errors.py::classify`, same as the standard
  summary. Disabled backend returns 409, empty prompt 422.
- The answer is rendered as Markdown with react-markdown (raw HTML is not
  interpreted).

Known limit: the model sees excerpts, not the full transcript, so questions about
detail that was cut will get "not in the material" answers. Step 2 addresses that.

## Open decisions for steps 2 and 3

**Getting content to the model.** Options: (A) brief only, (B) retrieval over an
indexed transcript, (C) the whole transcript. Recommended: B, using SQLite FTS5
over message text, with the top snippets plus the brief sent each turn. C breaks
on long sessions and makes project chat impossible. A is what step 1 does.

**Cost.** Chat through the claude or codex CLI spends the user's own quota on
every turn. The UI should say so and point to ollama or an OpenAI-compatible
endpoint as the cheap path.

**Privacy.** Project chat sends snippets from several agents' sessions to the
chosen backend. Fine for a local model; hosted backends need a visible warning
before the first project-level question.

**Indexing.** The index must update incrementally from the scanners and respect
the same ignore rules as the dashboard (including the summarizer's own sessions,
see `SUMMARIZER_CWD`). Build it lazily per project, not for all history up front.

**Citations.** Every project-level answer should link back to the session so the
user can verify it. Retrieval results carry session id, agent and timestamp for
this reason.

## Out of scope

No embedding model in the first version. Keyword search misses paraphrases, which
is an accepted cost until the keyword approach proves insufficient.
