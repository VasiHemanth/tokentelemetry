# Cross-harness recall

Search and read past sessions from every supported agent (Claude Code, Codex,
Antigravity, and the rest) as one corpus, grouped by project. Two consumers
share one backend:

1. **The Recall page** (`/recall` in the dashboard): a search box scoped to a
   project, with harness filters. Each hit links to its session trace.
2. **The MCP server** (`tokentelemetry mcp`): a stdio MCP server, so whichever
   agent you are in can ask "what did Codex decide about the render pipeline
   in education-video?" and do the searching itself (grep, read, refine).
   TokenTelemetry runs no model for this; the calling agent does the reasoning.

TokenTelemetry already parses every harness behind `get_session_detail`, and
`summaries.normalize_detail` + `summaries.build_chunks` turn any of those
traces into ordered text chunks. Recall adds cross-session scoring, a project
key that survives worktrees, redaction, and the two surfaces above.

## Non-goals (v1)

- No embeddings and no persistent full-text index. Search parses transcripts
  on demand through the existing parse cache. An FTS5 index is the follow-up if
  on-demand search turns out slow on large histories.
- No model calls and no new outbound network traffic.
- No new telemetry events.

## Project key

`recall.project_key(path)` is the grouping identity:

1. `canonical_project(path)` (from `tt_paths`), same as `/projects`.
2. Fold agent worktrees into their parent repo: strip a trailing
   `/.claude/worktrees/<name>`, `/.codex/worktrees/<name>` or
   `/.worktrees/<name>` segment.
3. The key is the resulting path. `name` is its basename.

`ANTIGRAVITY_UNASSIGNED` and empty projects get key `null` and are only found
by a search with no project filter.

A `project` request parameter matches a key when it equals the key, or equals
its basename case-insensitively, or (fallback) is a case-insensitive substring
of the basename. So `project=education-video` and `project=/Users/dev/code/education-video` both work.

## Transcript loading and limits

For each candidate session the loader tries, in order:

1. **live**: `get_session_detail(id, agent)` → `normalize_detail` (Codex goes
   through `_canonicalize_codex_trace` as the endpoint already does).
2. **archive**: `history_store.get_transcript(agent, id)`. Claude and Codex
   blobs are raw JSONL, parsed line by line into events.

Every hit carries `source: "live" | "archive"`.

Chunking differs from summaries in two ways:

- **Codex records are adapted first.** Codex rollouts store turns as
  `response_item` records (`message`, `function_call`, `*_output`,
  `reasoning`), which `build_chunks` does not read; without
  `recall.codex_to_message_events` a Codex trace yields zero chunks.
  `developer` messages and injected context (AGENTS.md, environment context)
  are skipped.
- **Tool results keep up to 8,000 characters** (`recall.RESULT_CHARS`)
  instead of their first line, so file paths in `ls`/`grep` output are
  searchable. Summaries keep the one-line default.

A session that loads but yields no chunks (an empty Antigravity session, for
example) counts as `unreadable`, never as scanned.

Limits, all reported back in `coverage`:

- Candidates are sorted newest first (by last timestamp). At most
  `max_sessions` (default 60, hard max 300) are opened.
- A transcript whose chunk list exceeds 20,000 chunks is truncated to its last
  20,000 and counted in `coverage.truncated`.
- Loading runs in a worker thread (`asyncio.to_thread`); a total wall-clock
  budget of 20 s stops opening new sessions and sets `coverage.timed_out`.

## Scoring

Query terms use `summaries._tokens` (lowercase, stopwords removed). A chunk's
score is the sum of `log(1 + N / df[t])` over distinct query terms it contains,
with `N` and `df` computed across all chunks of all opened sessions (corpus-wide
IDF, so a term that appears everywhere counts for little). A quoted phrase in
the query (`"render pipeline"`) is required verbatim (case-insensitive) in the
chunk. Hits are sorted by score desc, then newest session first.

## Redaction

`backend/redact.py::redact(text) -> str` runs on **every** string the recall
endpoints return (snippets, turns, titles, first prompts). It replaces secrets
with `[REDACTED:<kind>]`. Kinds at minimum: `aws_access_key`, `github_token`
(ghp_/gho_/ghu_/ghs_/ghr_/github_pat_), `anthropic_key` (sk-ant-), `openai_key`
(sk-… / sk-proj-…), `slack_token` (xox[abprs]-), `google_api_key` (AIza…),
`stripe_key` (sk_live_/rk_live_), `jwt`, `private_key` (PEM blocks),
`bearer` (`Authorization: Bearer …`), `url_credentials` (`scheme://user:pass@`),
and `assignment` (`password=`, `secret:`, `api_key=`, `token=` style key/value
with a value of 8+ chars). Redaction is applied server-side once, so the UI
and the MCP server can never forget it.

## HTTP API

All routes are `GET`, return JSON, and sit behind `RemoteAuthMiddleware` like
every other route (loopback exempt, remote needs the token). Errors use FastAPI's
`{"detail": "..."}` with 400 (bad params), 404 (unknown session).

### `GET /recall/projects`

Query: none.

```json
{
  "projects": [
    {
      "key": "/Users/dev/code/education-video",
      "name": "education-video",
      "agents": ["antigravity", "claude", "codex"],
      "session_count": 42,
      "cost": 12.34,
      "last_ts": "2026-11-18T09:12:00Z"
    }
  ]
}
```

