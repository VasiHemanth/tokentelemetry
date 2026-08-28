# Cursor + VS Code + IDE-fork survey (delta vs BRIEF.md)

Scope: `~/.cursor` (Cursor CLI), `~/Library/Application Support/Cursor` (Cursor IDE app),
`~/Library/Application Support/Code` (VS Code), and a scan of other Application Support
IDE forks. All values from auth/credential/token keys are redacted as `<redacted>`.
No user prompt/code/response text is quoted anywhere below — only key names and JSON
key structure with values elided.

---

## Cursor CLI — `~/.cursor`, 2.7M, 426 files
**Agent identity / still active?** Dormant. Latest `agent-transcripts` mtime ≈ late April
2026 (epoch ~1777124747); today is 2026-08-26, so this user has not driven the Cursor CLI
agent in ~4 months. `.gitignore` present (user opted the dir out of their own git repos).

### Directory map
```
~/.cursor/
├── ai-tracking/
│   └── ai-code-tracking.db         # NEW — AI-vs-human code attribution DB (see below)
├── argv.json                        # VS Code/Cursor CLI launch flags (crash-reporter-id only; no secrets)
├── extensions/
│   └── extensions.json              # empty/no AI extensions installed for the CLI
├── plugins/
│   └── local/                       # empty on this machine
├── projects/                        # ALREADY COVERED (main.py CURSOR_DIR / "projects")
│   └── <slug-or-tmpdir-encoded-path>/
│       ├── agent-transcripts/<sid>/<sid>.jsonl       # session transcript — COVERED (full token/model/tool/subagent/plan extraction)
│       ├── agent-transcripts/<sid>/subagents/*.jsonl  # subagent transcripts, spawn-count only — COVERED
│       ├── canvases/                # NEW — not read anywhere; empty on this machine but the folder is a real Cursor CLI artifact type (visual/canvas mode output)
│       ├── mcps/                    # NEW — not read; per-project MCP session snapshot (empty here)
│       └── terminals/*.txt          # COVERED (surfaced as "Terminal: <name>" artifacts)
├── skills/                          # generic Claude-format skills synced into Cursor (tt-*, cloudflare, etc.) — not Cursor-specific, low value
└── skills-cursor/                   # Cursor's own skill templates (create-subagent, canvas, shell, statusline, etc.) — COVERED via _collect_skills(proj/".cursor"/"skills-cursor")
    └── .sync-manifest.json          # NEW (trivial) — {skills: {<name>: {lastSyncedAt: <epoch ms>}}}, sync bookkeeping only
```

### Store inventory
| Path | Format | What it holds | Cadence | Retention/cleanup | Coverage |
|---|---|---|---|---|---|
| `ai-tracking/ai-code-tracking.db` | sqlite (6 tables) | AI-vs-human code-attribution (git-blame style) | per commit / per AI edit | unbounded, no rotation seen | **NEW** |
| `projects/*/canvases/` | dir (empty here) | Cursor "canvas" mode artifacts | per session | unknown | **NEW** |
| `projects/*/mcps/` | dir (empty here) | per-project MCP session snapshot | per session | unknown | **NEW** |
| `skills-cursor/.sync-manifest.json` | JSON | skill→lastSyncedAt map | on sync | none | **NEW** (trivial) |
| `projects/*/agent-transcripts/**` | JSONL | full transcripts | per session | none | COVERED |
| `mcp.json`, `.cursor/mcp.json` (project) | JSON | MCP server config | on edit | none | COVERED |

### Schemas
**`ai-tracking/ai-code-tracking.db`** (all 6 tables present, all currently **empty** — 0 rows in every table except `tracking_state` which has 1 row — on this machine, because Cursor CLI usage stopped in April; schema is real and will populate with any Cursor CLI usage on an active machine):
```sql
CREATE TABLE ai_code_hashes (
  hash TEXT PRIMARY KEY, source TEXT NOT NULL, fileExtension TEXT, fileName TEXT,
  requestId TEXT, conversationId TEXT, timestamp INTEGER, model TEXT, createdAt INTEGER NOT NULL
);
CREATE TABLE scored_commits (
  commitHash TEXT NOT NULL, branchName TEXT NOT NULL, scoredAt INTEGER NOT NULL,
  linesAdded INTEGER, linesDeleted INTEGER, tabLinesAdded INTEGER, tabLinesDeleted INTEGER,
  composerLinesAdded INTEGER, composerLinesDeleted INTEGER, humanLinesAdded INTEGER, humanLinesDeleted INTEGER,
  blankLinesAdded INTEGER, blankLinesDeleted INTEGER, commitMessage TEXT, commitDate TEXT,
  v1AiPercentage TEXT, v2AiPercentage TEXT, PRIMARY KEY (commitHash, branchName)
);
CREATE TABLE tracking_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);  -- only row seen: trackingStartTime
CREATE TABLE conversation_summaries (
  conversationId TEXT PRIMARY KEY, title TEXT, tldr TEXT, overview TEXT, summaryBullets TEXT,
  model TEXT, mode TEXT, updatedAt INTEGER NOT NULL
);
CREATE TABLE tracked_file_content (
  gitPath TEXT PRIMARY KEY, content TEXT NOT NULL, conversationId TEXT, model TEXT,
  fileExtension TEXT, createdAt INTEGER NOT NULL
);
CREATE TABLE ai_deleted_files (
  gitPath TEXT NOT NULL, composerId TEXT, conversationId TEXT, model TEXT, deletedAt INTEGER NOT NULL,
  PRIMARY KEY (gitPath, deletedAt)
);
```
This is Cursor's per-commit "how much of this commit was AI-written" scorer — it computes
`v1AiPercentage`/`v2AiPercentage` per commit by diffing tab-completions vs composer-written
vs human-written line counts, and keeps a rolling `conversation_summaries` (title/tldr/overview)
independent of the full transcript files.

