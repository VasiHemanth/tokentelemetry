# Harness survey: Grok, Qwen, Vibe, OpenClaw

Cross-checked every "NEW" claim below against `origin/main` `backend/main.py` (grep for the
relevant dir/filename constants) so nothing already wired up gets re-reported as new.

---

## Grok Build (xAI) — `~/.grok`, 1.7G, 7642 files

**Agent identity / still active?** Grok Build / `grok` CLI, xAI's terminal coding agent (README: "A
terminal-based AI coding assistant and agentic harness"). Version 1.0.5 (`version.json`,
`.metadata_version`), auto-update on. Actively used: an `active_sessions.json` entry is live as of
today (2026-08-26, pid still running against `/Users/hemanthvasi/Documents/antigravity/quirky-borg`),
and `logs/unified.jsonl` has entries from the same timestamp.

### Directory map
```
~/.grok/
├── auth.json, auth.json.lock                # xAI OAuth/API-key credential (structure only, see below)
├── config.toml, config.toml.bak             # user config; .bak is CLI's auto-backup on write
├── version.json, .metadata_version, CHANGELOG.{json,md}
├── agent_id                                 # stable per-install UUID (device id, not a session id)
├── active_sessions.json                     # LIVE: array of {session_id,pid,cwd,opened_at} for running TUIs
├── active_sessions.lock
├── campaigns_state.json(.lock)              # dismissed in-app announcement/launch-banner ids
├── trusted_folders.toml(.lock)              # per-directory "trust this workspace" decisions (path + epoch)
├── last-copy.txt                            # plaintext of the LAST thing the user copied in-app (raw user text)
├── slash-mru.json                           # most-recently-used slash commands, by name + unix ts
├── tip_cursor.json                          # in-app tips carousel position
├── models_cache.json                        # cached /v1/models catalog: per-model context_window, pricing hints, agent_type
├── managed_config.lock, .config-init.lock
├── worktrees.db                             # sqlite: git worktree lifecycle tracking (see schema below) — EMPTY currently
├── relocations/*.lock                       # ~280 empty lock files, one per historical repo-move/session-relocate event
├── upload_queue/, hooks/, hooks-paths, bin/ # bin/{grok,agent} symlinks to downloads/<version>; rest empty on this machine
├── downloads/grok-{1.0.4,1.0.5,macos-aarch64}   # 336M — cached self-update binaries, prune-able
├── bundled/{agents,personas,roles,skills}/manifest.json  # built-in agent/persona/skill defs shipped with the CLI
├── installed-plugins/registry.json + skills-<hash>/      # xAI marketplace plugin install (here: cloudflare skills pack, git-cloned)
├── marketplace-cache/<hash>[.lock]          # 5 cached marketplace source listings (git repo scans)
├── docs/user-guide/*.md                     # 24 shipped help topics (memory, background-tasks, sandbox, plan-mode, permissions, hooks, monitoring-usage, subagents, dashboard, headless-mode, ...) — ground truth for feature-to-file mapping used throughout this doc
├── completions/{bash,zsh}                   # shell-completion scripts
├── vendor/rg-15.0.0-override                # bundled ripgrep binary
├── logs/
│   ├── unified.jsonl                        # 12,760 lines / 4.3M — global structured debug+telemetry log (see below)
│   └── mcp/{grok,agent-browser,open-claude-in-chrome}.stderr.log   # per-MCP-server stderr capture
├── memtrace/*.jsonl, *-jemalloc-*.txt       # 11M — allocator/RSS diagnostics dumps (crash/perf debugging only)
├── sandbox-events.jsonl                     # sandbox profile-applied events (seatbelt/macos), workspace + rw-paths per launch
├── cc-plugin/jobs/<job-group>/job-<id>.{json,log}   # background-job store backing the Claude-Code "grok:*" plugin skills (rescue/status/result/cancel) — 8 job groups, ~16 jobs
├── projects/<enc-cwd>/mcps/<server>/tools/<tool>.json   # per-project cached MCP TOOL SCHEMAS (not tool calls)
├── skills/<name>/SKILL.md                   # USER-authored skills (4 found: gh-issue-fix, tt-hot-topics-post, tt-social-post, tt-threads-post) — separate from bundled/ and installed-plugins/
└── sessions/
    ├── session_search.sqlite                # sqlite+FTS5 full-text index over session content (19 docs indexed)
    └── <url-encoded-cwd>/<session-uuid>/    # per BRIEF: summary.json, events.jsonl, updates.jsonl, chat_history.jsonl,
        │                                    #   plan_mode.json, signals.json are ALREADY read. Everything else below is NOT:
        ├── system_prompt.txt                # exact system prompt sent for this session
        ├── prompt_context.json              # inputs used to BUILD that system prompt (AGENTS.md/CLAUDE.md files loaded, memory_enabled, OS, shell, model label)
        ├── plan.json                        # `{"todos": {...}}` — Grok's TODO-list state (distinct from plan_mode.json)
        ├── rewind_points.jsonl(.lock)       # CHECKPOINT/REWIND log: one row per prompt with full file-content snapshots
        ├── hunk_records.jsonl               # line-level edit provenance: which agent/session/prompt added/removed which lines of which file
        ├── announcement_state.json          # per-session cache of MCP server fingerprints (tool_count/hash) + full list of "seen" skill names across ALL installed sources
        ├── resources_state.json             # effective per-tool resource limits/policy (timeouts, output caps, background-exec policy) as actually applied
        ├── last_recap_main_turn             # bare integer — turn index of the last auto-recap
        ├── title_refresh_idx                # bare integer (session-title regeneration cursor) — present in some sessions only
        ├── subagents/<child-uuid>/{meta.json,output.json}   # per-spawn subagent record (see below) — child is ALSO a full sibling session dir
        ├── recap_requests/<uuid>.json       # request/response log for auto-generated conversation recaps (chat_history snapshot sent to a side model)
        ├── compaction/{INDEX.md,segment_NNN.md}   # human-readable PLAN/SUMMARY artifacts written when context is compacted
        ├── compaction_requests/<uuid>.json  # raw request sent to the compaction model
        ├── compaction_checkpoints/<uuid>.json     # full pre-compaction chat_history snapshot, kept for rollback
        ├── terminal/call-<uuid>-<n>.log     # raw stdout+stderr of every Bash tool invocation, one file per call
        ├── mcp/call-<uuid>-<n>.json         # raw request/response for every MCP tool call
        ├── web_fetch/<n>.md + .allocation   # cached fetched-page bodies (markdown) per WebFetch call, with a byte-budget ledger
        └── prompts/prompt_<n>.txt           # raw text of each user prompt, one file per turn
```

