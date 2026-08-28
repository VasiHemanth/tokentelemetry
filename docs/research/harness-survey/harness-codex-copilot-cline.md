# Codex / Copilot CLI / Cline — survey (done by lead after subagent hit session limit)

## OpenAI Codex — `~/.codex`, 1.0G, 9477 files
Version 0.146.0 (`version.json`). Electron app + CLI sharing one dir. Very active.

### Directory map (depth 1, annotated)
```
~/.codex/
├── sessions/YYYY/MM/DD/rollout-*.jsonl   289M, 133 rollout files  [COVERED]
├── plugins/                              328M — cache/<marketplace>/<plugin>/  [COVERED]
│   ├── cache/openai-bundled/{visualize,sites,browser,chrome,computer-use,codex-app-tools}
│   ├── cache/openai-primary-runtime/{documents,presentations,pdf,spreadsheets,template-creator}
│   ├── cache/openai-curated-remote/{openai-templates,plugin-management}
│   └── cache/grok-mcp/grok
├── logs_2.sqlite                          96M, 23511 rows          [NEW]
├── computer-use/                          69M — "Codex Computer Use.app" + config.json [NEW]
├── thread_history_1.sqlite                23M — per-turn projection [NEW]
├── cache/                                 21M — codex_app_directory, codex_apps_server_info,
│                                          codex_apps_tools, remote_plugin_catalog [NEW]
├── sqlite/                                15M — dev copies (codex-dev.db, codex-history-snapshots-dev.db,
│                                          codex-thread-summaries-dev.db) [NEW, dev-only, skip]
├── vendor_imports/                        7.8M [NEW]
├── skills/                                5.4M — 39 skill dirs [PARTIAL]
├── state_5.sqlite                         2.0M — THE thread registry [NEW — highest value]
├── dictation-history/                     1.8M — 7 voice-input blobs [NEW, SENSITIVE]
├── generated_images/ (1), attachments/ (5), visualizations/2026/08/ [NEW]
├── ambient-suggestions/<sha1>/ambient-suggestions.json  [NEW]
├── automations/<id>/{automation.toml,memory.md}         [NEW — the "schedules" store]
├── browser/{config.toml, sessions/<uuid>.toml}          [NEW]
├── memories_1.sqlite, goals_1.sqlite, queue_1.sqlite    [NEW]
├── worktrees/<short-sha>/                               [NEW]
├── process_manager/chat_processes.json  (live PIDs, "[]" when idle) [NEW]
├── rules/default.rules, shell_snapshots/, log/, ipc/, tmp/
├── config.toml, config.json, .codex-global-state.json   [PARTIAL]
├── models_cache.json (196K), session_index.jsonl (52), history.jsonl (31)
├── auth.json  [COVERED — auth_mode only; NEVER read tokens]
├── version.json, update-check.json, installation_id
├── chrome-native-hosts{,-v2}.json, transcription-history.jsonl [SENSITIVE]
└── AGENTS.md, instructions.md, memories/, pets/, node_repl/, mcp-oauth-locks/
```

### Store inventory
| Path | Format | Holds | Coverage |
|---|---|---|---|
| `state_5.sqlite` → `threads` (132) | sqlite | full thread registry | **NEW** |
| `state_5.sqlite` → `thread_spawn_edges` (60) | sqlite | parent→child delegation graph | **NEW** |
| `state_5.sqlite` → `thread_dynamic_tools` (12) | sqlite | per-thread tool defs + input_schema | **NEW** |
| `state_5.sqlite` → `remote_control_enrollments` (1) | sqlite | remote-control pairing | **NEW** |
| `thread_history_1.sqlite` → `thread_turns` (19) | sqlite | per-turn status/duration/error | **NEW** |
| `thread_history_1.sqlite` → `thread_items` (2519) | sqlite | per-item projection of rollouts | **NEW** |
| `logs_2.sqlite` → `logs` (23511) | sqlite | structured app log, thread-scoped | **NEW** |
| `goals_1.sqlite` → `thread_goals` (0) | sqlite | per-thread objective + token budget | **NEW** |
| `memories_1.sqlite` → `stage1_outputs`/`jobs` (0) | sqlite | memory-distillation pipeline | **NEW** |
| `queue_1.sqlite` → `queued_items` (0) | sqlite | queued follow-up messages | **NEW** |
| `automations/<id>/automation.toml` | toml | **cron + heartbeat schedules** | **NEW** |
| `config.toml` `[projects."<path>"]` | toml | per-project `trust_level` | **NEW** |
| `browser/sessions/<uuid>.toml` | toml | browser-tool session state | **NEW** |
| `ambient-suggestions/<sha1>/…json` | json | proactive suggestions per project root | **NEW** |