### Dashboard candidates
1. **AI-code-attribution % per commit** (`scored_commits.v2AiPercentage` joined to git log) —
   high value (directly answers "how much of my code did the agent write"), easy extraction
   (single sqlite table, already keyed by commitHash+branch). Best net-new Cursor metric.
2. **Conversation summaries as a lightweight session index** (`conversation_summaries.title/tldr`) —
   medium value, easy — gives human-readable titles for Cursor CLI sessions without re-parsing
   full JSONL transcripts.
3. Canvas/MCP-session folder counts as an "activity" signal — low value (both empty on this
   machine, existence-only counting), trivial extraction.

### Cross-harness parallels
- **Memory/checkpoints**: `ai_deleted_files` + `tracked_file_content` act as an undo/audit log
  of AI-touched files — Cursor's version of a checkpoint ledger, keyed by conversation, not
  by turn (coarser than Claude Code's checkpoint system).
- **Plan artifacts**: none beyond what's already read from `thinking` blocks in transcripts.
- **Usage/quota**: not present in `~/.cursor` — Cursor's quota/plan state lives server-side
  (Cursor CLI has no local quota file, consistent with existing `_AGENT_FEATURES` note that
  Cursor previews are "gated in Cursor's cloud / opaque store").

### Gotchas
- `ai-code-tracking.db` will very likely be **empty** on most machines unless the user
  actively drives Cursor CLI with git commits in the loop — don't treat 0 rows as "broken."
- `canvases/` and `mcps/` project subfolders exist but were empty in this sample; their file
  format inside (when populated) is unverified — would need a machine with active Cursor
  canvas/MCP usage to confirm schema before wiring extraction.

---

## Cursor IDE (app) — `~/Library/Application Support/Cursor`, 29M, 218 files
**Agent identity / still active?** Dormant — same April-2026 cutoff as the CLI (`User/globalStorage/state.vscdb` mtime = Apr 28 2026; `logs/` has exactly one session dir `20260423T151328`). This is the Cursor **desktop app** (a VS Code fork) — a completely separate data store from `~/.cursor` above. **None of this is read by `main.py` today** except `User/workspaceStorage/*/workspace.json` (used only to resolve a workspace hash → folder path for the CLI-transcript project mapping; the state.vscdb *contents* are never opened).

### Directory map
```
~/Library/Application Support/Cursor/
├── User/
│   ├── globalStorage/
│   │   ├── state.vscdb              # NEW — ItemTable (108 rows) + cursorDiskKV (839 rows): the real chat/composer/checkpoint store
│   │   ├── state.vscdb.backup       # mirror, same schema
│   │   └── storage.json             # window/profile bookkeeping, telemetry device IDs (redact)
│   ├── workspaceStorage/
│   │   ├── <32-hex-hash>/           # per-project workspace (1 of 3 on this machine)
│   │   │   ├── workspace.json       # {"folder": "file://<path>"} — COVERED (hash→path map)
│   │   │   ├── state.vscdb          # NEW — per-workspace ItemTable: aiService.prompts/generations, composer.composerData index
│   │   │   └── anysphere.cursor-retrieval/   # NEW — codebase-indexing artifacts (embeddable_files.txt, high_level_folder_description.txt)
│   │   └── <numeric-id>/            # empty windows (no folder), same schema
│   ├── History/                     # empty (local file-revision history, not AI-specific)
│   └── snippets/                    # empty
├── snapshots/
│   ├── roots/<repo>-<hash>/         # NEW (low value) — @codebase indexing roots, name gives a *second* hash→repo-name mapping
│   └── codebases/<uuid>/            # indexed codebase blobs — cache-like, skip
├── logs/20260423T151328/
│   └── window*/workbench.mcp.{oauth,allowlist,files}.log   # NEW — MCP connection/permission log lines (text logs, not structured)
├── ai-tracking/                     # N/A — this is the CLI's dir, not present here
└── (Cache, GPUCache, CachedData, Crashpad, Session/Local Storage, DawnGraphiteCache, etc.) — Chromium/Electron cache, excluded per traversal caps
```

### Store inventory
| Path | Format | What it holds | Cadence | Retention | Coverage |
|---|---|---|---|---|---|
| `User/globalStorage/state.vscdb` → `ItemTable` | sqlite k/v | app-wide settings, auth tokens, last-command telemetry | on every UI action | last-write-wins per key | **NEW** |
| `User/globalStorage/state.vscdb` → `cursorDiskKV` | sqlite k/v, 839 rows | **composerData** (chat session index), **bubbleId** (individual chat messages incl. tool calls, todos, token counts), **checkpointId** (file-state snapshots), **agentKv:blob** (raw model request/response blobs) | one row per message/checkpoint/blob | append-only, no observed pruning | **NEW — highest-value find in this survey** |
| `User/workspaceStorage/*/state.vscdb` → `ItemTable` | sqlite k/v | `aiService.prompts` (legacy prompt-only history), `aiService.generations` (generation event log), `composer.composerData` (selected/focused composer IDs), `workbench.backgroundComposer.workspacePersistentData` | per workspace | last-write-wins | **NEW** |
| `anysphere.cursor-retrieval/*.txt` | plain text | codebase file list + folder description used for @-codebase retrieval | on index rebuild | overwritten | **NEW** (low value, no session linkage) |
| `logs/*/window*/workbench.mcp.*.log` | text log | MCP connect/oauth/allowlist events | per session | rotated by VS Code's own log-folder-per-launch scheme | **NEW** (low value, unstructured) |
| `User/workspaceStorage/*/workspace.json` | JSON | `{folder: file://...}` | on workspace open | overwritten | COVERED |

### Schemas
**`cursorDiskKV` key prefixes** (839 total rows: `agentKv` 577, `bubbleId` 244, `checkpointId` 6, `composerData` 12):

- `composerData:<composerId>` → top-level keys: `_v, composerId, richText, hasLoaded, text, fullConversationHeadersOnly, conversationMap, status, context (composers/selections/fileSelections/terminalSelections/selectedDocs/cursorRules/cursorCommands/subagentSelections/browserSelections/mentions{...}), generatingBubbleIds, codeBlockData, originalFileStates, newlyCreatedFiles, newlyCreatedFolders, createdAt, hasChangedContext, ...` — this is the **composer/chat-session container**, one per Cursor chat tab.
- `bubbleId:<composerId>:<bubbleId>` → **one chat message**, keys include: `_v, bubbleId, type, capabilities, capabilityContexts, capabilityType, conversationState, createdAt, isAgentic, isRefunded, requestId, text, thinking, thinkingDurationMs, tokenCount {inputTokens, outputTokens}, todos, tokenCount, toolResults, mcpDescriptors, supportedTools, cursorCommands, cursorRules, notepads, knowledgeItems, gitDiffs, pullRequests, docsReferences, images, aiWebSearchResults, interpreterResults, attachedCodeChunks, attachedFolders, attachedHumanChanges, diffHistories, humanChanges, lints, multiFileLinterErrors, recentLocationsHistory, workspaceUris, ...` (values elided). **`todos`, `tokenCount`, `mcpDescriptors`, `thinkingDurationMs`, `toolResults` are directly usable per-message metrics** without any transcript parsing.
- `checkpointId:<composerId>:<checkpointId>` → `{files, nonExistentFiles, newlyCreatedFolders, activeInlineDiffs, inlineDiffNewlyCreatedResources: {files, folders}}` — a **file-system checkpoint** tied to a specific message, i.e. Cursor's rewind/undo point.
- `agentKv:blob:<sha256>` → raw request/response payload, e.g. `{"role":"system","content":"<elided — identifies backend model name>"}` or similar assistant/tool payloads. **Values must never be surfaced** — this is closest to a raw model I/O dump.

**`ItemTable` (globalStorage) key names of interest** (values elided/redacted):
`cursorai/serverConfig`, `cursor.commands.globalCommands.classic`, `composer.composerHeaders`,
`cursorAuth/refreshToken` (**redact**), `cursorAuth/accessToken` (**redact**), `adminSettings.cached`,
`anysphere.cursor-always-local`, `agentLayout.shared.v6`, `cursorai/donotchange/newPrivacyMode2`.

**`ItemTable` (per-workspace) key names of interest**: `aiService.prompts` → JSON array of
`{text, commandType}` (elide `text`); `aiService.generations` → array of
`{unixMs, generationUUID, type, textDescription}` (elide `textDescription`);
`composer.composerData` → `{selectedComposerIds, lastFocusedComposerIds, hasMigratedComposerData, hasMigratedMultipleComposers}`.

### Dashboard candidates
1. **Per-message token/thinking metrics from `bubbleId` rows** (`tokenCount`, `thinkingDurationMs`,
   `toolResults` count, `mcpDescriptors`) — high value, medium ease: requires walking
   `composerData:*` → its bubble IDs (via `fullConversationHeadersOnly`) → `bubbleId:*` rows.
   This is the *only* way to get Cursor IDE (desktop) usage/token data at all, since the
   IDE's chat never touches `~/.cursor/projects` (that's CLI-only).