### Store inventory
| Path | Format | What it holds | Cadence | Retention/cleanup | Coverage |
|---|---|---|---|---|---|
| `auth.json` | JSON | xAI OAuth session (key, refresh_token, email, user_id, team_id, oidc issuer/client — all redacted) | on login/refresh | never expires on disk (refreshed in place) | NEW (structure only, never read) |
| `config.toml` | TOML | CLI settings: default model, plugins enabled, MCP servers, marketplace sources, privacy ack | on `/config` change | single file, `.bak` kept | NEW |
| `active_sessions.json` | JSON array | live TUI processes: pid, cwd, opened_at | on launch/exit | pruned on clean exit | NEW — "is Grok running right now" signal |
| `campaigns_state.json` | JSON | dismissed launch-banner ids | on dismiss | unbounded but tiny | NEW |
| `trusted_folders.toml` | TOML | per-workspace trust decision + epoch | on first open of new dir | grows with # of trusted dirs | NEW |
| `slash-mru.json` | JSON | slash-command usage recency, by command name | every slash command | capped list | NEW — feature-usage signal |
| `models_cache.json` | JSON | full model catalog: context window, pricing hints, agent_type, hidden flags | periodic refetch | overwritten | NEW |
| `worktrees.db` | sqlite | `worktrees(id,path,source_repo,repo_name,kind,creation_mode,git_ref,head_commit,session_id,creator_pid,created_at,last_accessed_at,status,metadata)` + `meta` | on worktree create/reclaim | auto-reclaimed (CHANGELOG: "never deletes last copy") | NEW — cross-harness "worktrees" parallel; 0 rows on this machine |
| `logs/unified.jsonl` | JSONL | structured event log, every subsystem (`shell.*`, `auth.*`, `subagent *`, `billing: fetched credits config`, `marketplace handle_list`, `trace.upload.decision`, ...) | continuous while any grok process runs | unbounded, single growing file (4.3M/12.7k lines here) | **PARTIAL** — TT's `_grok_usage_from_unified_log` already parses ONLY `shell.turn.inference_done` rows for token/cost aggregation. Every other message type (tool exec, MCP calls, auth, and critically `billing: fetched credits config`) is unused. |
| `cc-plugin/jobs/*/job-*.json` | JSON | `{id,kind,prompt,status,sessionId,startedAt,finishedAt,model}` | one per grok:rescue/search background invocation from Claude Code | never cleaned (8 groups seen back to June) | NEW — backs the `grok:*` Claude-Code-plugin skills directly |
| `installed-plugins/registry.json` | JSON | marketplace plugin install records (git url/ref/commit, install/update time, plugin version) | on plugin install/update | grows with installs | NEW |
| `marketplace-cache/<hash>` | dir (git scan cache) | per-source plugin listing cache | on marketplace refresh | 5 entries, locked pairs | NEW (low value — just a scan cache) |
| `projects/<enc-cwd>/mcps/<server>/tools/<tool>.json` | JSON | cached MCP tool JSON-schema (name/description/inputSchema) | on MCP server (re)connect | one dir per project that used an MCP server | NEW — per-project MCP tool inventory |
| `skills/<name>/SKILL.md` | Markdown | user-authored skills (separate namespace from marketplace/bundled) | on skill creation | — | NEW — Grok has no skills-inventory entry in TT at all (`_collect_skills` is never called with `GROK_DIR`) |
| `sessions/session_search.sqlite` | sqlite+FTS5 | `session_docs(session_id,cwd,updated_at,title,content,content_hash,last_indexed_offset)` + FTS5 virtual table | reindexed on memory/session search | 19 docs currently | NEW (low priority — a search index, not a source of truth) |
| `sessions/<enc>/<uuid>/rewind_points.jsonl` | JSONL | `{prompt_index, created_at, file_snapshots:{path:content}, after_snapshots}` | one row per prompt where files changed | grows with session; snapshots hold FULL file content at that point | NEW — this **is** Grok's checkpoint/rewind feature (`/rewind` in the docs) |
| `sessions/<enc>/<uuid>/hunk_records.jsonl` | JSONL | `{hunkId, filePath, hunkStart/End, linesAdded, linesRemoved, authorType, authorId, agentId, sessionId, timestamp, promptIndex, sourceType, eventType}` | one row per edited hunk | 975 rows in the sampled session | NEW — per-file/per-agent edit-density analytics |
| `sessions/<enc>/<uuid>/subagents/<id>/meta.json` | JSON | `{subagent_id, parent_session_id, child_session_id, subagent_type, description, prompt, status, started_at, completed_at, duration_ms, tool_calls, turns, effective_context_source, resumed_from, child_cwd, effective_model_id}` | one dir per spawned subagent (130 in the busiest session sampled) | never cleaned | **COVERED** by `_grok_subagent_meta()` — all fields it reads (`agent_id/agent_type/description/status/duration_ms/tool_calls/turns/model/child_session_id`) match. NOT read: `resumed_from` (subagent-resumed-a-prior-subagent chaining) and `prompt`. |
| `sessions/<enc>/<uuid>/subagents/<id>/output.json` | JSON | `{schema_version, output: "<final markdown result>"}` | same cadence | — | NEW — the subagent's actual final answer is never surfaced, only its metadata |
| `sessions/<enc>/<uuid>/plan.json` | JSON | `{"todos": {...}}` | live todo-list state | overwritten | NEW — distinct from `plan_mode.json` (which IS read) |
| `sessions/<enc>/<uuid>/announcement_state.json` | JSON | `mcp_server_fingerprints` (tool_count + hashes per connected MCP server) + `announced_skill_names` (full catalog of every skill Grok has ever surfaced to the user, across every install source: bundled, marketplace, tokentelemetry:*, gemini:*, codex:*, grok:*, cloudflare:*) | updated as new MCP servers/skills are seen | — | NEW — a full point-in-time skills+MCP inventory per session, free of extra scanning |
| `sessions/<enc>/<uuid>/prompt_context.json` | JSON | `{prompt_mode, audience, agents_md_files:[{file_name,file_path,content}], memory_enabled, os_name, shell_path, working_directory, system_prompt_label}` | built once per session | — | NEW — shows exactly which AGENTS.md/CLAUDE.md files were loaded into context (already-covered file literals `AGENTS.md`/`CLAUDE.md` are consumed here but this JSON is not read) |
| `sessions/<enc>/<uuid>/resources_state.json` | JSON | effective per-tool policy: `grok_build.Bash.{timeout_secs, output_byte_limit, enabled_background, ...}`, `grok_build.ReadFile.*`, `grok_build.SearchReplace.*` | per session | — | NEW — permissions/config cross-harness parallel |
| `sessions/<enc>/<uuid>/compaction/{INDEX.md,segment_NNN.md}` | Markdown | human-readable compaction summaries with a keyword-tagged index table | on auto-compact | one segment file per compaction event | NEW — closest thing Grok has to a "plan artifact" / session recap doc |
| `sessions/<enc>/<uuid>/compaction_checkpoints/<id>.json` | JSON | `{checkpoint_id, prompt_index_at_compaction, compacted_history, original_user_info, reread_file_paths}` | on compaction | — | NEW |
| `sessions/<enc>/<uuid>/recap_requests/<id>.json` | JSON | `{request_id, created_at, trigger, model, chat_history, summary, error}` | on auto-recap (for session titles) | — | NEW |
| `sessions/<enc>/<uuid>/terminal/call-<id>-<n>.log` | plain text | raw stdout+stderr per Bash call | one file per bash tool call | unbounded | NEW — could back a "commands run" surface, but high volume |
| `sessions/<enc>/<uuid>/mcp/call-<id>-<n>.json` | JSON | raw MCP request/response | one per MCP call | unbounded | NEW |
| `sessions/<enc>/<uuid>/web_fetch/<n>.md` + `.allocation` | Markdown + JSON | fetched page bodies + a byte-budget ledger | one per WebFetch | unbounded | NEW |
| `sessions/<enc>/<uuid>/system_prompt.txt` | plain text | the literal system prompt for that session | once | — | NEW (low priority — mostly boilerplate) |

