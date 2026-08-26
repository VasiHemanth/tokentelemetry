# Local model runtimes + TokenTelemetry's own store — survey

Scope: `~/.ollama`, `~/.lmstudio`, `~/.cache/huggingface`, `~/.tokentelemetry`.
Security note: no credential/token/private-key VALUES are reproduced below;
files that hold them are named and their key names given, values elided. No
user prompt text is quoted verbatim.

---

## Ollama — `~/.ollama`, 149G, ~3500 files (99% in `models/blobs`, excluded from traversal)

**What is it / still active?** Yes — actively used. Latest `logs/server.log`
timestamp 2026-08-25 22:04 (today). Two Ollama versions observed across
rotated logs in the same window: 0.32.13 and 0.32.14 (app auto-updated
mid-session). `models/manifests` has 14 model:tag entries, oldest pulled
2025-09-22, newest 2026-08-17.

### Directory map
```
~/.ollama
├── id_ed25519            # private key, <redacted> — Ollama node identity for ollama.com push/pull
├── id_ed25519.pub         # matching public key (not secret, but not printed here either)
├── config.json            # {"integrations":[...], "last_selection":...} — app-level small state
├── history                 # plaintext, one CLI prompt per line — `ollama run` REPL history (last ~100 lines kept)
├── backup/                 # timestamped snapshots of config.json (5 kept) + one opencode/model.json snapshot
│   └── opencode/model.json.<ts>   # opencode CLI's own "recent model" list — cross-harness leak into ollama's backup dir, not ollama data itself
├── cache/
│   └── model-recommendations.json  # cloud model catalog cache (model, description, context_length, max_output_tokens, required_plan) — CLOUD models only, not local
├── launch/
│   └── dsh/                # config for a separate "dsh" agent launcher (groq/deepseek routing, onboarding state) — tangential, not core ollama data
├── logs/                   # rotated: server.log + server-1..5.log, app.log + app-1..5.log (6 generations = 6 most recent app restarts)
│   ├── server.log          # Go structured logs + embedded GIN HTTP access log (see below) — THE request log
│   └── app.log             # tray/updater app lifecycle (starting Ollama, tools registry init)
└── models/
    ├── manifests/registry.ollama.ai/library/<model>/<tag>   # 14 small JSON files — the real inventory
    └── blobs/               # 149G, NOT enumerated (per instructions) — content-addressed sha256 blobs
```