2. **Todos extraction from `bubbleId.todos`** — direct cross-harness parallel to Claude Code's
   TodoWrite / Hermes kanban; high value, easy (already-structured array per message).
3. **Checkpoint timeline (`checkpointId:*` rows) as a rewind/undo history** — medium value
   (only 6 rows on this sample machine, but structurally a clean "checkpoints" feed), easy.
4. **MCP tool inventory from `mcpDescriptors` in bubbles** — cross-checks/extends the
   `~/.cursor/mcp.json` static config with *actually invoked* MCP tools per message.
5. Do **not** attempt to render `agentKv:blob:*` — it's raw provider payloads including full
   system prompts; highest re-identification/leak risk in the whole Cursor surface.

### Cross-harness parallels
- **Checkpoints/rewind** → `checkpointId:*` rows (file-state snapshots keyed to a message).
- **Todos** → `bubbleId.todos`.
- **MCP + tools inventory** → `bubbleId.mcpDescriptors` / `.supportedTools` / `.toolResults`
  (actual usage) vs `~/.cursor/mcp.json` (static config, already covered).
- **Memory** → none observed distinct from chat history itself (no separate "rules" memory
  store found beyond `.cursorrules`/`cursorRules` array embedded per-message).
- **Model config** → `cursorai/serverConfig` (opaque blob, not decoded here).
- **Per-workspace mapping** → `workspace.json` `folder` field (already used); a *second*,
  independent mapping exists at `snapshots/roots/<repo-name>-<hash>/` (repo name is
  human-readable in the folder name itself, no JSON needed) — useful as a fallback resolver
  if `workspace.json` is missing/stale.