### Schemas (values elided)

`state_5.sqlite` → `threads`:
```
id, rollout_path, created_at, updated_at, source, model_provider, cwd, title,
sandbox_policy, approval_mode, tokens_used, has_user_event, archived, archived_at,
git_sha, git_branch, git_origin_url, cli_version, first_user_message, agent_nickname,
agent_role, memory_mode, model, reasoning_effort, agent_path, created_at_ms,
updated_at_ms, thread_source, preview, recency_at(_ms), history_mode, name,
is_pinned, thread_section_id → thread_sections(id), section_position,
section_entered_at_ms, project_id → projects(id)
```
`thread_spawn_edges`: `parent_thread_id, child_thread_id PK, status`  ← delegation
`thread_dynamic_tools`: `thread_id, position, name, description, input_schema, defer_loading, namespace`

`thread_history_1.sqlite` → `thread_turns`:
```
thread_id, turn_id, rollout_ordinal, status, error_json, started_at, completed_at,
duration_ms, first_user_item_id, final_agent_item_id, rollout_byte_offset,
rollout_end_ordinal, rollout_end_byte_offset
```
(`thread_items` carries `item_json`, `item_type`; a partial index exists on `item_type='userMessage'`.)

`goals_1.sqlite` → `thread_goals`:
```
thread_id PK, goal_id, objective, status CHECK IN
  ('active','paused','blocked','usage_limited','budget_limited','complete'),
token_budget, tokens_used, time_used_seconds, created_at_ms, updated_at_ms
```

`logs_2.sqlite` → `logs`:
```
id, ts, ts_nanos, level, target, feedback_log_body, module_path, file, line,
thread_id, process_uuid, estimated_bytes
```

`automations/<id>/automation.toml` (real example, prompt elided):
```toml
version = 1
id = "weekly-review"
kind = "cron"                # also seen: "heartbeat"
name = "Weekly review"
prompt = "<elided>"
status = "ACTIVE"
rrule = "RRULE:FREQ=WEEKLY;BYHOUR=16;BYMINUTE=0;BYDAY=FR"
model = "gpt-5.6-terra"
reasoning_effort = "high"
execution_environment = "local"
target = { type = "project", project_id = "<uuid>" }
cwds = ["<repo path>"]
created_at = <ms>, updated_at = <ms>
```
Sibling `memory.md` accumulates notes across runs of that automation.
Two live on this machine: `weekly-review` (cron), `hourly-threads-ai-news-posting` (heartbeat, RRULE:FREQ=HOURLY;INTERVAL=1).

`config.toml` globals: `model`, `model_reasoning_effort`, `service_tier`, `notify[]`,
`approval_policy` (= `never` here), `approvals_reviewer`, `sandbox_mode`
(= `danger-full-access` here), `[mcpServers.<name>]`, and ~15+
`[projects."<abs path>"] trust_level = "trusted"` entries.

`.codex-global-state.json` keys (Electron): `local-projects`, `selected-project`,
`pinned-project-ids`, `pinned-thread-ids`, `thread-project-assignments`,
`projectless-thread-ids`, `queued-follow-ups`, `thread-titles`, `project-order`,
`codex-mobile-has-connected-device`, `selected-remote-host-id`,
`electron-local-remote-control-{installation,environment}-id`, window bounds, misc flags.

`auth.json` keys only: `auth_mode` (= `chatgpt`), `OPENAI_API_KEY` `<redacted>`,
`tokens` `<redacted>`, `last_refresh`.

`models_cache.json`: `fetched_at`, `etag`, `client_version`, `models[]`.
`session_index.jsonl`: `{id, thread_name, updated_at}` × 52.
`history.jsonl`: `{session_id, ts, text}` × 31 — raw prompt text, SENSITIVE.

