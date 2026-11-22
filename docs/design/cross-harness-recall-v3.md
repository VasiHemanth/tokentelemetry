# Cross-harness recall v3: project knowledge index

Builds on v1 (keyword recall, MCP server) and v2 (vector store, hybrid search,
Ask agent). v3 makes semantic search real and broad:

- **Everything an agent produced or was given for a project**, not only chat:
  sessions, images, skills, commands, agent definitions, artifacts and plans,
  Markdown files, MCP server configuration. Never source code. Where each
  agent keeps these: [recall-knowledge-inventory.md](recall-knowledge-inventory.md).
- **Providers.** Default: the user's Ollama with `embeddinggemma-2:740m`
  (text and images, 1.3 GB, one-click pull). Alternative: a cloud embedding
  API the user configures (endpoint, key, model).
- **Same-model lock.** A project's index only ever holds vectors from one
  model; a change is detected and forces an explicit re-index.
- **Indexing happens on the Recall page,** when the user opens a project and
  confirms, with a live animation drawn from real indexing events.
- **Capability check** with a plain-English note when the machine cannot do it.

Runtime facts this relies on: [recall-embedding-runtime.md](recall-embedding-runtime.md).

## 1. Settings and secrets

`data_dir()/recall.json` (v2 file, extended; v2 keys keep working):

```json
{
  "semantic": {
    "enabled": false,
    "provider": "ollama",
    "ollama": {"url": "http://127.0.0.1:11434", "model": "embeddinggemma-2:740m"},
    "api": {"format": "openai", "endpoint": "https://api.openai.com/v1/embeddings", "model": "text-embedding-3-small"},
    "dims": 256,
    "images": true,
    "default_mode": "hybrid"
  }
}
```

- `provider`: `ollama` | `api`.
- `api.format`: `openai` (OpenAI and every OpenAI-compatible endpoint: Jina,
  Mistral, OpenRouter, LiteLLM, vLLM, LM Studio) | `gemini` (Gemini
  `embedContent`, supports images) | `voyage` (Voyage multimodal).