- **Usage/quota** → not found locally; `cursorAuth/*` tokens imply quota is server-side only.

### Gotchas
- **state.vscdb is SQLite with WAL** (`state.vscdb-shm`/`-wal` present) — reading while Cursor
  is running risks a locked DB; open read-only (`?mode=ro`) or copy first, same caveat as
  VS Code's own state.vscdb.
- `cursorDiskKV` values are large JSON blobs (composerData up to ~14KB seen) — walking every
  bubble for every composer across all workspaces is O(rows), fine for hundreds of rows but
  should be capped/paginated for power users with years of history.
- The mapping from a `composerId` to a **project path** is indirect: `composerData` itself has
  no project field — you must find which `workspaceStorage/<hash>/state.vscdb`'s
  `composer.composerData.selectedComposerIds` references that composerId, then resolve
  `<hash>` via `workspace.json`. A composer can also appear in **zero** workspace files if the
  workspace was later deleted (orphaned composer).
- Auth tokens (`cursorAuth/accessToken`, `cursorAuth/refreshToken`) sit in the **same table**
  as ordinary UI state — a naive "dump ItemTable" approach will capture live credentials.

---

## VS Code — `~/Library/Application Support/Code`, 2.6G, 17151 files
**Agent identity / still active?** Actively used — `User/globalStorage/state.vscdb` mtime =
Aug 24 2026 (2 days before today). Extensions present: `GitHub.copilot-chat` (the only
third-party AI *extension* with globalStorage data), plus **IDE companion** extensions for
CLI tools already covered elsewhere: `anthropic.claude-code`, `google.gemini-cli-vscode-ide-companion`,
`openai.chatgpt` (×2 versions), `qwenlm.qwen-code-vscode-ide-companion` — these add editor
diagnostics/selection-context to the CLI tools but do **not** create a separate session
store (their real data lives in `~/.claude`, `~/.gemini`, `~/.codex`, `~/.qwen`, already read).
**No** Cline / Roo / Continue / Codeium / Cody / Windsurf / Kilocode / Augment extension is
installed in this VS Code profile.