### Dashboard candidates (ranked)
1. **Scheduled automations** — name, kind (cron/heartbeat), human-readable RRULE, status, model, target repo, last-run (from `memory.md` mtime). Directly the "Codex stores schedules" hypothesis. High value, trivial parse.
2. **Thread registry table** — title, cwd→project, model, reasoning_effort, tokens_used, git branch/sha, archived/pinned. One SQL query; richer than the rollout scan.
3. **Security posture panel** — `approval_policy`, `sandbox_mode`, and the count of `trust_level="trusted"` project entries. Nothing else on the machine surfaces this, and `danger-full-access` is worth showing a user.
4. **Delegation graph** — `thread_spawn_edges` (60 edges) gives Codex parity with TT's existing Claude delegation view, for free.
5. **Per-turn latency** — `thread_turns.duration_ms` feeds the power/energy model without inferring latency from timestamps.
6. **Goals & budgets** — `thread_goals` token_budget vs tokens_used; statuses `usage_limited`/`budget_limited` map onto TT's budgets feature. (0 rows here — show only when populated.)
7. **Tool inventory per thread** — `thread_dynamic_tools`.
8. Error feed — `logs_2.sqlite WHERE level IN ('ERROR','WARN')` grouped by thread.

### Cross-harness parallels
| Slot | Codex |
|---|---|
| background jobs | `process_manager/chat_processes.json` (live PIDs), `queue_1.sqlite` |
| schedules/cron | **`automations/<id>/automation.toml`** (RRULE) |
| memory | `memories_1.sqlite`, `automations/*/memory.md`, `AGENTS.md`, `memory_mode` col |
| todos | `queued-follow-ups` in global state; `queue_1.sqlite` |
| checkpoints | `sessions/**/rollout-*.jsonl` + `thread_items` projection |
| plan artifacts | none distinct |
| MCP + tools | `config.toml [mcpServers.*]`, `thread_dynamic_tools`, `plugins/cache/**` |
| quota/rate-limit | `thread_goals.status` (`usage_limited`) |
| permissions/config | `approval_policy`, `sandbox_mode`, `[projects.*].trust_level` |
| subagents | **`thread_spawn_edges`** |
| hooks | `notify[]` in config.toml |
| model config | `model`, `model_reasoning_effort`, `service_tier`, `models_cache.json` |
| worktrees | `~/.codex/worktrees/<short-sha>/` |

### Gotchas
- All sqlite are `sqlx`-managed with `-wal`/`-shm`; open **read-only + `immutable=0`**, the Electron app holds them live.
- `sessions/` is date-partitioned `YYYY/MM/DD`, not flat.
- `~/.codex/sqlite/*dev.db` are development duplicates — skip or you double-count.
- `transcription-history.jsonl` + `dictation-history/` contain raw voice transcripts. **Never surface content.**
- `history.jsonl` is raw prompt text. Count only.
- Numeric timestamps are inconsistent: some cols are seconds, some `_ms`. Check per column.

---

## GitHub Copilot CLI — `~/.copilot`, 4.3M, 419 files
Active (log from today). TT currently reads `session-state/` only.

### Directory map
```
~/.copilot/
├── skills/                      2.4M — 9+ skill dirs  [NEW]
├── session-state/<uuid>/        720K — checkpoints/ files/ research/ workspace.yaml [PARTIAL]
├── session-store.db             320K + -wal/-shm      [NEW — high value]
├── logs/process-<epoch>-<pid>.log  20K                [NEW]
├── settings.json  {model, experimental}               [NEW]
├── config.json    (NOT json — parse defensively)      [NEW]
├── command-history-state.json {commandHistory}        [NEW]
├── vscode.session.metadata.cache.json  (session-id → VS Code meta) [NEW]
├── ide/<uuid>.lock              live IDE attach        [NEW]
└── restart/
```

### `session-store.db` schema (the find)
Tables + rows: `sessions` 4, `turns` 13, `checkpoints` 0, `session_files` 0,
`session_refs` 0, `forge_trajectory_events` 0, `assistant_usage_events` **12**,
`forge_skill_proposals` 0, `dynamic_context_items` 0, `search_index*` (FTS5) 13.

