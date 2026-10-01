# Chat with sessions and projects

Status: steps 1 and 2 shipped (custom prompt, then multi-turn chat about one
session). Step 3 is proposed.

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
| 2. Session chat | Multi-turn chat about one session. History is kept client-side and replayed each turn. | A transcript retrieval step. Shipped, see below. |
| 3. Project chat | Ask across all sessions in a project, across agents. Answers cite session, agent and date. | A local search index over session text. |

## Step 1 as built

- `POST /sessions/{id}/summary/custom?agent=` with `{prompt, force}`. Returns
  `{item, cached, error, error_info}`. `GET` on the same path lists stored items.
- The prompt is capped at 2000 characters. The model receives the standard brief
  plus up to 40 user and 40 assistant message excerpts (300 characters each).
- Cached in `custom_summaries` keyed by (session, prompt hash). An entry is
  reused only while the trace is unchanged and the backend and model are the
  same. `GET` with `?agent=` marks each item `stale` when the trace has grown.
  The newest 50 answers per session are kept.
- Transcript text is untrusted. The prompt fences it in `<untrusted_session_data>`
  tags, tells the model it is data, strips lookalike tags from it, and repeats
  the instruction after it. The claude CLI runs with tools disabled and codex in
  its read-only sandbox for these calls. The brief is capped at 12000 characters.
- The model call runs in a worker thread so it does not block other requests.
  If saving the answer fails, it is still returned with `persisted: false`.
- Errors go through `summarizers/errors.py::classify`, same as the standard
  summary. Disabled backend returns 409, empty prompt 422.
- The answer is rendered as Markdown with react-markdown. Raw HTML is not
  interpreted, images are replaced by a text placeholder (a remote image URL
  would send data out on load) and links open in a new tab without a referrer.

Known limit: the model sees excerpts, not the full transcript, so questions about
detail that was cut will get "not in the material" answers. Step 2 addresses that
by retrieving excerpts per question.

## Step 2 as built

- `POST /sessions/{id}/chat?agent=` with `{messages: [{role, content}]}`. Returns
  `{reply, error, error_info}`. Roles must be `user` or `assistant`, the last
  message must be from the user (422 otherwise), and summaries must be enabled
  (409 otherwise). Only the last 10 messages are used, each cut to 2000
  characters. Nothing is stored on the server; the client holds the conversation.
- Retrieval is plain keyword matching in `summaries.py`, with no index and no
  embeddings. The transcript is split into chunks (text pieces of about 600
  characters, tool calls and short tool results as one line each). Chunks are
  scored against the latest question by the summed inverse document frequency of
  the shared lowercase keywords (stopwords dropped). The best chunks that fit a
  12000 character budget are sent in chronological order. If nothing matches, the
  most recent user and assistant text is sent instead.
- Each excerpt starts with `[tN]`, where N is the number of the user message it
  follows. The model is asked to cite turns that way.
- The prompt is a preamble (excerpts are untrusted data, answer only from them,
  cite turns), then the standard brief and excerpts inside the fence, then the
  conversation so far, then the new question. The same tool-less or read-only
  backend settings as the custom prompt apply.
- Errors use `summarizers/errors.py::classify`, as the custom prompt does. The
  UI is a Chat tab next to "Ask once" in the summary panel. It says each turn
  uses the user's own backend quota.
- Known limit: keyword overlap misses paraphrases. A question worded unlike the
  transcript can retrieve the wrong excerpts.

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