### Directory map
```
~/Library/Application Support/Code/
├── User/
│   ├── globalStorage/
│   │   ├── state.vscdb                         # ALREADY partially read? NO — core ItemTable itself is NOT read; only per-extension subfolders under globalStorage matter today
│   │   ├── agent-host-config.json               # NEW — VS Code's built-in Copilot "agent mode" settings/permissions (allow/deny, agentMerge.*, codexAgentEnabled, claudeMultiRootEnabled, ...)
│   │   ├── agent-host.db                        # NEW — sqlite: cross-provider agent session REGISTRY (provider, registration_source, start_time)
│   │   ├── github.copilot-chat/
│   │   │   ├── session-store.db                 # NEW — richest single find in VS Code: sessions/turns/checkpoints/session_files/session_refs + FTS5 search index
│   │   │   ├── vscode-sessions-<uuid>/           # NEW (low value) — shadow git index (diff.index = git DIRC format, pathspec.txt) for GitHub's CLOUD Copilot coding-agent PRs
│   │   │   ├── ask-agent/Ask.agent.md            # NEW — built-in agent-mode definition (frontmatter: name/description/tools/target)
│   │   │   ├── plan-agent/Plan.agent.md          # NEW — ditto, "Plan" mode
│   │   │   ├── explore-agent/Explore.agent.md    # NEW — ditto, "Explore" mode
│   │   │   ├── copilotCli/                       # NEW (low value) — bundled Copilot CLI shim scripts, not user data
│   │   │   └── toolEmbeddingsCache.bin           # cache, skip
│   │   ├── ms-python.python, ms-toolsai.jupyter, ms-vscode-remote.remote-containers, solomonkinard.git-blame, vscode.terminal-suggest  # non-AI extensions, skip
│   │   └── storage.json                          # window/telemetry bookkeeping
│   ├── workspaceStorage/<32-hex-hash>/ (109 workspaces)
│   │   ├── chatSessions/<sid>.json | .jsonl      # ALREADY COVERED (main.py reads both legacy .json and new delta-log .jsonl formats, incl. modelId, tokens via result.metadata)
│   │   ├── chatEditingSessions/<sid>/
│   │   │   ├── state.json                        # NEW — {sessionId, initialFileContents, linearHistory, linearHistoryIndex, recentSnapshot, version}: chat-driven-edit CHECKPOINT/REWIND state
│   │   │   └── contents/<sha1-prefix>             # NEW — content-addressed blob store of file snapshots referenced by state.json
│   │   ├── GitHub.copilot-chat/workspace-chunks.db  # NEW (cache-like) — local embedding index of the workspace (CacheMeta/Files/FileChunks w/ vector BLOB) for Copilot's codebase-context retrieval
│   │   └── state.vscdb                            # core per-workspace settings, not AI-specific beyond chat keys already covered
│   ├── History/                                   # 47M — local file-revision history (not AI-specific), skip
│   └── profiles/                                  # VS Code settings profiles, not AI-specific, skip
├── agent-host/                                     # NEW — top-level (not under User/), VS Code's native agent runtime host
│   ├── sdk-cache/claude/0.3.220/darwin-arm64/       # cached Claude Agent SDK binary (used to run Claude inside VS Code's agent mode) — cache, skip
│   └── local-endpoint/
│       ├── metadata.json                           # NEW — live editor instances: [{type, schemaVersion, pid, instanceId, endpointPath, connectionToken(**redact**), protocolVersion}]
│       └── entries/                                # empty on this machine
├── agentSessionData/<uuid>/session.db              # NEW — 121 per-session sqlite files (turns, file_edits, chat_drafts, reviewed_files, local_turns, turn_usage) — ALL EMPTY on this machine (0 rows everywhere); schema present, real data absent (see Gotchas)
├── CachedExtensionVSIXs, WebStorage, Cache, CachedData, Service Worker, Crashpad, GPUCache, DawnGraphiteCache, Partitions  # Chromium/Electron cache, excluded per traversal caps (671M+345M+193M+98M+...)
└── logs/                                            # 3.7M, standard VS Code logs incl. per-window extension-host logs
```

### Store inventory
| Path | Format | What it holds | Cadence | Retention | Coverage |
|---|---|---|---|---|---|
| `User/globalStorage/agent-host-config.json` | JSON | Copilot agent-mode config: tool permissions (`allow`/`deny`), `agentMerge.*` (auto-merge PR after CI/reviews), `modelCapabilityOverrides`, `codexAgentEnabled`, `claudeMultiRootEnabled`, `codexMultiRootEnabled`, `reasoningSummary`, `toolSearchEnabled` | on settings change | overwritten | **NEW** |
| `User/globalStorage/agent-host.db` | sqlite | cross-provider session registry: `sessions(session_uri, provider, start_time, external, registration_source)`, `metadata(key,value)` | on discovery/registration | append, `registration_source` distinguishes `discovery` (pre-existing external session, e.g. Claude Code CLI sessions auto-indexed) from `explicit` | **NEW** |
| `github.copilot-chat/session-store.db` | sqlite | `sessions` (cwd, repository, branch, agent_name, host_type), `turns` (user_message/assistant_response per turn — **contains prompt text, must be elided**), `checkpoints` (title/overview/history/work_done/technical_details/important_files/next_steps — structured plan-style summaries), `session_files` (file_path × tool_name × turn_index), `session_refs`, FTS5 `search_index` | per turn/checkpoint | unbounded, no rotation seen | **NEW** |
| `github.copilot-chat/*-agent/*.agent.md` | Markdown+frontmatter | built-in agent-mode definitions (Ask/Plan/Explore): `name, description, argument-hint, target, disable-model-invocation, tools[], agents[]` | ships with extension, rarely changes | static | **NEW** |
| `agentSessionData/<uuid>/session.db` | sqlite | native VS Code chat: `turns`, `file_edits` (before/after content + added/removed lines per tool call), `turn_usage` (usage JSON per turn), `local_turns` (payload JSON), `chat_drafts`, `reviewed_files` | per turn | one file per session, 121 present | **NEW** (schema real, 0 rows in every sampled DB here) |
| `agent-host/local-endpoint/metadata.json` | JSON | live running VS Code window instances + Unix-socket connection tokens (**redact tokens**) | live, overwritten per launch | ephemeral | **NEW** (low value — process bookkeeping) |
| `workspaceStorage/*/chatEditingSessions/<sid>/{state.json,contents/*}` | JSON + content-addressed blobs | chat-driven-edit checkpoint/rewind state | per editing session | grows with `contents/`, no observed GC | **NEW** |
| `workspaceStorage/*/GitHub.copilot-chat/workspace-chunks.db` | sqlite | local embedding index (`Files`, `FileChunks` w/ vector BLOB, `CacheMeta.embeddingModel`) | on index rebuild | cache-like | **NEW** (low value, no session linkage) |
| `User/globalStorage/state.vscdb` → `chat.cachedLanguageModels` / `.v2` | JSON array | available Copilot model catalog: `[{identifier, metadata: {...}}]` (per-model capability metadata) | refreshed periodically | overwritten | **NEW** (small, useful for "what models does this user's Copilot expose") |
| `workspaceStorage/*/chatSessions/*.json(.jsonl)` | JSON / delta-log JSONL | full chat session incl. `modelId`, `result.metadata/timings`, `response[]` | per session | none | COVERED |