```sql
sessions(id, cwd, repository, host_type, branch, summary, created_at, updated_at)
turns(id, session_id, turn_index, user_message, assistant_response, timestamp)
checkpoints(id, session_id, checkpoint_number, title, overview, history,
            work_done, technical_details, important_files, next_steps, created_at)
session_files(id, session_id, file_path, tool_name, turn_index, first_seen_at)
forge_trajectory_events(id, session_id, tool_call_id, turn_index, event_type,
            command, output, exit_code, event_key, event_value, created_at)
assistant_usage_events(
  id, session_id, turn_index, agent_id, parent_tool_call_id, model,
  input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
  reasoning_tokens, total_nano_aiu, request_multiplier, duration_ms,
  time_to_first_token_ms, inter_token_latency_ms, initiator, api_endpoint,
  reasoning_effort, finish_reason, content_filter_triggered,
  token_details_json, created_at)
```

### Dashboard candidates (ranked)
1. **`assistant_usage_events` as ground truth.** Every token class split out, plus
   `total_nano_aiu` and `request_multiplier` — Copilot's *premium request* billing
   units, which TT currently cannot compute. Also `duration_ms`,
   `time_to_first_token_ms`, `inter_token_latency_ms` (real tok/s for the power model),
   and `finish_reason` / `content_filter_triggered`. **This supersedes any
   cache-token heuristic** and is the highest-value single table found in this survey.
2. **Checkpoints panel** — structured `work_done` / `next_steps` / `important_files`
   per checkpoint. A genuine "where did I leave off" view. (0 rows here.)
3. **Files touched** — `session_files(file_path, tool_name)` → per-repo hot files.
4. **Command trajectory** — `forge_trajectory_events(command, exit_code)` → failed-command rate.
5. Delegation — `agent_id` + `parent_tool_call_id` on usage events.
6. Skills inventory (`skills/`) and `forge_skill_proposals` (skills the agent wanted).

### Cross-harness parallels
jobs → none · schedules → none · memory → `dynamic_context_items` ·
todos → `checkpoints.next_steps` · checkpoints → `checkpoints` table ·
plans → `session-state/<uuid>/research/` · MCP/tools → `skills/` ·
quota → `total_nano_aiu`, `request_multiplier` · permissions → `settings.json` ·
subagents → `agent_id`/`parent_tool_call_id` · model → `settings.json.model`

### Gotchas
- `config.json` is **not valid JSON** — wrap the parse.
- `session-store.db` overlaps `session-state/` on disk; prefer the DB, dedupe by session id.
- `total_nano_aiu` is nano-AIU: divide by 1e9 before display.
- FTS5 shadow tables (`search_index_*`) inflate the table list; ignore them.

---

## Cline CLI — `~/.cline`, 8.4M, 21 files
Separate from the VS Code extension store (`saoudrizwan.claude-dev`) TT already reads.

```
~/.cline/
├── data/
│   ├── sessions/<epochms>_<slug>/
│   │   ├── <id>.json           session metadata
│   │   └── <id>.messages.json  transcript
│   ├── settings/providers.json {version, lastUsedProvider, providers} [keys only]
│   ├── cache/feature-flags.json {version, updatedAt, userId, flagsPayload}
│   └── locks/hub/
└── cron/                        EMPTY — but the directory exists (feature stub)
```

Session metadata keys (4 sessions):
```
version, session_id, source, pid, started_at, ended_at, exit_code, status,
interactive, provider, model, cwd, workspace_root, team_name,
enable_tools, enable_spawn, enable_teams, prompt, metadata, messages_path
```
Messages file: `{version, updated_at, agent, sessionId, messages, system_prompt}`.

### Dashboard candidates
1. Session table with **`exit_code` + `status`** — one of the few harnesses recording
   whether a run actually succeeded. Pair with `started_at`/`ended_at` for duration.
2. **Teams/spawn flags** — `enable_teams`, `enable_spawn`, `team_name` expose Cline's
   multi-agent mode; nothing else on disk shows it.
3. Provider/model per session (`provider`, `model`, `lastUsedProvider`).
4. `~/.cline/cron/` — empty now; watch it, Cline is adding scheduling.

### Gotchas
- Two independent Cline stores (CLI here, VS Code extension elsewhere). TT already has
  `TT_CLINE_DIR`/`TT_CLINE_VSCODE_DIR` env overrides — reuse them.
- `prompt` and `system_prompt` fields hold raw text. Never surface.
- No token counts anywhere in the CLI store; cost must still come from the transcript.
