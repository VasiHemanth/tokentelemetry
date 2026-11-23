# ADR-0008: Index each project's non-code knowledge for semantic recall, with a model lock

- **Status:** Proposed
- **Date:** 2026-11-22
- **Deciders:** Maintainer
- **Related:** [v3 design doc](../design/cross-harness-recall-v3.md), [knowledge inventory](../design/recall-knowledge-inventory.md), [ADR-0007](0007-semantic-recall-and-ask-agent.md)

## Context

ADR-0007 added opt-in semantic search over session transcripts. Transcripts are only part of what an agent produces for a project. Skills, slash commands, agent definitions, plans, task lists, reports, published artifacts, instruction files and memory files often hold the decisions a user later wants to find. The inventory lists where 21 agents keep these, and most live outside the project directory.

Three facts shape the design.

- The user-level items (global skills, agents, commands, MCP servers) are shared across projects. Indexing all of them into every project would make search noisy and would leak configuration into projects that never used it.
- MCP server configuration holds tokens in `env`, `headers` and URL query strings. Those values must never reach an index or a model.
- Vectors from different models are not comparable. The index for a project has to hold one model only, and the app has to notice when the model changes. Ollama tags and cloud APIs both change behavior without changing a name the app can rely on: an Ollama digest can move under the same tag, and a gateway can route one slug to another model.

ADR-0007 also set the rule that nothing leaves the machine unless the user opts in. A cloud embedding API sends redacted text to a third party, so it needs its own opt-in, its own key storage and its own warning.

## Decision

We will index a project's non-code knowledge as typed documents, and we will lock each project's index to one embedding model.

1. **Document types.** Sessions, images, skills, commands, agent definitions, artifacts (plans, task lists, reports, published artifacts), Markdown files in the project, and MCP server entries are indexed as documents. Source code is never indexed. Files on each agent's never-index list (credentials, paste caches, file history, shell history, backup settings, `.env*`) are excluded.
2. **Scope.** Project-scope items under the project root are indexed. User-scope skills, agents, commands and MCP servers are indexed only when a session in that project used them, as recorded by the existing scan.
3. **MCP secrets.** Each MCP server is indexed as one rendered line of name, agent, scope, transport, command and tool names. `env`, `headers`, token-bearing arguments and URL query strings are dropped before rendering, so they never reach the embedder.
4. **Providers.** The default is the user's Ollama on loopback with `embeddinggemma-2:740m`. The alternative is a cloud embedding API in one of three formats (`openai`, `gemini`, `voyage`). Images are embedded by default for Ollama and off by default for APIs.
5. **Same-model lock.** Each project index stores a lock record (provider, model, endpoint host, dimensions, Ollama digest or returned model name, and the vector of a fixed probe text). The app checks the lock before indexing and reuses a recent check for semantic search. A mismatch moves the project to `model_changed`, where semantic search falls back to keyword and incremental indexing is refused until the user re-indexes everything.
6. **Storage.** Chunk vectors are keyed by the hash of the redacted, prefixed chunk text and shared across projects that use the same model. Removing a document or running a full re-index deletes that project's rows first and then garbage-collects vectors no row references. Vectors are never deleted by project.
7. **Indexing runs from Recall or project Activity.** A run starts only when the user opens a project and confirms. A delta check that reads no transcript text tells the user what is new or changed before any embedding happens.

## Alternatives considered

- **Index all user-scope items into every project.** Rejected: unrelated skills and MCP servers would match queries about a project they never touched, and the index would carry configuration the project never used.
- **Index source code too.** Rejected: code is large, changes on every commit, and is already searchable with the agent's own tools. Its embeddings would dominate the index without adding decisions or intent.
- **Allow mixed models per project and tag each vector with its model.** Rejected: a query vector from one model cannot rank vectors from another. Mixing would need per-model search passes and still hide quality differences between models.
- **Trust the model name and skip the probe.** Rejected: a name does not prove the same weights are behind it. The probe is one embedding per check, cached for ten minutes, so the cost is small.
- **Send images to cloud APIs by default.** Rejected: images cannot be redacted the way text is, so they would leave the machine with no filter.
- **Store API keys in the main settings file.** Rejected: the settings route returns the settings to the page, so a key stored there would be served back to the browser. The key lives in a separate file that no route returns.

## Consequences

- ✅ Searches cover what the user asked agents to produce and remember, not only chat, and user-level tooling appears only where it was used.
- ✅ A project's index never mixes vectors from two models, and a model change is visible instead of silently degrading results.
- ✅ Routine updates embed only new or changed items and only new chunk text, so a re-index costs roughly the changed part, which the banner estimates before the run.
- ✅ The MCP secret stripping is enforced before rendering, so a regression shows up as a missing field in a test rather than as a leaked token.
- ⚠️ Each index run checks the lock against the provider. Semantic searches can reuse that check for ten minutes.
- ⚠️ A cloud API receives redacted text for every indexed document. The "nothing leaves the machine" promise in the Recall docs applies only to the Ollama provider.
- ⚠️ Key storage is file-based. On macOS and Linux the file is mode 0600. On Windows, file modes do not restrict access, so the key is protected only by the user profile.
- ⚠️ Some providers do not return a model name in their responses, so for those the probe checks the vectors against the locked model and keeps incompatible generations from sharing stored vectors.
- 🔁 Undoing project-scope indexing means dropping the `documents` table rows for non-session types and the Markdown and MCP discoverers. Undoing the lock means removing the `locks` table and the probe check. Either change should supersede this ADR. Changing the default embedding model does not need a migration: every project becomes `model_changed` and is re-indexed once.