### Schemas
Already inlined above (JSON keys, values elided) for: auth.json (redacted), active_sessions.json,
worktrees.db `.schema`, session_search.sqlite `.schema`, job-*.json, subagents/meta.json,
subagents/output.json, plan.json, resources_state.json, announcement_state.json,
prompt_context.json, rewind_points.jsonl (one row), hunk_records.jsonl (one row),
recap_requests/*.json, compaction_checkpoints/*.json.

`billing: fetched credits config` (a `logs/unified.jsonl` row, not a session file) — this is
Grok's **usage/quota state**, refetched periodically and logged inline:
```json
{"msg":"billing: fetched credits config","ctx":{
  "config":{"creditUsagePercent":29.0,
            "currentPeriod":{"type":"USAGE_PERIOD_TYPE_WEEKLY","start":"<iso>","end":"<iso>"},
            "onDemandCap":{"val":0},"onDemandUsed":{"val":0},"prepaidBalance":{"val":0},
            "isUnifiedBillingUser":true,
            "billingPeriodStart":"<iso>","billingPeriodEnd":"<iso>","historyLen":0},
  "onDemandEnabled":null,"subscriptionTier":"X Premium"}}
```

### Dashboard candidates (ranked, value × ease)
1. **Subscription usage meter** (high value, easy): parse `billing: fetched credits config` rows
   out of the already-opened `unified.jsonl` — zero new file to read, just a new msg-type filter.
   Shows `creditUsagePercent`, `subscriptionTier`, weekly/billing period bounds. Directly answers
   "how close am I to my Grok quota."
2. **Background jobs panel** (high value, easy): `cc-plugin/jobs/*/job-*.json` — surfaces every
   `grok:rescue`/`grok:search` invocation launched from Claude Code, with status/kind/timing. This
   is Grok's literal "background tasks" store and nothing reads it today.
3. **Rewind/checkpoint timeline** (medium-high value, medium ease): `rewind_points.jsonl` — list
   timestamps + which files were snapshotted per prompt (never surface file *content*, just counts
   and paths) as a rewind-point picker, mirroring what `/rewind` shows the user live.
4. **Subagent delegation, upgraded** (medium value, easy — data already partially read): add
   `output.json` (final result text, truncated) and `resumed_from` (chain subagents that resumed
   other subagents) to the existing `/sessions/{id}/delegation`-style view.
5. **Edit provenance / hunk heatmap** (medium value, medium ease): `hunk_records.jsonl` aggregated
   by file → "which files did the agent touch most, added vs removed lines" — good complement to
   existing token/cost analytics.
6. **Skills+MCP inventory without a live scan** (medium value, easy): `announcement_state.json`'s
   `announced_skill_names` + `mcp_server_fingerprints` give a free per-session snapshot of every
   skill/MCP tool the session actually saw — cross-check against the live marketplace/plugin scan.
7. **Compaction summaries as session recap** (low-medium value, easy): `compaction/INDEX.md` +
   `segment_NNN.md` are literally human-readable session recaps Grok already wrote — could feed a
   "what happened in this long session" view for free.
8. **Worktree lifecycle** (low value here — 0 rows — but cross-harness parity is valuable):
   `worktrees.db` schema is ready to surface once populated; matches Claude Code's own worktree UI.

### Cross-harness parallels
- **background jobs**: `cc-plugin/jobs/` (Claude-Code-plugin-launched Grok jobs)
- **schedules/cron**: `/loop` scheduler — already detected via `chat_history.jsonl` regex in
  `_grok_loop_detect()`; no separate on-disk store found beyond that.
- **memory**: `~/.grok/memory/` (Markdown + sqlite index) — **disabled by default**
  (`GROK_MEMORY=0`), not present on this machine; doc-verified path structure only.
- **todos**: `sessions/<enc>/<uuid>/plan.json` (`{"todos":{}}`) — separate from `plan_mode.json`.
- **checkpoints/rewind**: `rewind_points.jsonl` with full file-content snapshots.
- **plan artifacts**: `compaction/*.md` (auto-generated) + `plan_mode.json` (already read).
- **MCP + tools inventory**: `announcement_state.json` (fingerprints) + `projects/<enc>/mcps/*/tools/*.json` (schemas) + `logs/mcp/*.stderr.log` (per-server errors).
- **usage/quota/rate-limit state**: `billing: fetched credits config` rows in `unified.jsonl`.
- **permissions/config**: `config.toml` (`[ui] permission_mode`) + per-session `resources_state.json`.
- **subagents**: `sessions/<enc>/<uuid>/subagents/<id>/{meta.json,output.json}`.
- **hooks**: `~/.grok/hooks/`, `hooks-paths` — both empty on this machine; doc `10-hooks.md` describes the feature.
- **model config**: `models_cache.json` (catalog) + `config.toml [models]`.
- **worktrees**: `worktrees.db`.
- **IDE integration**: `mcp_servers.agent-browser` in `config.toml` (a local Node MCP server bridging Chrome).

### Gotchas
- `GROK_HOME` env var relocates the entire `~/.grok` root — a scanner hardcoding `~/.grok` misses
  anyone who set this.
- `GROK_CONFIG_PATH` / `GROK_CONFIG` env vars override `config.toml` contents without touching the file on disk — don't assume `config.toml` is the full picture of effective config.
- `GROK_SESSION_ID` env var lets headless invocations resume a specific session — relevant if
  correlating `cc-plugin/jobs/*.json`'s `sessionId` field to a `sessions/` directory.
- Session dirs live under a **URL-encoded cwd** path segment (`%2FUsers%2F...`), same convention as
  BRIEF's already-covered files — `find`/`ls` need percent-decoding awareness, and shell globs with
  literal `%` need quoting.
- `unified.jsonl` is a single ever-growing file across ALL projects/sessions (not per-session) —
  any new parser needs the same mtime/size cache-key pattern `_grok_usage_from_unified_log` already
  uses, or a full rescan will get expensive as it grows.
- `rewind_points.jsonl` embeds **full file contents** in `file_snapshots` — treat as sensitive,
  never surface raw content in any UI, only counts/paths/timestamps.
- `last-copy.txt` and `prompts/prompt_N.txt` and `chat_history.jsonl` all contain **raw user text**
  verbatim — must never be echoed into a published surface.
- Locks (`*.lock`) sit next to nearly every mutable JSON file — always skip `.lock` siblings when
  glob-scanning a directory for real content.
- `memory/` only appears if the user has ever enabled `GROK_MEMORY=1` — absence is normal, not a bug.

---

## Qwen Code CLI — `~/.qwen`, 8.6M, 448 files

**Agent identity / still active?** Qwen Code, a Gemini-CLI fork (Alibaba). Session-log `version`
field shows `0.7.1`. Latest touched files (`ide/*.lock`, Aug 1 2026) suggest a VS Code integration
was opened then, but the last real chat activity in `projects/*/chats/*.jsonl` and `debug/*.txt`
dates to around **June 20, 2026** — effectively dormant for ~2 months as of today.

### Directory map
```
~/.qwen/
├── settings.json, settings.json.orig        # $version 3 vs 2 — settings.json.orig is a pre-migration backup
├── installation_id                          # stable per-install UUID
├── oauth_creds.json                         # {access_token, token_type, refresh_token, resource_url, expiry_date} — ALL REDACTED
├── output-language.md                       # project-rule-style file: forces English output, preserves code/paths verbatim
├── tip_history.json                         # {sessionCount, tips:{<tip-id>:{totalShown,lastSessionTimestamp}}}
├── ide/<port>.lock                          # VS Code IDE-integration lock: {port, workspacePath, ppid, authToken, ideName} — authToken REDACTED
├── debug/<session-uuid>.txt (+ "latest" symlink)   # per-session verbose debug log (hook registry init, extension manager, OAuth flow)
├── tmp/<sha256-of-cwd>/{logs.json, shell_history}   # per-project scratch dir (see below)
├── todos/<session-uuid>.json                # {"todos":[{"content","id","status"}], "sessionId"} — Qwen's TodoWrite-equivalent state
├── skills/<name>/SKILL.md                   # marketplace-installed skills (same Cloudflare pack as Grok/Vibe/OpenClaw — shared install, not Qwen-specific)
└── projects/<enc-cwd>/chats/<uuid>.jsonl     # ALREADY READ by TT (session scan) — 8 project dirs, ~15 chat files
```

### Store inventory
| Path | Format | What it holds | Cadence | Retention/cleanup | Coverage |
|---|---|---|---|---|---|
| `projects/<enc>/chats/<uuid>.jsonl` | JSONL | full transcript, `{uuid,parentUuid,sessionId,timestamp,type,cwd,version,message:{role,parts/content}}` | one line per turn | unbounded | **COVERED** — TT's session scanner already reads this for tokens/model/tool_use/skill activation/plan detection |
| `settings.json` | JSON | `{ide:{enabled}, security:{auth:{selectedType}}, permissions:{allow:[...]}, ui:{}}` | on `/settings` change | `.orig` kept as pre-migration backup | NEW |
| `oauth_creds.json` | JSON | OAuth token set (all fields sensitive) | on login/refresh | overwritten | NEW (structure only) |
| `todos/<uuid>.json` | JSON | live todo list per session | on TodoWrite-equivalent call | one file per session that used todos (8 found) | NEW — direct "todos" cross-harness parallel |
| `tmp/<sha256(cwd)>/logs.json` | JSON array | `{sessionId, messageId, type, message}` — a SECOND, older transcript log, keyed by hashed cwd rather than encoded path | per turn | 6 project-hash dirs found, oldest Dec 2025 | NEW — appears to be a legacy/duplicate log path pre-dating `projects/*/chats/`; contains raw prompt text |
| `tmp/<hash>/shell_history` | plain text | raw shell command + full stdout/stderr transcript | appended per Bash tool call | unbounded | NEW — raw command output, treat as sensitive |
| `debug/<uuid>.txt` | plain text log | startup/auth/hook/extension diagnostic log | per session | one file per session, `latest` symlink | NEW — mentions "Hook registry initialized" (0 entries here) confirming Qwen has a hook system |
| `ide/<port>.lock` | JSON | active VS Code integration handshake (port, workspace, authToken) | while IDE extension connected | removed on disconnect (2 stale locks present) | NEW — IDE-integration signal |
| `tip_history.json` | JSON | onboarding-tip impression tracker | per session | tiny, capped | NEW (low value) |
| `output-language.md` | Markdown | output-language project rule | user-set once | — | NEW (low value, config-like) |
| `installation_id` | plain text UUID | anonymous install id | set once | — | NEW (low value) |

### Schemas
Inlined above for: todos/*.json, tmp/*/logs.json (one record), settings.json, settings.json.orig,
oauth_creds.json (redacted), ide/*.lock (redacted authToken).

### Dashboard candidates
1. **Todos panel** (medium value, easy): `todos/<uuid>.json` directly maps session → live task list
   with status — same shape Claude Code / Grok expose, trivial to add as a "Todos" tab per session.
2. **IDE-connected indicator** (low-medium value, easy): `ide/*.lock` existence + `workspacePath` →
   "Qwen is currently attached to VS Code in project X."
3. **Legacy log reconciliation** (low value, medium ease): `tmp/<hash>/logs.json` predates the
   `projects/*/chats/*.jsonl` scanner and covers sessions from Dec 2025–Apr 2026 that may not appear
   in `projects/` at all if the hash scheme changed — worth a one-time backfill check for older
   sessions currently invisible to the dashboard.
4. **Permissions view** (low value, easy): `settings.json.permissions.allow` — same shape as Claude
   Code's own permission allowlist, could feed a unified "what can each agent auto-run" page.

### Cross-harness parallels
- **todos**: `todos/<uuid>.json`.
- **memory**: none found — no `QWEN.md`/memory directory present on this machine despite BRIEF's
  lead (`memory/QWEN.md`); Qwen (as a Gemini-CLI fork) likely follows Gemini's project-memory
  convention (`GEMINI.md`/`QWEN.md` in-repo) rather than a home-dir store — not present under `~/.qwen`.
- **permissions/config**: `settings.json.permissions.allow` (Bash allowlist patterns).
- **hooks**: debug log confirms a hook registry exists (`[HOOK_REGISTRY]`), 0 entries configured here — no on-disk hook config file found.
- **IDE integration**: `ide/<port>.lock`.
- **usage/quota**: none found (no billing/credits file under `~/.qwen`).

### Gotchas
- Two DIFFERENT transcript stores exist (`projects/*/chats/*.jsonl` keyed by URL-encoded cwd, and
  `tmp/<sha256>/logs.json` keyed by a hash of cwd) — they don't necessarily agree on which sessions
  exist; a naive "list all qwen sessions" that only reads one will silently miss the other's history.
- `settings.json.orig` is NOT a live config — it's a one-time backup taken during a schema
  migration (`$version` 2→3); don't merge it back in as if it were current.
- `oauth_creds.json` and `ide/*.lock` both carry live bearer tokens — never print raw.
- Extremely stale on this machine (~2 months) — don't assume `~/.qwen` presence means active daily use; check latest `projects/*/chats/*` mtime, not just directory existence, before showing Qwen as "active."

---

## Vibe — `~/.vibe`, 2.5M, 398 files — identified as **Mistral Vibe CLI** (mistral-vibe), NOT vibe-kanban

**Agent identity / still active?** `config.toml` and `vibe.log` both point unambiguously to
`mistralai/mistral-vibe` — Mistral's own terminal coding agent, using `devstral-*` models via the
Mistral API (or a local llama.cpp backend for a `"local"` alias). This is **not** vibe-kanban (a
Rust/React Claude-Code-orchestration board) — no kanban, task-board, or PR-orchestration files
exist anywhere under this directory. Last real chat activity: a session dated 2026-04-08, followed
only by three bare "Using config" startup pings on 2026-07-16 with **no** completions call after —
effectively dormant since April 2026 (two 401 Unauthorized errors on that April 8 session suggest
the API key may have gone stale, which likely explains the abandonment).

### Directory map
```
~/.vibe/
├── .env                                     # MISTRAL_API_KEY=<redacted> — plaintext API key on disk
├── config.toml                              # full CLI config: providers, models+pricing, tool permissions (see below)
├── instructions.md                          # empty (0 bytes) — project-rule file, unused
├── vibehistory                              # flat list of past top-level prompts (one per line, quoted) — RAW USER TEXT
├── vibe.log                                 # plain-text app log: config loads, GitHub release checks, HTTP request/response status lines
├── skills/<name>/SKILL.md                   # same shared Cloudflare marketplace pack as the other 3 harnesses
└── logs/session/session_<YYYYMMDD_HHMMSS>_<hash>.json   # ALREADY READ by TT — full per-session record (see below); only 2 files exist
```

### Store inventory
| Path | Format | What it holds | Cadence | Retention/cleanup | Coverage |
|---|---|---|---|---|---|
| `logs/session/session_*.json` | JSON | `metadata:{session_id,start_time,end_time,git_commit,git_branch,environment:{working_directory},auto_approve,username,stats:{steps,session_prompt_tokens,session_completion_tokens,tool_calls_agreed/rejected/failed/succeeded,context_tokens,last_turn_*,tokens_per_second,input_price_per_million,output_price_per_million,session_total_llm_tokens,session_cost},total_messages,tools_available:[...]}` + `messages:[{role,content}]` | one file per CLI invocation | 2 files (Dec 2025, Apr 2026) | **PARTIAL** — TT reads `stats.session_prompt_tokens/session_completion_tokens/context_tokens/session_total_llm_tokens`, `agent_config.active_model`(*), and `tools_available` names, then RECOMPUTES cost via `calculate_cost()`. NOT read: `git_commit`/`git_branch`, `username`, `auto_approve`, `tool_calls_agreed/rejected/failed/succeeded` (tool-outcome breakdown), `tokens_per_second`, the session's OWN `session_cost` (uses Vibe's actual per-model $/M pricing from `config.toml`, which may differ from TT's `calculate_cost` table for `devstral-*` aliases), and the full `messages` transcript itself (only `tools_available` is used from the tool list; message content is never parsed for plan/todo detection the way Qwen's `thinking` blocks are). |
| `config.toml` | TOML | providers (mistral, llamacpp), models with real `input_price`/`output_price` per million, tool-permission policy (`[tools.bash].allowlist/denylist/denylist_standalone`, `[tools.grep]`, `[tools.write_file]`, etc.), `[session_logging]` | on `/config` change | single file | NEW |
| `.env` | dotenv | `MISTRAL_API_KEY` | set once | plaintext on disk | NEW (structure only — key redacted) |
| `vibehistory` | plain text, one quoted string per line | flat history of top-level prompts across all sessions | appended each prompt | unbounded, 3 lines here | NEW — raw user text, do not surface verbatim |
| `vibe.log` | plain text | app-level log: config path, GitHub release-check calls, Mistral API call status codes (200/401) | continuous | unbounded, single file | NEW — good source for "is auth broken" (401 rows) without opening `.env` |
| `instructions.md` | Markdown | project/system-instructions override | user-set | empty here | NEW (unused on this machine) |

### Schemas
Inlined above: full `session_*.json` metadata block including `stats`, and first `messages[0]`
(system prompt, elided) and `tools_available[0]` (function-calling schema, elided).

### Dashboard candidates
1. **Tool-call outcome breakdown** (medium value, easy — file already opened): `stats.tool_calls_agreed/rejected/failed/succeeded` gives an approval/failure rate per session that TT currently discards. Cheap add since the file is already parsed for tokens.
2. **Auth-health indicator** (medium value, easy): scan `vibe.log` for the last HTTP status line — surfaces the same 401-then-abandoned pattern found on this machine, i.e. "this agent stopped being usable because its key expired," which is exactly the kind of insight a user wouldn't otherwise notice.
3. **Native cost vs TT's cost** (low-medium value, easy): `stats.session_cost` uses the session's OWN `input_price_per_million`/`output_price_per_million` (pulled live from `config.toml` at run time) — compare against TT's `calculate_cost()` result for the same session as a sanity check, since Mistral's `devstral-2`/`devstral-small` aliases may not be in TT's pricing table.
4. **Permissions/tool-policy view** (low value, easy): `config.toml`'s per-tool `allowlist`/`denylist`/`denylist_standalone` — same shape as Qwen's `settings.json.permissions`, could unify into one "agent tool policy" comparison page across harnesses.

### Cross-harness parallels
- **permissions/config**: `config.toml [tools.*]` (per-tool allow/deny lists + `permission: ask|always`), `[tools.bash].denylist_standalone` (blocks bare interpreters like `python`, `bash`, `vim`).
- **model config**: `config.toml [[models]]` with literal `input_price`/`output_price` per million tokens — Vibe is unusual in shipping its own ground-truth pricing table instead of relying on a shared pricing DB.
- **usage/quota**: none found (no separate credits/billing file; per-session `stats` is the only usage record).
- **memory/todos/checkpoints/subagents/hooks/MCP/worktrees/IDE**: **none found** — `config.toml` has `mcp_servers = []` (empty) and no subagent, hook, checkpoint, or IDE-integration file/section exists anywhere under `~/.vibe`. Vibe appears to be a deliberately minimal single-agent, single-turn-loop CLI with no delegation or checkpoint model.

### Gotchas
- Directory name (`.vibe`) collides in spirit with "vibe-kanban" — **do not conflate them**; this
  machine's `.vibe` is 100% Mistral Vibe CLI, confirmed by `config.toml`'s `mistralai/mistral-vibe`
  GitHub-release-check URL and `api.mistral.ai` base URL.
- `.env` holds a plaintext API key at the harness root (not under a `credentials/` subdir like most
  other harnesses) — a naive "scan for secrets to skip" pattern keyed on filename (`auth.json`,
  `credentials.json`) could miss it.
- `session_*.json`'s `stats.session_cost` and `tokens_per_second` fields are **all zero** in the
  sampled Apr-2026 file because the two completions calls both 401'd before any tokens were billed
  — don't treat a `0.0` cost as "free," check `stats.steps`/`tool_calls_failed` too.
- Only 2 session files exist total on this machine (Dec 2025, Apr 2026) — any per-agent dashboard
  panel needs to degrade gracefully to "barely used" rather than assume a rich history exists.

---

## OpenClaw — `~/.openclaw`, 2.4M, 392 files — a Claude-Code-compatible skills-based CLI, essentially unused on this machine

**Agent identity / still active?** Confirmed (via an unrelated third-party skill-installer project
on this machine, `explore-oss/llm-wiki-skill/platforms/openclaw/README.md`) that "OpenClaw" is a
coding-agent CLI that, like Claude Code/Grok/Qwen, installs skills under `~/.openclaw/skills/`. No
further first-party documentation, binary, or `which openclaw` was found on this machine — it may
not even be installed as a CLI, just have had its skills directory seeded by a marketplace/plugin
install. **Not active**: every file's mtime is June 20, 2026 or earlier (skills install) except
`claw3d/` (May 26, 2026) and `workspace/` (Feb 4, 2026, and still empty) — nothing from the last two
months. No session logs, no chat transcripts, no auth file, no config beyond one small JSON, exist
anywhere in the tree.

### Directory map
```
~/.openclaw/
├── workspace/                                # EMPTY (0 files) — presumably OpenClaw's default working-copy sandbox root, never used
├── claw3d/
│   └── settings.json                        # {"adapter":"hermes","url":"ws://localhost:18789","token":""} — a companion "claw3d" feature that bridges to a Hermes-adapter websocket
└── skills/<name>/{SKILL.md,references/,scripts/,templates/,tests/}   # the SAME Cloudflare marketplace skill pack (agents-sdk, cloudflare, cloudflare-email-service, durable-objects, sandbox-sdk, turnstile-spin, web-perf, workers-best-practices, wrangler) seen verbatim in ~/.grok, ~/.qwen, ~/.vibe — 350+ of the 392 files are this shared pack (references/ subtrees, e.g. cloudflare/references/ alone has 70+ topic files)
```

### Store inventory
| Path | Format | What it holds | Cadence | Retention/cleanup | Coverage |
|---|---|---|---|---|---|
| `claw3d/settings.json` | JSON | `{adapter, url, token}` — websocket connection config pointing at `ws://localhost:18789` with adapter type `"hermes"` | set once | unconfigured (empty token) here | NEW — the only OpenClaw-specific artifact found; hints at a live integration with the user's own Hermes harness (a Databricks meta-harness already tracked by TT) rather than anything OpenClaw-native |
| `skills/**/*` | Markdown + shell scripts | marketplace skill content, byte-identical in structure to the Grok/Qwen/Vibe copies | on marketplace install | static until re-installed | NEW to OpenClaw specifically, but **not agent-specific data** — this is shared third-party skill content, not user telemetry; low priority to parse per-harness since it duplicates what's already visible via Grok/Qwen/Vibe's copies |
| `workspace/` | dir | empty | — | — | N/A — no data |

### Schemas
`claw3d/settings.json` — full file shown above (no redaction needed, `token` field is empty string
on this machine; if populated it would need `<redacted>` treatment as a connection credential).

### Dashboard candidates
Given the near-total absence of first-party data, there is currently **nothing worth building** for
OpenClaw specifically on this machine:
1. **"Not yet used" state** (trivial): if `~/.openclaw` exists but has no session/chat/log file
   newer than the skills-install mtime, show OpenClaw in the agent list with a "detected, not yet
   used" badge rather than fabricating a dashboard from skill-pack metadata.
2. **Claw3D/Hermes bridge indicator** (speculative, low value without more evidence): if
   `claw3d/settings.json.token` is ever non-empty, that's a signal OpenClaw is actively bridging to
   a running Hermes instance on `localhost:18789` — worth a one-line "connected to Hermes" note if
   that ever fires, but not worth building against on spec.

### Cross-harness parallels
None found — no session store, no config beyond the one settings.json, no auth, no MCP, no todos,
no memory, no hooks, no subagents on this machine. This survey cannot distinguish "OpenClaw has
none of these features" from "OpenClaw has them but this install has simply never been used" —
treat as **inconclusive, re-survey once real usage exists**.

### Gotchas
- `~/.openclaw/skills/` is near-100% shared marketplace content, not OpenClaw-specific — a scanner
  that walks every `SKILL.md` under every harness root and treats them as distinct data will triple-
  or quadruple-count the same Cloudflare skill pack (it's byte-for-byte identical across `.grok`,
  `.qwen`, `.vibe`, `.openclaw` on this machine — likely a shared git-clone-based marketplace
  install mechanism common to several of these CLIs).
- `claw3d` is a directory, not a file — a naive scanner checking `path.is_file()` before reading
  will skip it silently.
- Do not infer OpenClaw is "inactive as a product" from this survey — this specific machine simply
  never ran it beyond an initial skill install; the dormancy finding is about *this user's usage*,
  not the CLI itself.

---

## Summary of genuinely new, high-value finds (cross-file)

1. **Grok subscription usage %** — sitting unused inside a log TT already parses (`unified.jsonl`, `billing: fetched credits config` rows). Cheapest possible win.
2. **Grok background jobs** (`cc-plugin/jobs/`) — directly backs the `grok:rescue/status/result/cancel` Claude-Code skills; currently invisible to TT.
3. **Grok rewind points / hunk records** — genuine checkpoint and edit-provenance data with no TT equivalent for any harness.
4. **Grok has no skills-inventory entry at all** (`_collect_skills` never called with `GROK_DIR`), unlike Qwen — a real gap, not just missing detail.
5. **Vibe's per-session tool-call outcome counts and native `session_cost`/pricing** are read out of a file TT already opens but discarded — cheap to add.
6. **Qwen has a second, older, hash-keyed transcript log** (`tmp/<sha256>/logs.json`) that may cover sessions invisible to the current `projects/*/chats/*.jsonl` scanner — worth checking for coverage gaps on older histories.
7. **`.vibe` is Mistral's CLI, not vibe-kanban** — correct this identification anywhere in TT that assumes otherwise.
8. **OpenClaw has essentially no local footprint to mine** on this machine — don't overinvest here; the shared marketplace `skills/` content is noise, not signal, across all four harnesses.