### Schemas
**`agent-host-config.json`** (top-level keys, values are settings not secrets except where noted):
`permissions.{allow,deny}[]`, `telemetryLevel`, `customizations[]`, `defaultShell`,
`githubEnterpriseUri`, `copilotSdkLogLevel`, `opus48Prompt`, `toolSearchEnabled`,
`toolSearchDeferThreshold`, `reasoningSummary`, `modelCapabilityOverrides{}`,
`agentMerge.{enabled,addressReviews,fixCI,resolveConflicts,mergePullRequest,mergeMethod,replyAttribution}`,
`activeAgentTitleGeneration`, `markdownPlanRichLinksEnabled`, `copilotMultiRootEnabled`,
`claudeMultiRootEnabled`, `codexMultiRootEnabled`, `codexAgentEnabled`,
`migrateLegacyCopilotCliEnabled`, `showExternalSessions`, `autoReplyEnabled`, `globalAu...` (truncated).

**`agent-host.db`**: on this machine, 121 rows, all `provider='claude', registration_source='discovery'`
— i.e. VS Code auto-discovered 121 pre-existing Claude Code CLI sessions (from `~/.claude`,
already read elsewhere) and indexed pointers to them for its own UI; it is a **cross-reference**,
not a new data source, but confirms VS Code enumerates external agent sessions this way.
`metadata` table had 2 rows: `sessionRegistryBackfilled:claude`, `sessionRegistryBackfilled:copilotcli`.

**`github.copilot-chat/session-store.db`** schema:
```sql
CREATE TABLE sessions (id TEXT PRIMARY KEY, cwd TEXT, repository TEXT, host_type TEXT,
  branch TEXT, summary TEXT, agent_name TEXT, agent_description TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE turns (id INTEGER PRIMARY KEY, session_id TEXT, turn_index INTEGER,
  user_message TEXT, assistant_response TEXT, timestamp TEXT, UNIQUE(session_id, turn_index));
CREATE TABLE checkpoints (id INTEGER PRIMARY KEY, session_id TEXT, checkpoint_number INTEGER,
  title TEXT, overview TEXT, history TEXT, work_done TEXT, technical_details TEXT,
  important_files TEXT, next_steps TEXT, created_at TEXT, UNIQUE(session_id, checkpoint_number));
CREATE TABLE session_files (id INTEGER PRIMARY KEY, session_id TEXT, file_path TEXT,
  tool_name TEXT, turn_index INTEGER, first_seen_at TEXT, UNIQUE(session_id, file_path));
CREATE TABLE session_refs (id INTEGER PRIMARY KEY, session_id TEXT, ref_type TEXT,
  ref_value TEXT, turn_index INTEGER, created_at TEXT, UNIQUE(session_id, ref_type, ref_value));
CREATE VIRTUAL TABLE search_index USING fts5(content, session_id UNINDEXED, source_type UNINDEXED, source_id UNINDEXED);
```
Only 1 session / 1 turn / 0 checkpoints on this machine (this user's Copilot usage mostly
flows through the CLI-discovered Claude sessions above, not native Copilot Chat turns) — but
the schema is exactly a **plan/memory artifact** store: `checkpoints.title/overview/work_done/
technical_details/important_files/next_steps` is a structured, LLM-written progress summary,
directly analogous to Hermes's kanban checkpoints.

**`*.agent.md` frontmatter** (e.g. `ask-agent/Ask.agent.md`): `name, description, argument-hint,
target: vscode, disable-model-invocation, tools: [...], agents: []` followed by the system-prompt
body (not quoted here) — this is VS Code Copilot's own subagent/mode registry, analogous to
Claude Code's `.claude/agents/*.md`.