- `api.endpoint` must be `https://`, or `http://` on loopback.
- The API key lives in `data_dir()/recall_secrets.json`, file mode 0600 on
  macOS/Linux (on Windows chmod does not restrict access; the file relies on
  the user profile's permissions and the docs say so), written only by
  `PUT /recall/settings` and never returned by any route.
  GET returns `"api_key_set": true|false` only.
- `images`: embed images. Default `true` for `ollama`, forced `false` for
  `api` unless the user turns it on (images cannot be redacted and would leave
  the machine).
- Ollama `url` keeps the v2 loopback-only rule.
- `dims`: 128 | 256 | 512 | 768 (Matryoshka truncate, then re-normalize). For
  `api` providers that accept a dimension parameter it is sent; otherwise the
  returned vector is truncated client-side only if the provider documents
  Matryoshka support, else `dims` must equal the native size and the UI says so.

## 2. Embedding providers

`backend/recall_embed.py`. One interface:

```python
class Embedder:
    identity: dict          # provider, model, endpoint_host, dims, format
    supports_images: bool
    def embed_texts(self, texts, kind) -> List[List[float]]   # kind: "query" | "document"
    def embed_images(self, images: List[bytes]) -> List[List[float]]
    def lock_evidence(self) -> dict  # see section 3
```

- Text prefixes (EmbeddingGemma): query `task: search result | query: {q}`;
  document `title: {title} | text: {content}` with the real document title
  (session title, skill name, file name) or `none`. Other models get no
  prefix unless the format requires `input_type` (Voyage `query`/`document`).
- Images: Ollama `{"image": "<base64>"}` inputs to `/api/embed`; Gemini
  `inline_data`; Voyage `image_base64`. `openai` format never gets images.
- Every vector is truncated to `dims` and L2-normalized before it leaves the
  embedder.
- Errors raise `EmbedError` with a plain-English message and fix (Ollama not
  running, model missing, 401 bad key, 429 rate limited, 413 too large).
- Batching: 32 texts per call for Ollama, provider limits for APIs; retries
  with backoff on 429/5xx (max 3), never on 4xx auth errors.
- No new dependencies (urllib).

### Ollama setup

- `GET /recall/setup` returns capability (section 6) plus provider status.
- `POST /recall/setup/pull` streams Ollama `/api/pull` progress as NDJSON:
  `{"status", "completed", "total", "percent"}` then `{"status": "success"}`
  or `{"type": "error", ...}`. Only on an explicit user click. Refuses when
  Ollama is too old (registry 412) with the update message.

## 3. Same-model lock

Each project index has a lock record:

```json
{"provider": "ollama", "model": "embeddinggemma-2:740m", "endpoint_host": "127.0.0.1:11434",
 "dims": 256, "returned_model": null, "ollama_digest": "sha256:…",
 "probe": [0.0123, …], "created_at": "…"}
```

- `probe` is the embedding of the fixed text
  `TokenTelemetry recall probe: the quick brown fox checks the index model.`
  (document kind) taken when the index is created.
- **Check** (fresh before any index run, cached for up to 10 minutes for
  semantic search): same provider, model, endpoint, API format, dims; Ollama
  digest equal (from `/api/tags`); API `returned_model` equal when the
  provider returns one; and the fresh probe vector has cosine >= 0.999 with
  the stored one.
- **On mismatch** the project's index state becomes `model_changed`: semantic
  and hybrid search fall back to keyword (coverage says why), indexing refuses
  incremental updates, and the UI offers "Re-index everything with <new
  model>", which deletes that project's vectors and lock first.
- When Ollama gives no digest, the probe is part of the shared-vector key so a
  provider alias that changes models cannot reuse vectors from another project.
- Changing provider/model/dims in settings never mixes vectors: every
  project whose lock differs becomes `model_changed`.

## 4. Documents

Every indexed thing is a document:

```json
{"doc_id": "skill:claude:user:bug-audit", "project_key": "…", "type": "skill",
 "agent": "claude", "scope": "user|project", "title": "bug-audit",
 "source": {"kind": "file", "path": "~/.claude/skills/bug-audit/SKILL.md"} | {"kind": "session", "id": "…"},
 "mtime": 1763700000.0, "size": 4120, "fingerprint": "sha256…"}
```

Types: `session`, `image`, `skill`, `command`, `agent`, `artifact` (plans,
task lists, walkthroughs, reports, published artifacts), `markdown`
(instruction files, memory files, and the project's own `*.md`), `mcp`.

- **Discovery** (`backend/recall_sources.py`) follows the inventory doc, one
  discoverer per agent, each returning documents for a project. Missing paths
  are skipped silently and counted; unverified layouts never raise.
- **Project link:** project-scope paths live under the project root.
  User-scope items (global skills, agents, commands, MCP servers) are included
  only when a session in this project used them, using what the scan already
  records per session (`skills_used`, `mcp_tools`, `subagents`, slash commands
  in transcripts).
- **Project `*.md`:** walk the project root for `*.md`/`*.mdx` with
  `followlinks=False` (never follow symlinks, never leave the root),
  skipping `.git`, `node_modules`, `vendor`, `dist`, `build`, `.next`,
  `target`, `.venv`/`venv`, nested agent worktrees (`.claude/worktrees`,
  `.codex/worktrees`, `.grok/worktrees`, `.worktrees`) and any directory in
  `.gitignore` when cheap to read; max 2,000 files and 1 MB per file, counted
  when skipped.
- **Never index:** the inventory's never-index list (credentials, paste
  caches, file history, shell history, backup settings, `.env*`), and any
  source code file.
- **MCP:** one document per server per config file: rendered text
  `MCP server <name> (<agent>, <scope>): transport <t>, command <cmd>, tools: …`.
  `env`, `headers`, token-bearing `args` and URL query strings are dropped
  before rendering.
- **Images:** inline base64 image blocks in transcripts and image files the
  inventory lists (screenshots, generated media), up to 8 MB each; only when
  `images` is on and the embedder supports images. Each image document's
  `title` is the session title or file name; it links back to its session.
- Text documents are chunked with the same 600-char splitter as sessions,
  redacted (`redact` + `mask_key_continuations`) before embedding.

## 5. Index store, reuse and delta

Extends the v2 SQLite store (`recall_index.db`, schema version bump with a
migration that keeps v2 session vectors only if their lock matches):

- `locks(project_key PRIMARY KEY, lock_json, state, updated_at)`;
  `state` in `ready`, `model_changed`, `building`.
- `documents(project_key, doc_id, type, agent, scope, title, source_json,
  mtime, size, cheap_fp, content_fp, chunks, indexed_at, PRIMARY KEY(project_key, doc_id))`.
  Two fingerprints with different jobs, never compared with each other:
  `cheap_fp` is what delta can compute without reading content (files:
  mtime + size; sessions: the scan's `last_ts` + token totals + message
  count); `content_fp` is the sha256 of the redacted chunk texts, used by the
  query-time staleness check. Index runs write both. Index then delta must
  report `up_to_date`.
- `chunk_vectors(lock_id, chunk_hash, dim, vec, PRIMARY KEY(lock_id, chunk_hash))`:
  vectors keyed by the sha256 of the redacted, prefixed chunk text, so an
  unchanged chunk is never embedded twice (sessions only grow; a re-index
  embeds only the new tail). `lock_id` is a hash of the lock identity.
- `doc_chunks(project_key, doc_id, idx, lock_id, chunk_hash)` maps document
  chunk positions to vectors.
- **Shared vectors, counted deletion.** Projects on the same model share
  `chunk_vectors` rows. Removing a document, or a project's `full` re-index,
  deletes only that project's `doc_chunks`/`documents` rows, then
  garbage-collects `chunk_vectors` rows no `doc_chunks` row references
  (same transaction). Never delete `chunk_vectors` by project.
- Query-time staleness check from v2 stays: a document whose current
  fingerprint differs from `documents.fingerprint` serves keyword only.

### Delta (cheap, no embedding)

`GET /recall/index/delta?project=…` compares discovered documents (paths,
mtimes, sizes, session fingerprints) with `documents`:

```json
{"state": "never_indexed" | "up_to_date" | "stale" | "model_changed" | "unavailable",
 "last_indexed_at": "…", "lock": {"model": "…", "provider": "…"},
 "new":     {"session": 4, "image": 2, "skill": 1, "command": 0, "agent": 0, "artifact": 3, "markdown": 1, "mcp": 0},
 "changed": {"session": 2},
 "removed": {"artifact": 1},
 "new_chunks_estimate": 412, "estimate_seconds": 38.0}
```

Must return in under 2 s for a 300-session project (no transcript parsing:
session fingerprints come from the scan's per-session `last_ts` + token
totals, not chunk text; exact chunk diffing happens during the run).

## 6. Capability

`backend/recall_capability.py` (exists). `GET /recall/capability?project=…`
returns its `assess()` verdict. The speed test runs only after the user asks
for it (`sample_project=true`) and the Ollama model is installed. It uses up to
32 redacted chunks from the project; for `api` providers there is
no local check beyond reachability (`status` from a 1-item test call) and the
estimate uses the API's measured latency.

## 7. Index run and live events

`POST /recall/index {"project": "…", "full": false}` starts the run (one at a
time; 409 with status when busy; `full: true` drops the project's vectors and
lock first). `GET /recall/index/events?since=<seq>` streams NDJSON of the
current run (and replays from `since` so a reloaded page catches up):

```json
{"seq": 1, "type": "start", "project": {…}, "totals": {"documents": 380, "by_type": {…}}}
{"seq": 2, "type": "doc", "doc_id": "…", "doc_type": "skill", "agent": "claude", "title": "bug-audit", "chunks": 6, "reused": 4, "xy": [0.41, -0.77]}
{"seq": 3, "type": "vector", "doc_id": "…", "doc_type": "skill", "preview": [0.12, -0.03, …24 values], "xy": [0.41, -0.77]}
{"seq": 4, "type": "progress", "documents_done": 12, "chunks_embedded": 140, "chunks_reused": 610, "tokens": 18210, "per_sec": 46.2, "by_type": {…}, "by_agent": {…}}
{"seq": 99, "type": "done", "elapsed_s": 41.2, "summary": {…}}
{"seq": 99, "type": "error", "message": "…", "fix": "…"}
```

- `preview`: the first 24 values of a real vector. `xy`: the vector projected
  to 2D with a fixed seeded random projection (deterministic per lock, so the
  same document lands in the same place across runs and similar documents
  cluster), scaled to [-1, 1].
- Rate: at most ~40 `vector` previews per second, with a map coordinate on
  every document event. Progress events report exact counters up to four times
  a second. `GET /recall/index/map?project=…` restores the map from the index.
- Text in `doc` events is the redacted title only, never content.

## 8. Search and Ask

- `/recall/search` gains `types` (comma list of document types; default all)
  and returns non-session hits with `doc_type`, `doc_id`, `title`, `path`
  (display path with `~`), `agent`, and `session_id` for images that came
  from a session. Session hits keep the v1 shape plus `doc_type: "session"`.
- `GET /recall/document/{doc_id}?project=…` returns the redacted text chunks
  of a non-session document (paged like `/recall/session`), or for an image
  `{"type": "image", "url": "/recall/document/<id>/image"}` (served
  token-gated). The image route serves bytes only when the document is in
  the index AND belongs to the requested project; images cannot be
  redacted, so this check is the only protection.
- Ask agent: `search` gains an optional `types` argument; new tool
  `read_document {"doc_id"}`; evidence labels cover documents (`D1…`) as well
  as sessions (`S1…`); citations link to sessions, files and images. Scope
  rules from v2 apply (only documents of the user's project and agents).
- MCP `search_sessions` gains `types`; new MCP tool `read_document`.

## 9. UI (Recall and project activity pages)

- **On project select:** call delta. Show a banner:
  - `never_indexed`: "Index this project" with what will be embedded and the
    estimate.
  - `stale`: "142 new chunks, 3 new skills, 2 images since Nov 18. Re-index
    (~40 s)".
  - `model_changed`: "This project was indexed with <old model>. Re-index
    everything with <new model>".
  - `up_to_date`: a quiet "Indexed Nov 21 with embeddinggemma-2:740m".
- **Setup card** (first time, from Embedding setup, or under Manage index on
  the project Activity page): Local (Ollama, the
  default) with capability verdict and "Download model (1.3 GB)" button
  streaming pull progress; or API (format, endpoint, model, key, dims, the
  plain warning that text leaves this machine, image toggle off by default).
- **Note "What gets embedded"** (always visible near the banner):
  - Only projects you turn on. Nothing is embedded for projects you never
    enable.
  - Only these content types: sessions, images, skills, commands, agents,
    artifacts/plans, .md files, MCP config. Never source code.
- **Capability note** when `blocked` / `slow` / `unknown`: the reasons and
  fixes from `assess()`; "Index anyway" for `slow`; names the host when the
  backend is remote.
- **Indexing animation** (from `/recall/index/events`): document cards fly in
  with type and agent icons and real titles; each breaks into token chips
  that collapse into a vector strip drawn from `preview`; the vector lands as
  a dot at `xy` on a live project map colored by document type; live
  counters (documents, chunks embedded vs reused, tokens, per second, by
  type, by agent); samples cards when events outpace the animation but keeps
  counters and map exact; canvas-based for speed; `prefers-reduced-motion`
  shows counters and a static map only. Ends with a summary and the map stays
  as a browsable "project knowledge map" (hover a dot for its title).
- Search results and Ask citations render document types with icons; file
  citations open a side drawer with the redacted text; image citations show
  the thumbnail.

## 10. Tests (minimum)

Providers (fake HTTP servers for Ollama and each API format), lock
mismatch paths (digest, returned model, probe cosine, dims), secrets file
mode and never returned, discovery per agent against fake home and project
trees built in `tmp_path` (including never-index files and MCP secret
stripping), chunk-hash reuse (second run embeds only new chunks), delta
speed and counts, event stream order/sampling/exact counters, search
`types`, Ask `read_document` and document citations, scope enforcement.

## Live retrieval benchmark

A local video-production project was indexed with EmbeddingGemma 2 740M,
256 dimensions, and Ollama 0.40.16. The final index held 189 sessions,
62 artifacts, 68 images, 67 Markdown documents, and 16 skills. Of 208
candidate sessions, 19 were unreadable. Eight images were also unreadable.

The original benchmark supplied 34 exact-word queries and 34 paraphrases
across 23 target sessions. Twenty-eight of the 34 labelled targets were
present in the new index. All modes used the same warmed project snapshot
and all requests scanned the 189 readable sessions within the time budget.

| Mode | Exact first | Exact top ten | Paraphrase first | Paraphrase top ten |
| --- | ---: | ---: | ---: | ---: |
| Keyword | 22/34 | 25/34 | 9/34 | 20/34 |
| Semantic | 20/34 | 27/34 | 11/34 | 25/34 |
| Hybrid | 22/34 | 25/34 | 13/34 | 26/34 |

Hybrid preserved first-place exact retrieval and improved paraphrase
retrieval. It is the default when semantic search is enabled and no mode
preference was saved. Keyword stays the default with semantic search off.

The supplementary benchmark scored the first expected result in the top ten returned
hits from `/recall/search`. It used the same queries and type filters for
each mode and deduplicated repeated hits for a session or document.

| Queries with a correct top-ten hit | Keyword | Semantic | Hybrid |
| --- | ---: | ---: | ---: |
| Exact session phrases | 3/3 | 3/3 | 3/3 |
| Session paraphrases | 2/3 | 2/3 | 3/3 |
| Skills | 0/2 | 2/2 | 2/2 |
| Artifacts and plans | 0/2 | 2/2 | 2/2 |
| Images described by their role in the video | 0/2 | 0/2 | 0/2 |
| Images described by visible content | 0/2 | 2/2 | 2/2 |

Keyword searches session text, so the document rows measure additional
retrieval coverage. Image search found both visually described targets
and missed both generic descriptions. An explicit non-session type filter
uses hybrid if the request leaves the mode unspecified.

A separate smoke test embedded two text queries and two generated color
squares. All four vectors were unit length at 256 dimensions. Each query
scored its matching square above the other, and the real provider also
indexed, retrieved, and rendered an inline image in a browser fixture.