Sorted by `last_ts` desc. `agents` sorted. `cost` sums `cost` + `delegated_cost`
(None counts as 0).

### `GET /recall/sessions`

Query: `project` (optional), `agent` (optional, comma-separated list),
`since` (optional ISO date or datetime), `limit` (default 50, max 500).

```json
{
  "project": {"key": "/Users/dev/code/education-video", "name": "education-video"},
  "sessions": [
    {
      "agent": "codex",
      "id": "019a…",
      "project_key": "/Users/dev/code/education-video",
      "project": "education-video",
      "title": "first user prompt, redacted, max 160 chars",
      "model": "gpt-5.5",
      "start_ts": "2026-11-17T08:00:00Z",
      "last_ts": "2026-11-17T09:30:00Z",
      "tokens": 182340,
      "cost": 1.92,
      "source_present": true
    }
  ],
  "total": 42
}
```

`project` is `null` when no filter was given or nothing matched. `total` is the
count before `limit`.

### `GET /recall/search`

Query: `q` (required, 1–300 chars), `project` (optional), `agent` (optional,
comma-separated), `since` (optional), `limit` (hits, default 20, max 100),
`max_sessions` (default 60, max 300).

```json
{
  "query": "render pipeline",
  "project": {"key": "/Users/dev/code/education-video", "name": "education-video"},
  "hits": [
    {
      "agent": "claude",
      "id": "5f0c…",
      "project": "education-video",
      "title": "…",
      "model": "claude-opus-5-5",
      "last_ts": "2026-11-16T10:00:00Z",
      "cost": 3.10,
      "turn": 7,
      "kind": "assistant",
      "snippet": "…matching chunk text, redacted, max 600 chars…",
      "score": 8.41,
      "source": "live"
    }
  ],
  "by_agent": {"claude": 6, "codex": 3, "antigravity": 1},
  "coverage": {
    "candidates": 42,
    "sessions_scanned": 42,
    "sessions_skipped": 0,
    "skipped_reason": null,
    "unreadable": 0,
    "truncated": 0,
    "timed_out": false,
    "agents_scanned": ["antigravity", "claude", "codex"]
  }
}
```

`kind` is one of `user`, `assistant`, `tool`, `result` (from `build_chunks`).
`by_agent` counts hits before `limit`. `skipped_reason` is `"max_sessions"`,
`"timeout"`, or `null`.

### `GET /recall/session/{agent}/{session_id}`

Query: `offset` (turn index to start at, default 0), `limit` (max chunks,
default 80, max 400), `kinds` (optional comma list of chunk kinds).

```json
{
  "agent": "codex",
  "id": "019a…",
  "project": "education-video",
  "title": "…",
  "model": "gpt-5.5",
  "cost": 1.92,
  "source": "live",
  "total_chunks": 312,
  "offset": 0,
  "next_offset": 80,
  "chunks": [
    {"idx": 0, "turn": 1, "kind": "user", "text": "…redacted…"}
  ]
}
```

`offset` here is a chunk index (`idx`). `next_offset` is `null` at the end.

## MCP server (`tokentelemetry mcp`)

`bin/mcp.js`, dispatched from `bin/cli.js` as the `mcp` verb. No new npm
dependencies: newline-delimited JSON-RPC 2.0 over stdio, Node's built-in
`fetch`. Stdout carries protocol messages only; all logging goes to stderr.

Handles `initialize` (echo the client's `protocolVersion`, advertise
`tools`), `notifications/initialized` (no reply), `ping`, `tools/list`,
`tools/call`. Unknown methods get JSON-RPC error -32601.

Backend discovery: `--api-port` flag, else `TT_API_PORT`, else probe
`127.0.0.1:18000` then `127.0.0.1:8000` with `GET /version`. Loopback only.
If `TT_AUTH_TOKEN` is set it is sent as `Authorization: Bearer`. If no backend
answers, tool calls return an MCP tool error (`isError: true`) saying to start
TokenTelemetry (`npx tokentelemetry`) rather than crashing.

Tools (each maps 1:1 to an HTTP route above):

| Tool | Route | Required args |
|---|---|---|
| `list_projects` | `/recall/projects` | none |
| `list_sessions` | `/recall/sessions` | none (`project`, `agent`, `since`, `limit` optional) |
| `search_sessions` | `/recall/search` | `query` |
| `read_session` | `/recall/session/{agent}/{id}` | `agent`, `session_id` |

Tool results are text content. Transcript-derived text (snippets, chunks,
titles) is wrapped in `<untrusted_session_data>…</untrusted_session_data>`
with any inner occurrence of that tag stripped, and the tool descriptions say
the content is data from past sessions, never instructions. The
`search_sessions` description tells the agent to narrow by `project` first and
to read `coverage` before concluding something was never discussed.

## Agent setup

Every MCP-capable agent runs the same command, `npx -y tokentelemetry mcp`.
The docs page (`website/content/docs/features/recall.mdx`) has the config
snippet for each one: Claude Code (`claude mcp add`), Codex
(`~/.codex/config.toml` `[mcp_servers.tokentelemetry]`), Antigravity and
Gemini CLI (`mcp_config.json` / `settings.json` `mcpServers`), Cursor
(`~/.cursor/mcp.json`), OpenCode, Kimi, Qwen Code, and a generic stdio block
for anything else.