**`agentSessionData/<uuid>/session.db`** schema (0 rows in all sampled DBs — 121 files, all
identical 65536-byte page-allocated-but-empty):
```sql
CREATE TABLE turns (id TEXT PRIMARY KEY, event_id TEXT, checkpoint_ref TEXT);
CREATE TABLE session_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);  -- only key seen: isRead
CREATE TABLE file_edits (turn_id TEXT, tool_call_id TEXT, file_path TEXT, edit_type TEXT DEFAULT 'edit',
  original_path TEXT, before_content BLOB, after_content BLOB, added_lines INTEGER, removed_lines INTEGER,
  PRIMARY KEY (tool_call_id, file_path));
CREATE TABLE chat_drafts (chat_uri TEXT PRIMARY KEY, draft TEXT NOT NULL);
CREATE TABLE reviewed_files (uri TEXT, nonce TEXT, PRIMARY KEY (uri, nonce));
CREATE TABLE local_turns (turn_id TEXT PRIMARY KEY, chat_uri TEXT, anchor_turn_id TEXT, seq INTEGER, payload TEXT NOT NULL);
CREATE TABLE turn_usage (turn_id TEXT PRIMARY KEY, usage TEXT NOT NULL);
```
`turn_usage.usage` (JSON, schema unconfirmed — no populated row available) is almost certainly
a per-turn token-usage object; `file_edits` before/after content is a full diff-checkpoint store.

**`chatEditingSessions/<sid>/state.json`**: `{sessionId, initialFileContents, linearHistory,
linearHistoryIndex, recentSnapshot, version}`. `contents/<7-hex>` files are content-addressed
by a short SHA1 prefix (e.g. `da39a3e` = prefix of SHA1 of the empty string).

**`chat.cachedLanguageModels`** (globalStorage `state.vscdb` ItemTable): JSON array of
`{identifier, metadata: {...}}` — 8 entries on this machine (per-model capability rows,
fields elided but include vendor/family/token-limit style metadata based on key length).

### Dashboard candidates
1. **`agent-host-config.json` as a "Copilot agent settings" panel** — high value, trivial
   extraction (single JSON file): surfaces auto-merge-PR behavior, tool allow/deny lists,
   multi-root agent toggles per backend (Claude/Codex/Copilot) — this is the closest VS Code
   analog to Hermes's `/hermes/soul` or Claude's `settings.json` permissions view.
2. **`session-store.db.checkpoints`** rendered like Hermes kanban cards (title/overview/
   work_done/next_steps) — high value when populated, easy (single sqlite table);
   currently sparse on this machine but the schema guarantees clean structured text once used.
3. **`chatEditingSessions` as a checkpoint/rewind timeline** — medium-high value (mirrors
   Claude Code's checkpoint feature that TT doesn't yet expose for VS Code), medium ease
   (need to walk `linearHistory` + resolve `contents/<hash>` blobs, sizes could be large).
4. **`*.agent.md` files as a "subagents/modes" inventory** for Copilot — medium value, trivial
   (3 static files, just parse frontmatter), directly fills the "subagents" cross-harness slot.
5. **`chat.cachedLanguageModels`** as "models available to this user's Copilot" — low-medium
   value, trivial, good for a settings/config summary card.
6. `agentSessionData` / `agent-host` sdk-cache — low value on this machine (all empty / cache
   only); revisit if a machine with heavier native-VS-Code-chat usage is available.

### Cross-harness parallels
- **Checkpoints/rewind** → `chatEditingSessions/*/state.json` (chat-driven edits) AND
  `agentSessionData/*/session.db.file_edits` (native chat) — two parallel checkpoint stores
  depending on which chat surface was used.
- **Plan/memory artifacts** → `github.copilot-chat/session-store.db.checkpoints`.
- **Subagents/modes** → `github.copilot-chat/{ask,plan,explore}-agent/*.agent.md`.
- **Permissions/config** → `agent-host-config.json` (`permissions.allow/deny`, `agentMerge.*`).
- **Model config** → `chat.cachedLanguageModels[.v2]`, plus `modelId` already read per-turn
  from `chatSessions`.
- **Usage/quota** → `turn_usage.usage` (schema present, no populated sample obtained).
- **MCP + tools inventory** → not found as a distinct VS-Code-core store; Copilot's tool list
  is implied by `*.agent.md` `tools:[]` frontmatter plus whatever MCP servers are configured
  in VS Code `settings.json` (not surveyed here — out of this agent's scope, but worth a
  follow-up grep of `User/settings.json` for an `mcp` key).
