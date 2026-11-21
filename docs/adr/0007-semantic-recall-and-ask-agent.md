# ADR-0007: Add opt-in local semantic search and an Ask agent to Recall

- **Status:** Proposed
- **Date:** 2026-11-21
- **Deciders:** Maintainer
- **Related:** [v1 design doc](../design/cross-harness-recall.md), [v2 design doc](../design/cross-harness-recall-v2.md), [ADR-0006](0006-cross-harness-recall-on-demand.md)

## Context

ADR-0006 chose lexical search over the parsed traces, with no model and no index. In use, it finds the right session for a keyword query but misses paraphrases. On a real project with 192 sessions, a keyword query put the right session first 79% of the time. A paraphrased version of the same question did so 26% of the time. Users who ask "why did we drop the queue" do not use the words the transcript used.

Users also want an answer, not a list of snippets. Reading five hits to assemble a sentence is the work they wanted to skip.

The constraints from ADR-0006 still hold: local-first, no new outbound calls by default, no new runtime dependencies, and transcript text is data, not instructions. TokenTelemetry is solo-maintained, so the design should reuse the summarizer backends it already ships rather than add a new model provider.

## Decision

We will add two features on top of the v1 search.

1. **Opt-in semantic search.** A local embedding model (EmbeddingGemma 2 through Ollama, truncated to 256 Matryoshka dimensions) embeds redacted chunks into a persistent SQLite index, built per project on request. Search can run in `keyword`, `semantic` or `hybrid` mode. Hybrid fuses the keyword and vector rankings with reciprocal rank fusion. Keyword stays the default mode. It changes only after the benchmark shows that hybrid improves paraphrase recall without lowering keyword recall.
2. **An Ask agent.** A ReAct loop answers a question about a project's history. TokenTelemetry owns the tools (search, read session) and drives the loop. The model is the summarizer the user already configured, called as plain text in and plain text out. Each run has a step limit, a time budget and cancellation when the client disconnects. Answers cite the sessions they used.

Both features are off until the user enables them. With semantic search off, v1 behavior is unchanged.

## Alternatives considered

- **Per-session digests.** Summarize each session once and search the digests. Rejected: one session often covers several topics, and a digest keeps only a few of them. Chunk-level embeddings keep every topic retrievable.
- **Single-shot retrieval-augmented generation.** Retrieve once, then ask the model once. Rejected: when the first query misses, nothing recovers. The loop lets the model refine the query, read a session in full and try again.
- **Embeddings only, no keyword.** Simpler ranking. Rejected: embeddings are weak on exact identifiers, error strings and file names, which keyword matching handles well. Hybrid keeps both.
- **MCP only, no Ask.** Leave the reasoning to the calling agent. Rejected as the only path: a dashboard user without an agent gets no answer, and the cost of many searches lands in the caller's session. MCP stays as the second surface, and its `search_sessions` tool gains the same `mode` argument.

## Consequences

- ✅ Paraphrased questions can find sessions that keyword search misses, measured by the benchmark before the default changes.
- ✅ The Ask agent gives a cited answer on the Recall page and works with any summarizer backend already in Settings, including CLI agents that run without tools.
- ✅ No new Python dependency. Vectors are float32 blobs in SQLite and scored in pure Python. `numpy` is used only when it is already importable.
- ✅ The Ask prompt, the evidence and the tool results go through the same redaction as v1 before any model sees them.
- ⚠️ Index build time and disk use grow with history. Each project is embedded once, and later builds skip sessions whose fingerprint has not changed.
- ⚠️ Semantic search needs a recent Ollama release and the model pulled locally. Ollama must listen on loopback. A remote Ollama URL is rejected.
- ⚠️ Each Ask question uses the user's model quota, up to six LLM calls and about three minutes. Cancellation stops further calls when the tab closes, but calls already in flight finish.
- ⚠️ Prompt injection remains a risk. Past-session text is fenced as untrusted data and CLI runs use no tools, but a model can still be steered by text it is told to trust. The fence is a convention the model must respect, not an enforced boundary.
- ⚠️ Ask sends redacted transcript excerpts to whichever summarizer the user configured. A hosted backend receives that text, so the "nothing leaves the machine" promise applies only to semantic search over Ollama.
- 🔁 Undoing the Ask agent means removing the `/recall/ask` route and the Ask tab. Undoing semantic search means dropping the vector tables and the Ollama settings. Either change should supersede this ADR. Replacing the embedding model changes the stored vectors and needs a rebuild. The index already ignores vectors from another model, so no migration is needed for that case.
