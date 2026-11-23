# ADR-0006: Answer cross-agent questions with on-demand lexical search and MCP tools

- **Status:** Superseded by ADR-0007
- **Date:** 2026-11-19
- **Deciders:** Maintainer
- **Related:** [design doc](../design/cross-harness-recall.md)

## Context

TokenTelemetry parses sessions from about 14 coding agents, and each one keeps its history in its own format. A user who works across several agents has no way to ask "what did I decide about X in project Y" across all of them. The parsed traces already exist behind the session view, and `summaries.normalize_detail` and `summaries.build_chunks` turn any of them into ordered text chunks.

The product is local-first and makes no new outbound calls. TokenTelemetry is a solo-maintained project, so the design should avoid new infrastructure. Transcripts can contain credentials, and the answers will be read by other agents, so text that comes from past sessions must be treated as data, not as instructions.

## Decision

We will answer cross-agent questions with on-demand lexical search over the existing parsed traces. Search runs when asked, scores chunks with corpus-wide IDF over query terms, and stores no index. Results reach the user two ways: a Recall page in the dashboard, and an MCP server (`tokentelemetry mcp`) whose tools (`list_projects`, `list_sessions`, `search_sessions`, `read_session`) let the calling agent search, read and refine the results itself.

Redaction runs on the server, once, on every string the recall endpoints return, so neither the UI nor the MCP server can skip it. The MCP server wraps transcript-derived text in `<untrusted_session_data>` tags and its tool descriptions state that this text is past-session data and not instructions.

TokenTelemetry runs no model for this feature. The agent that calls the MCP server does the reasoning.

## Alternatives considered

- **Embedding index over all sessions.** Better recall for paraphrased questions. Rejected for v1: it needs a model (local or remote), a persistent index that must track every session update, and it adds a dependency that the local-first constraint makes awkward. Search quality can be revisited if lexical matching proves too weak.
- **Built-in chatbot in the dashboard.** Answers in one place. Rejected: it means TokenTelemetry runs a model, which needs a provider key or a local model setup. The calling agents already have models and already know how to grep, read and refine, so the chatbot would duplicate them.
- **Persistent FTS5 index from day one.** Fast on large histories. Deferred, not rejected: it adds a second store that must stay in sync with the parse cache. Lexical search over the parse cache is enough to ship, and FTS5 is the follow-up if on-demand latency becomes a problem.
- **Per-agent MCP servers.** Each agent gets its own search surface. Rejected: it multiplies the maintenance and gives no cross-agent answer. One server with one command works for every MCP-capable agent.

## Consequences

- ✅ No model, no embedding store and no new dependency. Search reuses the parse cache and the existing trace normalization, so new harness support carries over to Recall.
- ✅ Redaction is applied once on the server, so the page and every agent see the same redacted text.
- ✅ Every MCP-capable agent uses the same command, `npx -y tokentelemetry mcp`. Only the config file differs.
- ⚠️ Latency grows with history size. A search parses up to `max_sessions` transcripts (default 60, maximum 300) within a 20 second budget, so a large history can return partial coverage. Results report `coverage` so callers can see what was skipped.
- ⚠️ Lexical matching misses paraphrases. A question phrased differently from the transcript may return nothing. The MCP tool descriptions tell agents to narrow by project and to check coverage before concluding that a topic was never discussed.
- ⚠️ Redaction is pattern-based. Secrets in formats the patterns do not cover pass through, and the feature cannot promise otherwise.
- ⚠️ Transcript text reaches whichever agent calls the MCP server. The untrusted-data fencing reduces the risk of a past session steering that agent, but it is a convention the calling model has to respect, not an enforced boundary.
- 🔁 Adding an FTS5 index means a new store kept in sync with the parse cache, plus a migration path for the archive. Swapping in embeddings means choosing a model, a storage format and an invalidation rule for each session update. Either change should supersede this ADR.