- **Background/cloud jobs** → `github.copilot-chat/vscode-sessions-<uuid>/` (shadow git index
  for GitHub's server-side Copilot coding-agent PRs) — this is VS Code's window into a
  **remote** agent, not local compute; low priority since it's mostly a git index, not usage data.
- **Per-workspace mapping** → `workspaceStorage/<hash>/state.vscdb` doesn't store the folder
  path directly the way Cursor's `workspace.json` does; VS Code instead keeps a **global**
  `openedPathsList`/`backupWorkspaces` structure in `User/globalStorage/storage.json`
  (`backupWorkspaces.folders[].folderUri`, `profileAssociations.workspaces{}`) that must be
  cross-referenced by hash — confirm the exact key before wiring a resolver (not fully
  chased down in this pass; flagged as a gap).

### Gotchas
- `agentSessionData/*/session.db` files are **all 65536 bytes and 0 rows** on this machine —
  don't assume the schema is unused; it's more likely this user's native-VS-Code-chat volume
  is near-zero relative to Copilot-Chat-extension and CLI-discovered sessions. A scanner
  should handle the empty-DB case gracefully rather than treating it as a parse error.
- `session-store.db` has an FTS5 virtual table (`search_index` + its `_data/_idx/_content/
  _docsize/_config` shadow tables) — a naive "list all tables" will surface 5 extra FTS
  internal tables per FTS5 index; filter `sqlite_master` on `type='table' AND name NOT LIKE
  'search_index_%'` or you'll double-count.
- `agent-host/local-endpoint/metadata.json` contains live **Unix-domain-socket connection
  tokens** (`connectionToken`) for currently-running VS Code windows — must be redacted, and
  is also inherently ephemeral (stale/invalid once the window closes), so it has near-zero
  historical dashboard value beyond "is VS Code currently running."
- `CachedExtensionVSIXs` (671M!) and `WebStorage` (371M) dominate the directory size but are
  pure extension-marketplace/webview caches — correctly excluded per traversal caps, but worth
  flagging in any "how big is my AI data footprint" feature so users aren't alarmed by the 2.6G
  total (almost all of it is cache, not agent history).
- `state.vscdb` WAL files present (`-shm`/`-wal`) on the live, actively-used Code install —
  same read-while-running lock risk as Cursor.
- Workspace-hash → repo-path resolution for VS Code is **not** as clean as Cursor's
  `workspace.json`; needs its own investigation pass (see "Per-workspace mapping" above).

---

## Other IDE forks scan (bonus — light pass only, per assignment's "ls and note" instruction)

`ls ~/Library/Application\ Support/` shows **no** Windsurf, Trae, Void, Zed, Positron, Kiro,
or PearAI directory on this machine — none of those forks are installed here, so nothing to
report for them (their absence itself is a data point: this survey machine's IDE-fork
footprint is Cursor + VS Code + Antigravity only).

**`Antigravity` (512M) and `Antigravity IDE` (104M) — genuinely new, NOT the same as the
`~/.gemini/antigravity*` brain dirs already read by `main.py`.** This is Google's Antigravity
desktop app (a VS Code fork, formerly Windsurf/Codeium lineage), with its own
`User/globalStorage/state.vscdb` containing Antigravity-specific keys never seen in Cursor/VS
Code: `antigravityUnifiedStateSync.trajectorySummaries` (181KB — "trajectory" = Antigravity's
term for an agent run), `.artifactReview`, `.agentPreferences`, `.sidebarWorkspaces`,
`.userStatus`, `.oauthToken` (**redact**), `antigravityAuthStatus` (**redact if it contains a
token**), `jetskiStateSync.agentManagerInitState` (internal codename "jetski" for its agent
manager), plus 61 `workspaceStorage` entries (heavier usage than Cursor IDE, lighter than VS
Code). Sampled values under these keys were **not JSON** (likely protobuf/binary) so schemas
could not be extracted without a dedicated decode pass. **This deserves its own full survey
pass** at the same depth as Cursor/VS Code above — flagging it here rather than skipping
silently, since it's sizeable (616M combined) and structurally rich, but it was out of this
agent's assigned scope (Cursor + VS Code) and a proper pass needs its own time budget.

---

## Summary of NEW stores found (for triage)

| Store | Size/rows | Value | Ease | Priority |
|---|---|---|---|---|
| Cursor IDE `cursorDiskKV` (composerData/bubbleId/checkpointId) | 839 rows | High | Medium | **1** |
| VS Code `agent-host-config.json` | 1 file | High | Trivial | **1** |
| VS Code `github.copilot-chat/session-store.db` (checkpoints) | sparse now, rich schema | High | Easy | **2** |
| Cursor CLI `ai-code-tracking.db` (scored_commits AI%) | empty now, rich schema | High | Easy | **2** |
| VS Code `chatEditingSessions` (checkpoint/rewind) | per-session | Med-High | Medium | **3** |
| VS Code `*.agent.md` (Ask/Plan/Explore modes) | 3 files | Medium | Trivial | **3** |
| Cursor IDE per-workspace `aiService.*` | small | Low-Med | Easy | 4 |
| VS Code `chat.cachedLanguageModels` | 8 rows | Low-Med | Trivial | 4 |
| VS Code `agent-host.db` (session registry) | 121 rows | Low (cross-ref only) | Easy | 4 |
| Antigravity (whole app) | 512M+104M | Unknown-High | Needs own pass | flagged, not scoped here |