### Store inventory
| Path | Format | What it holds | Cadence | Retention/cleanup | Coverage |
|---|---|---|---|---|---|
| `models/manifests/**` | JSON (OCI-image-manifest shaped) | Per model:tag — config blob digest + layer list (digest, size, mediaType, optional `name`) | Written on pull, mtime = last pull/update | No cleanup; manifest deleted on `ollama rm` | **NEW** |
| `id_ed25519` / `.pub` | OpenSSH key | Ollama's per-machine identity (signs registry pushes) | Created once (Mar 2024) | Persistent | NEW (existence only, structural) |
| `history` | plaintext, newline-delimited | Ollama CLI REPL prompt history (`ollama run` interactive session inputs) | Appended per REPL line | Trimmed to recent window (~100 lines seen) | **NEW** |
| `config.json` | JSON | `integrations`, `last_selection` | Written on settings change | 5 dated backups kept in `backup/` | NEW, low value |
| `cache/model-recommendations.json` | JSON | Cloud-catalog recommendation list (model, context_length, max_output_tokens, required_plan) — refreshed from ollama.com, **not local model data** | Periodic background refresh (fails offline, seen in logs) | Overwritten each refresh | NEW, low value (cloud only) |
| `logs/server*.log`, `logs/app*.log` | Go `log/slog` text + embedded Gin access-log lines | Server startup/env dump, GPU/VRAM detection, default-context derivation, and **every HTTP request**: method, path, status, latency, remote addr | Real-time, one line per event/request | Rotates on app restart; only 6 generations kept (≈15 days of history observed: Aug 10–25) | **NEW** |
| `launch/dsh/*.yaml` | YAML | Config for a co-installed "dsh" agent-launcher tool (cloud model routing via Ollama's OpenAI-compat endpoint) | On dsh config change | n/a | Tangential — not ollama's own data |
| `backup/opencode/model.json.<ts>` | JSON | opencode CLI's "recently used models" list (providerID/modelID pairs, spans ollama + github-copilot + opencode providers) | Snapshotted alongside config.json backups | 1 seen | Tangential cross-harness leak |

### Schemas

**Manifest** (`models/manifests/registry.ollama.ai/library/<model>/<tag>`), GGUF-style example (`qwen3/0.6b`):
```json
{
  "schemaVersion": 2,
  "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
  "config": { "mediaType": "application/vnd.docker.container.image.v1+json", "digest": "sha256:...", "size": 490 },
  "layers": [
    { "mediaType": "application/vnd.ollama.image.model",    "digest": "sha256:...", "size": 522640096 },
    { "mediaType": "application/vnd.ollama.image.template", "digest": "sha256:...", "size": 1723 },
    { "mediaType": "application/vnd.ollama.image.license",  "digest": "sha256:...", "size": 11338 },
    { "mediaType": "application/vnd.ollama.image.params",   "digest": "sha256:...", "size": 120 }
  ]
}
```
- **Real disk cost** = sum of `layers[].size` (the `.model` layer dominates; `.template`/`.license`/`.params` are near-zero). Cross-checked: summing all 14 manifests gives 159.8 GB vs. `du -sh models` = 149G — the manifest sum overcounts slightly because some layers (e.g. shared tokenizer/template blobs across `qwen3.6` variants) are deduplicated on disk but counted once per manifest that references them.
- **Cloud-proxy models** (e.g. `deepseek-v4-flash:cloud`) have `"layers": []` — zero disk cost, not a real local model. A scanner MUST special-case empty layers or it will treat a cloud alias as a 0-byte local model.
- **Quant / param count / architecture**: NOT in the manifest. Fetch the **config blob** (`config.digest`, tiny — 300–500 bytes) and read it directly as JSON:
  ```json
  { "model_format":"gguf", "model_family":"qwen3", "model_families":["qwen3"],
    "model_type":"751.63M", "file_type":"Q4_K_M", "architecture":"amd64", "os":"linux",
    "rootfs": {"type":"layers","diff_ids":[...]} }
  ```
  `model_type` = param count string (e.g. "751.63M", "27B"), `file_type` = quant (e.g. "Q4_K_M"), `model_family` = arch family. This works for **GGUF** models (4-layer manifests: model/template/license/params).
- **MLX / safetensors models** (`gemma4:12b-mlx`, `qwen3.8:27b-mlx`, `muse-glimmer:30b-mlx`) use a completely different manifest shape: **hundreds to 1500+ layers**, one per tensor (`mediaType: application/vnd.ollama.image.tensor`, each with a `name` like `model.language_model.layers.0.input_layernorm.weight`), plus `.json`/`.params`/`.license` layers. The config blob for these has **empty** `model_type`/`file_type`/`architecture` fields but instead carries `renderer`, `parser`, `requires` (min Ollama version), and a `capabilities` array (`["completion","vision","audio","tools","thinking"]`) — useful for "what can this model do" badges. Some (gemma4) also declare a `draft` sub-config for speculative decoding (separate draft model + tensor prefix). Real disk cost for MLX models = sum of all tensor layer sizes (737–1503 layers observed; 7.65–21.2 GB depending on model).
- **Params blob** (`application/vnd.ollama.image.params`) = default sampling params only: `{"temperature":1,"top_k":64,"top_p":0.95,"repeat_penalty":1,"stop":[...]}`. Not context length.
- **Context length is NOT stored anywhere in the manifest tree for GGUF models.** It must come from either (a) the server log's env dump (`OLLAMA_CONTEXT_LENGTH` — global override, defaults to 131072 in this install) and the runtime-computed `default_num_ctx` (VRAM-based, e.g. 32768 for 25GB VRAM), neither of which is per-model, or (b) parsing the GGUF header of the actual `.model` tensor blob. Confirmed feasible: the GGUF magic/version/tensor-count/kv-count are the first 24 bytes of the file (`GGUF`, version 3, n_tensors, n_kv observed on a real blob) — the context-length KV pair (`<arch>.context_length`) lives in the small KV section immediately after, so a scanner can read a few KB from the start of one large blob file (not the whole blob) without downloading/copying it. This is a real GGUF-key-value parser to write (medium effort, no external deps needed) — LM Studio already does exactly this (see below), proving it's practical.

**Server log** (`logs/server.log`, structured `time=... level=... source=... msg="..." k=v`):
- Startup line `msg="server config" env="map[...]"` — full env dump including `OLLAMA_MODELS` (models dir path, respects override), `OLLAMA_KEEP_ALIVE` (5m0s default — when an idle model unloads), `OLLAMA_MAX_LOADED_MODELS`, `OLLAMA_NUM_PARALLEL`, `OLLAMA_CONTEXT_LENGTH`, `OLLAMA_HOST`, `OLLAMA_ORIGINS`, proxy vars.
- `msg="inference compute"` — GPU/accelerator detected (`Apple M5`, Metal, `total="25.0 GiB"` VRAM).
- `msg="vram-based default context"` — the context length Ollama actually picked at runtime.
- Embedded Gin access-log lines: `[GIN] <date> - <time> | <status> | <latency> | <remote_ip> | <METHOD> "<path>"`. Confirmed paths seen: `/api/tags` (heavily polled — 191 hits, ~30s interval, some external client polling model list), `/api/chat`, `/api/generate`, `/api/show`, `/api/pull`, `/api/ps` (currently-loaded models), `/api/me`, `/api/status`, `/api/version`, `/health`, `/v1/chat/completions` (OpenAI-compat), `/api/experimental/model-recommendations`. Latency field on `/api/chat`/`/api/generate`/`/v1/chat/completions` lines is **wall-clock request duration including generation** (one seen at `1m54s`, one at `5m8s` — real inference-time evidence). A couple of these calls returned HTTP 500.

### Dashboard candidates (ranked, value × ease)
1. **Model inventory table** — name:tag, param count, quant, format (GGUF/MLX/safetensors), disk GB, last-pulled date. Source: `manifests/**` + config blob. High value, easy (pure JSON reads, no blob scanning).
2. **"Last actually run" per model** — derive from `server*.log` Gin lines matching `/api/chat` or `/api/generate` (correlate by nearest preceding `/api/show`/`/api/ps` call, since the request body with the model name isn't in the access-log line itself — only path/status/latency are). Medium value, medium effort (log parsing + rotation-aware merge across `server.log`..`server-5.log`), and only as far back as the last 6 app restarts (~15 days in this install).
3. **Runtime/server config panel** — version, `OLLAMA_KEEP_ALIVE`, `OLLAMA_CONTEXT_LENGTH`, `OLLAMA_MODELS` path, `OLLAMA_MAX_LOADED_MODELS`, detected GPU + VRAM, computed default context. High value (explains behavior users don't understand — e.g. why a model unloaded), easy (one log grep per restart).
4. **Request activity / usage history** — count and latency histogram of `/api/chat`, `/api/generate`, `/v1/chat/completions` calls over the retained log window; flag 500s. Medium value, easy given #2's parser already exists.
5. **Capabilities badges for MLX models** (vision/audio/tools/thinking) from the config blob's `capabilities` array. Low-medium value, trivial.
6. **True context length per model** via GGUF header KV parsing. High value (this is the one field genuinely missing everywhere else), medium-high effort (write a minimal GGUF KV reader — magic/version/tensor-count/kv-count/typed KV entries).
7. **CLI usage history** — `~/.ollama/history` as a lightweight "recent prompts sent via `ollama run`" feed, similar to a shell history panel. Low value (only captures REPL usage, not API usage which is the majority), trivial to read, but treat content as sensitive (never surface raw prompt text; at most a count/timestamp roll-up).

### Cross-harness parallels
- Model inventory: `manifests/**` ↔ LM Studio's `.internal/gguf-metadata-cache.json` / model.json config.json (HF); ↔ Hermes has no local-model inventory equivalent.
- Last-run/usage history: `server*.log` Gin lines ↔ LM Studio's `model-data.json` (`lastLoadedTimestamp`, explicit and structured — better signal than Ollama's) ↔ Hermes kanban/request dumps.
- Request log: `server*.log` ↔ LM Studio `server-logs/YYYY-MM/*.log` (llama.cpp backend log, richer — includes model load path and speculative-decoding init) ↔ Grok's `events.jsonl`.
- Loaded-model state: no persisted file — only derivable live via `/api/ps` (not logged unless polled) or by watching `keep_alive` timers server-side (not observable from disk).
- Disk cost: `manifests` layer sizes ↔ HF cache blob sizes ↔ LM Studio manifests are absent (LM Studio has no separate manifest layer — the GGUF/safetensors file IS the model dir entry under `models/`, out of scope here per traversal caps).
- Config/params: `models/manifests/.../params` blob (sampling defaults) ↔ LM Studio `settings.json.defaultContextLength` / per-session `inferenceConfig`.
- Server settings: env dump in `server.log` ↔ LM Studio has no equivalent single dump (settings spread across `settings.json` + `backend-preferences-v1.json`).

### Gotchas
- **Never traverse `models/blobs`** — 149G, thousands of files, would explode any scanner; only manifests + a *by-digest* read of one specific config-blob file (looked up from a manifest, small, <1KB) or a *bounded-byte* read of one specific `.model`/tensor blob's first few KB (for GGUF header) are safe.
- `OLLAMA_MODELS` env var relocates the whole `models/` dir — don't hardcode `~/.ollama/models`.
- Cloud-proxied model tags have empty `layers: []` — must special-case, not just "no local weight found."
- Log rotation keeps only 6 generations per stream (`server.log`..`server-5.log`), rotated on app/service **restart**, not by size or time — a long-running daemon may have only ONE log file covering months; a frequently-restarted one (as observed here) covers just ~15 days. Never assume a fixed time window.
- GGUF vs MLX/safetensors manifests have structurally different `layers[]` shapes (4 fixed-role layers vs. hundreds of per-tensor layers) — a manifest parser needs a branch on `config.model_format`.
- `~/.ollama/history` and any `msg=` log text should be treated as containing user-authored content in the worst case — don't echo raw lines into a UI without redaction awareness (observed content here was scan-time queries, but the file format doesn't guarantee that).
- `id_ed25519` — genuine private key file, mode `-rw-------`; never read/print its contents in any scanner or report.

---

## LM Studio — `~/.lmstudio`, 18G (`models/` dir, 17G, excluded from traversal)

**What is it / still active?** Yes. `server-logs/2026-08/2026-08-18.1.log` is the newest log (Aug 18), llama.cpp backend serving `Qwen3.8-27B-Q4_K_M.gguf` with MTP speculative decoding. `.internal/ng-sessions.sqlite` migrations table implies a schema-versioned "ng" (next-gen) session store actively evolving. App internal codename is **"bionic"** — nearly everything interesting lives under `~/.lmstudio/apps/bionic/`, not the paths named in the assignment brief directly (the brief's `conversations/`, `config-presets/`, `server-logs/`, `user-files/` exist as **empty top-level stubs**; the real per-app and per-project data is nested one level deeper).

### Directory map
```
~/.lmstudio
├── credentials/
│   ├── lmstudio-hub.json     # <redacted> — hub account credential
│   ├── mcp-oauth/            # <redacted> — OAuth tokens for MCP servers LM Studio connects to
│   └── ng-mcp-oauth/         # <redacted>
├── hub/
│   ├── models/qwen/qwen3.8-27b/    # cached hub listing metadata for a viewed/downloaded model page
│   └── presets/
├── extensions/
│   ├── backends/    # versioned inference backend binaries: llama.cpp-mac-arm64-*-2.28.2, mlx-llm-*-1.11.0 (x2 variants), executorch-asr-*-0.0.8
│   ├── frameworks/  # harmony-*-0.3.5 (OpenAI harmony format?), lmlink-connector-*-0.1.0
│   ├── models/      # empty (extension-provided model definitions, none installed)
│   └── plugins/lmstudio/
├── .internal/
│   ├── gguf-metadata-cache.json      # PARSED GGUF headers, keyed by absolute file path — see schema below
│   ├── model-data.json               # per-model load history — see schema below
│   ├── model-index-cache.json        # hub catalog cache
│   ├── download-jobs-info.json       # extension/backend/model download job history (URL, state, timestamps)
│   ├── single-downloads-info.json
│   ├── cloud-account.json / cloud-account-usage.json  # LM Studio Cloud billing usage snapshot — see schema below
│   ├── ng-cloud-models.json          # cloud model catalog
│   ├── ng-sessions.sqlite            # APP-LEVEL session/chat store (empty in this install: 0 sessions)
│   ├── recent-projects.json
│   ├── projects-registry.json
│   ├── backend-preferences-v1.json   # which inference backend (llama.cpp/mlx/executorch) is selected
│   ├── persistent-extension-pack-state.json
│   ├── server-logs-state.json        # log-rotation bookmark {filePathBase, index, lastWrittenFileSizeBytes}
│   ├── api-prediction-history/packs/ # empty — placeholder for API-usage prediction/autocomplete history
│   ├── retrieval-sessions/           # empty — RAG session state placeholder
│   ├── cached-rag-pipeline-chunks/   # empty — RAG chunk cache placeholder
│   ├── bundled-models/nomic-ai/      # ships one bundled embedding model (nomic-embed-text-v1.5, GGUF)
│   └── config-presets-drafts/
├── apps/bionic/                       # <- the real app data root ("bionic" = internal codename)
│   ├── settings.json                  # user-facing app settings — see schema below
│   ├── server-logs/2026-08/2026-08-{17,18}.1.log   # llama.cpp SERVER backend log — see below
│   ├── .internal/
│   │   └── ng-sessions.sqlite         # APP-LEVEL chat DB (0 sessions here — chats live in project-scoped DBs instead)
│   ├── projects/<uuid>/
│   │   ├── project.json               # {"name","projectType"}
│   │   ├── working-directories/       # tracked working dirs for this coding project
│   │   ├── conversations/             # empty (superseded by the sqlite below)
│   │   └── .internal/ng-sessions.sqlite   # PROJECT-SCOPED chat/session DB with real data — see schema below
│   ├── config-presets/   # empty at top level (presets are per-project or in .internal/config-presets-drafts)
│   ├── user-files/       # empty
│   └── working-directories/  # empty at app level
```

### Store inventory
| Path | Format | What it holds | Cadence | Retention/cleanup | Coverage |
|---|---|---|---|---|---|
| `.internal/gguf-metadata-cache.json` | JSON (serialized Map: `{json:{map:[[path,{mtimeMs,fileSizeBytes,metadata:{...}}]], cacheVersion}}`) | **Fully parsed GGUF header** per model file, keyed by absolute path, invalidated by mtime+size | Written once per model on first load/scan | Grows with models touched; not size-capped observed | **NEW — high value** |
| `.internal/model-data.json` | JSON (serialized Map) | Per-model-identifier: `source` (hub/huggingface origin), `lastAttemptedToLoadTimestamp`, `lastLoadedTimestamp` | Updated on every load attempt | Small, no eviction seen | **NEW — high value** (this is the direct "when was this model last run" answer) |
| `apps/bionic/projects/<uuid>/.internal/ng-sessions.sqlite` | SQLite | Full agentic-coding session store: `sessions` (model used, tool/MCP module list, working directory, shell-approval mode), `chat_entries` (DAG via `previous_id`/`redirect_to_id`, role+parts message content, `source.ngModule`/`source.handler` attribution), `global_checkpoint_log`/`global_checkpoint_file_states` (git-like file-checkpoint system tied to chat turns — created/modified/deleted, sha256, `can_gc`), `file_references`, `resource_cleanup_queue` | Live, per turn | App-managed GC via ref-counting triggers on every table | **NEW — high value** |
| `apps/bionic/.internal/ng-sessions.sqlite` | SQLite, same schema | App-level (non-project) chat sessions | Same | Same | NEW (same schema, 0 rows in this install) |
| `apps/bionic/server-logs/YYYY-MM/*.log` | plaintext, llama.cpp/llama-server debug log | Model load path, load timing, speculative-decoding ("MTP draft context") init, Metal/GPU warnings, per-request server internals | Real-time while server running | Daily files, rotation bookmark in `server-logs-state.json`; only 2 files present (Aug 17–18) | **NEW** |
| `.internal/cloud-account-usage.json` | JSON | LM Studio Cloud usage: `payload.{requestCount, inputTokens, cachedInputTokens, outputTokens, spendMicrodollars, period, generatedAtIso}` | Refreshed periodically from LM Studio's account API | Overwritten each refresh | **NEW** — real usage/cost data for cloud-routed requests through LM Studio, all-zero in this install (unused) |
| `.internal/download-jobs-info.json` | JSON | Model/extension/backend download job history: URL, subpath, job state (`completed`/etc.), completion timestamp | Appended per download | Not seen to be pruned | NEW, low-medium value |
| `apps/bionic/settings.json` | JSON | App config incl. `defaultContextLength`, `cloudInference`, `developerMode`, `autoLoadBundledLLM`, `modelLoadingGuardrails`, `hfSearchToken`/`hfDownloadToken` (empty in this install) | On settings change | n/a | PARTIAL (config surface, not usage data) |
| `.internal/backend-preferences-v1.json` | JSON | Selected inference backend (llama.cpp vs MLX vs executorch) per model type | On preference change | n/a | NEW, low value |
| `credentials/*` | JSON / dir | Hub account + MCP OAuth credentials — **values not inspected/reported** | n/a | n/a | Existence only |

### Schemas

**`gguf-metadata-cache.json`** (values elided beyond types; real sample values for two non-sensitive numeric fields shown to prove derivability):
```
{ json: { map: [ [ <absolute-gguf-path>, {
    mtimeMs: <float>, fileSizeBytes: <int>,
    metadata: {
      arch, name, numExperts, defaultNumExperts, chatTemplate,
      embeddingLength, numAttentionHeads, numKeyValueHeads,
      parameters,            // e.g. "27B" — confirmed present
      bosToken, eosToken,
      contextLength,         // e.g. 262144 — confirmed present, THE field Ollama lacks
      numLayers,              // e.g. 65
      nextnPredictLayers, supportsMtp,
      draftSpeculationVocab: { tokenCount, startTokenId, maxVocabSizeDifference, prefixHashes, bosTokenId, eosTokenId, addBosToken, addEosToken }
    }
  } ] ] }, cacheVersion } }
```
This *proves* GGUF-header parsing for context length / param count / layer count is practical and cheap — LM Studio does it and caches by (path, mtime, size). TokenTelemetry could either (a) read this cache file directly for any model LM Studio has touched, or (b) implement the same GGUF-KV read independently (needed anyway for Ollama's GGUF models, which this cache doesn't cover since it's keyed by LM Studio's own `models/` paths).

**`model-data.json`** (actual small file, reproduced verbatim — no sensitive content):
```json
{"json":[
  ["qwen/qwen3.8-27b", {"source":{"type":"hub","url":"...","owner":"qwen","name":"qwen3.8-27b"},
    "transitive":false,"lastAttemptedToLoadTimestamp":1787058521206,"lastLoadedTimestamp":1787058545298}],
  ["lmstudio-community/Qwen3.8-27B-GGUF/Qwen3.8-27B-Q4_K_M.gguf", {"source":{"type":"huggingface","owner":"lmstudio-community","repo":"Qwen3.8-27B-GGUF","file":"Qwen3.8-27B-Q4_K_M.gguf"},"transitive":true}]
],"meta":{"values":["map"]}}
```

**`ng-sessions.sqlite`** — `sessions.session_json` keys (values elided):
```
baseSystemPrompt: str
modelSpecifier: { type: str, indexedModelIdentifier: str }
inferenceConfig: { reasoningLevel: str }
sessionConfig: { internalShellApprovalMode: str }
ngModuleSpecifiers: [ { identifier: str, initParams: dict } ]   # tool/MCP modules enabled for this session
ngUserToolSpecifiers: []
sessionParams: { working_directory: str }
queuedUserTurns: []
```
`chat_entries.entry_json` keys (values elided):
```
id: str, hidden: bool
source: { type: str, ngModule: str, handler: str }   # which tool/module produced this turn
type: str
message: { role: str, noAssistantResponse: bool, parts: [ {...} ] }
```
`global_checkpoint_log` columns: `type ∈ {created,modified,deleted}`, `path`, `file_sha256_base64`, `external`, `created_timestamp`, `move_counterpart_id`, `can_gc`, `chat_entry_id` (FK to the turn that caused it), `session_id`, `user_prompt`. This is a **file-change-per-turn audit log** — LM Studio's equivalent of Claude Code's checkpoint/undo feature, scoped to a project.

**`cloud-account-usage.json`** (full file, values are all-zero/inactive in this install, ownerKey redacted):
```json
{"ownerKey":"<redacted>","billingContext":{"type":"personal"},
 "payload":{"generatedAtIso":"...","period":"last30Days","requestCount":0,
   "inputTokens":"0","cachedInputTokens":"0","outputTokens":"0","spendMicrodollars":"0","unvaluedRequestCount":0}}
```

**`server-logs/*.log`** sample line shape:
```
[2026-08-18 18:38:52][DEBUG] 0.06.256.308 I srv    load_model: loading model '/Users/.../Qwen3.8-27B-Q4_K_M.gguf'
[2026-08-18 18:39:03][DEBUG] 0.17.079.560 I common_speculative_init_result: creating MTP draft context against target model '...'
```

### Dashboard candidates (ranked)
1. **Model inventory with true context length, param count, layer/head counts** straight from `gguf-metadata-cache.json` — highest value, trivial (already-parsed JSON, no binary parsing needed) for any model LM Studio has opened.
2. **"Last loaded" timestamp per model** from `model-data.json`'s `lastLoadedTimestamp`/`lastAttemptedToLoadTimestamp` — high value, trivial, and structurally better than Ollama's log-scraping approach.
3. **Per-project coding-session panel** (mirroring Hermes's kanban/soul dashboard): working directory, model used, tools/MCP modules enabled, and a **file-checkpoint timeline** from `global_checkpoint_log` (what files changed on which turn) — high value, medium effort (SQLite join across `sessions`→`chat_entries`→`global_checkpoint_log`), and it's a capability *no other harness in the brief has* except Claude Code's own checkpoint mechanism.
4. **Cloud usage/cost** from `cloud-account-usage.json` if the user has ever used LM Studio Cloud — medium value (currently zero for this user, but the shape is ready), trivial.
5. **Server activity log** (model loads, speculative-decoding setup, GPU warnings) from `server-logs/YYYY-MM/*.log` — medium value, easy, but very shallow retention (2 days present).
6. **Download/backend job history** from `download-jobs-info.json` — low-medium value ("when did I last update backend X"), trivial.

### Cross-harness parallels
- Model inventory: `gguf-metadata-cache.json` (richer than Ollama — includes context length natively) ↔ Ollama manifests+config blob ↔ HF cache `config.json`.
- Last-run/usage history: `model-data.json` timestamps ↔ Ollama's log-scrape (LM Studio's is structured and superior) ↔ Hermes kanban.
- Request log: `server-logs/*.log` ↔ Ollama `server*.log` Gin lines (LM Studio's carries model-load detail but not a clean per-request access-log line in the sample seen).
- Loaded-model state: not persisted separately, inferable from `model-data.json`'s latest timestamp + whether a `llmster-pid.lock`/process is alive (not investigated further — out of scope).
- Disk cost: not tracked in any small file (must come from the excluded 17G `models/` dir directly — a `du` per model folder, same caveat as Ollama's blobs but LM Studio doesn't dedupe by content hash the way Ollama does, so per-folder size is exact).
- Config/params: `sessionParams`/`inferenceConfig`/`sessionConfig` per session (sqlite) ↔ Ollama's static params blob (LM Studio's is per-session, richer).
- Server settings: `apps/bionic/settings.json` + `backend-preferences-v1.json` ↔ Ollama's env dump in server.log.
- **Unique to LM Studio**: project-scoped file-checkpoint log (`global_checkpoint_log`) — a coding-agent-style undo/diff trail tied to chat turns. No equivalent elsewhere in the brief except Claude Code itself.

### Gotchas
- The paths named in the assignment brief (`conversations/`, `config-presets/`, `server-logs/`, `user-files/`, `.plugin-*`) are **top-level stubs that are empty in current LM Studio versions** — the live data has moved under `apps/bionic/` (app-level) and `apps/bionic/projects/<uuid>/` (project-level). A scanner hardcoding the brief's flat paths will find nothing; it must descend into `apps/<app-codename>/`. The codename "bionic" itself could change in a future LM Studio version — detect by listing `apps/*` rather than hardcoding.
- Two `ng-sessions.sqlite` files exist per project *and* one at the app level — a scanner must enumerate `projects/*/​.internal/ng-sessions.sqlite` **and** `apps/bionic/.internal/ng-sessions.sqlite`, not assume a single DB.
- `gguf-metadata-cache.json` and `model-data.json` are both hand-rolled `Map` serializations (`{json: [...], meta: {values:["map"]}}` or `{map: [...], cacheVersion}`), not plain JSON objects — a naive `json.load` gives a list-of-pairs, not a dict; must reconstruct the map from `[key, value]` pairs.
- `credentials/` holds real OAuth/hub tokens — never read/print contents, existence-only.
- `~/.lmstudio/models` (17G) must NOT be recursively traversed per instructions — model disk-size and format there can only be sourced via the metadata caches above or a single `du -sh` per top-level model folder if truly needed.
- Log/session data volume is small and shallow (2 log days, low session counts) in this install — a "no data" state is expected and should not be treated as a scanner bug, but the schema support is real and should be built regardless.

---

## Hugging Face cache — `~/.cache/huggingface`, 14G (`hub/` blobs excluded from recursive traversal)

**Confirmed shape**: standard `huggingface_hub` cache layout, unchanged from what TokenTelemetry already reads. Documenting precisely since the brief asked for confirmation.

```
~/.cache/huggingface
├── token                       # <redacted> — HF auth token (37 bytes)
├── stored_tokens                # <redacted> — additional stored token(s), 61 bytes
├── .check_for_update_done
├── modules/transformers_modules/<repo>/   # trust_remote_code: cached custom Python model code pulled from a repo (e.g. modeling_*.py, configuration_*.py)
├── datasets/<name>/<config>/<version>/    # HF datasets cache (unrelated to model runtimes; small, 7.9M)
├── xet/                          # Xet chunk-based storage backend cache: logs/ (per-run upload/download logs) + <endpoint-hash>/{staging,chunk-cache}
└── hub/
    ├── CACHEDIR.TAG, version.txt, version_diffusers_cache.txt
    ├── .locks/models--<org>--<name>/      # lock files for in-progress or interrupted downloads (presence = incomplete download signal)
    └── models--<org>--<name>/
        ├── refs/<branch>              # plaintext commit sha the branch currently resolves to (e.g. "main" -> sha)
        ├── blobs/<sha>                 # content-addressed files, NOT enumerated recursively (per instructions), sampled by digest only
        ├── snapshots/<commit-sha>/     # symlink farm: filename -> ../../blobs/<sha>, one dir per resolved commit
        └── .no_exist/<commit-sha>/     # empty marker files for filenames PROBED but confirmed absent (e.g. adapter_config.json) — avoids repeat 404s
```
Models observed (org/name only, no content read): `mlx-community/Qwen3-TTS-12Hz-{0.6B-Base-4bit,1.7B-VoiceDesign-8bit,1.7B-CustomVoice-8bit}`, `black-forest-labs/FLUX.1-schnell`, `baidu/Unlimited-OCR`, `Systran/faster-whisper-{small,base}`, `gpt2`, `bert-base-uncased`, `distilbert-base-uncased`, `meta-models/Muse-Glimmer-30B-GGUF`, `ds4sd/docling-models`, `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign`, `Qwen/Qwen3-Embedding-0.6B`, `sentence-transformers/all-MiniLM-L6-v2`.

### Schema — per-model `config.json` (inside a snapshot dir, small, safe to read directly)
Confirmed keys on `Qwen/Qwen3-Embedding-0.6B`'s config.json: `architectures, attention_bias, attention_dropout, bos_token_id, eos_token_id, head_dim, hidden_act, hidden_size, initializer_range, intermediate_size, max_position_embeddings, max_window_layers, model_type, num_attention_heads, num_hidden_layers, num_key_value_heads, rms_norm_eps, rope_scaling, rope_theta, sliding_window, tie_word_embeddings, torch_dtype, transformers_version, use_cache, use_sliding_window, vocab_size`.
- **`max_position_embeddings`** = context length (HF's name for it) — directly present, no binary parsing needed, unlike Ollama's GGUF blobs.
- **`num_hidden_layers`, `hidden_size`, `num_attention_heads`** = architecture shape.
- No explicit total-param-count field for a from-scratch HF config (derivable via a standard formula from hidden_size/layers/vocab, or read from the model card / `safetensors` header's `metadata.total_size` if present — not verified here).
- **`torch_dtype`** (e.g. `bfloat16`) is the closest analog to "quant" for a full-precision HF checkoint; a GGUF/quantized re-upload (e.g. under `lmstudio-community/*-GGUF`) instead needs the GGUF-header approach documented under Ollama/LM Studio above.

### Dashboard candidates
1. **Per-model card**: org/name, last-modified commit sha (`refs/main`), context length + arch shape straight from `config.json`, disk size (sum blob sizes for that model's `blobs/` dir only — bounded, not the whole cache). High value, easy.
2. **Download-health flag**: presence of `.locks/models--*` = interrupted/in-progress download worth surfacing. Low-medium value, trivial.
3. **Custom code flag**: presence under `modules/transformers_modules/<repo>` = model requires `trust_remote_code`, worth a badge (security-relevant). Low value, trivial.

### Cross-harness parallels
Same role as Ollama/LM Studio's manifest trees (model inventory + disk cost) but with the architecture/context fields already in plain JSON — the easiest of the three formats to mine. No request/usage log lives here (HF cache is pure artifact storage, no server component); usage would only show up via whichever runtime (LM Studio, a Python script, transformers pipeline) actually loaded the weights.

### Gotchas
- **`HF_HOME`** (or older `TRANSFORMERS_CACHE`/`HUGGINGFACE_HUB_CACHE`) env vars relocate this entire tree — don't hardcode `~/.cache/huggingface`.
- `token`/`stored_tokens` are real credential files — existence-only, never read content.
- `.no_exist/` entries are empty 0-byte files whose *name* matters (probed-and-absent), not their content — don't skip them as "empty junk," they're informative for "did this repo ship a chat template" type checks.
- `blobs/` must not be recursively `find`'d across the whole `hub/` tree (14G) — only stat sizes for blobs referenced from one model's own `snapshots/` symlinks if per-model disk size is needed.
- Symlinks in `snapshots/` point relatively (`../../blobs/<sha>`) — a naive file-size check on the symlink itself (not following it) will report near-zero size; must `stat` the resolved target.

---

## TokenTelemetry's own store — `~/.tokentelemetry`, 433M, 513 files

**What is it / still active?** Yes, this is the running app's own persisted state (this repo, this branch). `history.db` (431M, dominant) is the aggregate scan-history store across every harness the app supports.

### Directory map
```
~/.tokentelemetry
├── VERSION                          # "1" — data-dir schema version marker
├── history.db                       # 431M SQLite — cross-harness session history + archived transcripts (see schema)
├── summaries.db                     # 296K SQLite — persisted AI-generated session summaries (brief/narrative JSON, cost, backend/model used)
├── evaluations.db                   # 24K SQLite — session quality-evaluation runs (rubric-based, queued/running/complete/failed)
├── automations.db                   # 84K SQLite — CI/PR automation run tracking (runs, executions, trace events, per-model usage events, registered runtimes) — a whole sub-feature, not model-runtime related but part of "what's on disk"
├── notifications.db                 # 20K SQLite — in-app notification feed (kind, dedup_key, severity, title/body/href, read/cleared flags)
├── omnigent_sessions.db             # 0 bytes — placeholder, unused in this install
├── dsh_lifecycle.jsonl              # 250 lines — plugin load-state transition log for the "dsh" agent launcher (pending→loading→...), keyed by plugin name + uid
├── dsh-lifecycle-plugin/            # the Node.js plugin source (index.js/package.json/README) that emits dsh_lifecycle.jsonl — shipped code, not data
├── cache/<agent>/<session-uuid>.json  # 489 files across claude(347)/codex(133)/muse(9) — PARSED SESSION SCAN CACHE, keys: tokens, model, cost, mcp_tools, has_plan, plans, delegation, tool_counts, timestamp, _mtime, _version
├── summarizer/<agent>/...           # per-agent cached summarizer run outputs (.antigravitycli/<uuid>.json, opencode/runs/) — separate from summaries.db
├── billing.json                     # {"grok": {...}} — provider billing/plan config
├── brains.json                      # map of project-path -> second-brain wiki registration
├── budgets.json                     # {"budgets": [...]}
├── custom-agents.json               # list of user-defined custom agent entries
├── evaluation.json                  # {enabled, backend, model, destination, methods, backend_options, verifier} — global eval config (vs. evaluations.db which is the run log)
├── plan_prices.json                 # [] — empty, provider plan pricing overrides
├── power.json                       # {loadWatts, costPerKwh, gridCarbonIntensity, subscriptionEndpoints, localEndpoints, referenceCloudModel} — the shipped power/CO2 feature's config
├── preferences.json                 # {update_check, telemetry, telemetry_notice_ack}
├── retention.json                   # {archive: {...}} — controls when history.db archives a transcript and drops the source
├── tray.json                        # {repo_path, api_port, front_port, poll_secs, node_path, npm_path, python_path, extra_path_dirs, data_dir_override, home_override, start_on_launch} — desktop-tray launcher config
└── workflows.json                   # {"wf_<id>": {...}} — saved automation/workflow definitions
```

### Store inventory
| Path | Format | What it holds | Cadence | Retention/cleanup | Coverage |
|---|---|---|---|---|---|
| `history.db: sessions` | SQLite | One row per (agent, session id) ever scanned: project, model, provider, endpoint, billing_mode, timestamps, token counts (input/output/cached/cache_reads/total), cost, tok_per_sec, `ecosystem_json`, presence flags | Upserted on every scan | Grows unbounded unless `retention.json` archive policy trims it | COVERED (this is the engine, not new) |
| `history.db: transcripts` | SQLite BLOB | Archived full transcript bytes for sessions whose source file was later deleted/rotated (371 rows, 438MB total) | Written when source disappears and archival is enabled | Governed by `retention.json` | COVERED |
| `history.db: summaries` | SQLite | Legacy/alternate summary slot (0 rows — superseded by `summaries.db`) | n/a | n/a | COVERED, currently unused |
| `summaries.db` | SQLite | `session_id, agent, content_hash, backend, model, brief_json, narrative_json, summary_cost, generated_at` | Written per summarize call, keyed by content hash for cache-hit reuse | No eviction observed | COVERED |
| `evaluations.db` | SQLite | Rubric-based session evaluations: status machine (queued/running/complete/failed/cancelled), `requested_methods_json`, `generation_backend_json`, `verifier_backend_json`, `usage_json`, cache key = (agent, session_id, project, content_hash, payload_hash, config_hash, schema_version) | Per evaluation run | Cache-key based reuse | COVERED |
| `automations.db` | SQLite, 6 tables | PR/CI automation run tracking: `automation_runs` (repo, PR#, base/head sha, harness, trigger, attempt), `automation_executions` (nested sub-runs), `automation_trace_events` (sequenced event log with payload+fingerprint), `automation_usage_events` (per-model token/cost accounting including `reasoning_tokens`, `cost_kind`, `provider_reported_cost`), `automation_runtimes` (registered runtime agents + heartbeat), `automation_ingest_deliveries` (webhook dedup) | Per automation run | FK cascade delete on run removal | **NEW** relative to this assignment's scope, though it's an existing shipped subsystem, not local-model related |
| `notifications.db` | SQLite | In-app notification feed: kind, dedup_key (unique), severity, title/body/href, toasted/read/cleared flags | Per event | Cleared flag, no hard delete seen | COVERED |
| `cache/<agent>/<uuid>.json` | JSON | Parsed-session scan cache (avoids re-parsing raw transcripts): `tokens, model, cost, mcp_tools, has_plan, plans, delegation, tool_counts, timestamp, _mtime, _version` | Per scan, invalidated by `_mtime`/`_version` | Only 3 agents cached currently: claude(347), codex(133), muse(9) — most harnesses aren't cached here, meaning either they're fast enough to re-scan raw each time or use a different cache path | COVERED (the mechanism); note only 3/19 agent names cache here |
| `dsh_lifecycle.jsonl` | JSONL | Plugin lifecycle transitions for the "dsh" launcher app: `{ts, plugin, entry_id, uid, from, to}` | Appended live | 250 lines, no rotation seen | COVERED (already in brief's literal list) |
| `power.json` | JSON | Power-cost feature config: load watts, cost/kWh, grid carbon intensity, subscription vs local endpoint classification, reference cloud model for comparison | On settings change | n/a | COVERED (shipped feature, discussion #49) |

### Schemas
`history.db` full DDL and `automations.db` full DDL captured above (Store inventory + directory map sections) since both are small enough to reproduce in full without any row values.

### Dashboard candidates
This directory is TokenTelemetry's own data, not a "click an agent" target — its value for this assignment is as the **existing-infrastructure reference**: any new local-model-runtime feature (Ollama/LM Studio panels above) should reuse `cache/<agent>/<id>.json` (mtime/version-gated parse cache) and `history.db`'s upsert pattern rather than inventing a new cache format. `automations.db` and `evaluations.db` show the existing convention for a status-machine + cache-key table if a "model load job" or "GGUF metadata parse job" ever needs async tracking.

### Cross-harness parallels
N/A — this is TokenTelemetry's own store, the aggregation target, not a harness being mined.

### Gotchas
- `history.db` is 431M and growing — any new scanner touching it should use the existing upsert/cache-key patterns (content_hash/payload_hash/config_hash triples seen in `evaluations.db`) rather than full-table scans.
- `omnigent_sessions.db` exists but is 0 bytes — a schema-not-yet-initialized placeholder; treat as "table doesn't exist yet," not corruption.
- Only 3 of ~19 agents seen in `history.db.sessions.agent` have a `cache/<agent>/` directory (claude, codex, muse) — `pi`, `smallcode`, `dsh`, `prime` appear as agent values in `sessions` but have no corresponding cache dir, config literal, or brief mention; they're out of scope for this assignment but are evidence of newer/experimental harness integrations not yet reflected in BRIEF.md.
- `dsh-lifecycle-plugin/` and `~/.ollama/launch/dsh/` are the same "dsh" concept observed from two sides (TokenTelemetry's ingestion plugin vs. the tool's own config dir) — worth a note for whoever eventually documents "dsh" as a harness, but not investigated further here (outside this assignment's directory list).
