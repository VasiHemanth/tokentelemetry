# Gemini CLI / Antigravity — survey (done by lead after subagent hit session limit)

## Headline correction
`~/.antigravity` (553M) and `~/.antigravity-ide` (543M) are **NOT agent data**. Each
contains only `extensions/` (VS Code–style extension bundles: java, python, go, php,
docker, sqlite-viewer, `google.gemini-cli-vscode-ide-companion`) plus `argv.json` and an
empty `antigravity/bin` stub. 1.1G of the machine's harness footprint is skippable.
All real Antigravity data lives under `~/.gemini/`.

## `~/.gemini` — 13G, 61967 files

```
~/.gemini/
├── antigravity-browser-profile/  5.2G  Chrome profile for the browser tool   [SKIP]
├── antigravity/                  5.2G  the desktop app store                 [PARTIAL]
├── antigravity-ide/              923M  the IDE surface                       [PARTIAL]
├── antigravity-backup/           922M  intentionally excluded by TT already  [SKIP]
├── extensions/                   281M  Gemini CLI extensions                 [PARTIAL]
├── antigravity-cli/              272M  the `agy` CLI surface                 [PARTIAL]
├── tmp/<project-sha256>/          55M  per-project chats + logs              [PARTIAL]
├── everything-claude-code/        40M
├── config/                       4.9M  mcp_config.json + plugins/            [NEW]
├── skills/                       2.4M
├── grok-mcp/                     320K
├── history/<project-name>/       132K  `.project_root` → abs path            [NEW]
├── GEMINI.md, settings.json(.orig), state.json, projects.json
├── trustedFolders.json                                                       [NEW]
├── installation_id
├── google_accounts.json   [keys only — SENSITIVE]
└── oauth_creds.json       [keys only — SENSITIVE]
```

### Antigravity per-surface layout
The three surfaces (`antigravity/` = app, `antigravity-ide/` = IDE, `antigravity-cli/` = `agy`)
share a layout. App surface shown; sizes differ per surface.

```
antigravity/
├── brain/<conversation-uuid>/           4.8G  [PARTIAL — TT reads the .md only]
│   ├── task.md / implementation_plan.md / walkthrough.md   (+ .resolved, .resolved.N)
│   ├── *.metadata.json                  per-artifact metadata          [NEW]
│   ├── ep<NN>_screenshot_<ms>.webp      episodic screenshots           [NEW]
│   ├── ep<NN>_preview_<ms>.webp                                        [NEW]
│   └── .tempmediaStorage/               media_<uuid>_<ms>.png + dom_<ms>.txt [NEW]
├── conversations/<uuid>.pb              266M, 88 files, protobuf       [PARTIAL]
├── playground/<codename>/                71M — scaffolded scratch projects
│                                        (phantom-oort, glowing-gemini, vacant-kuiper…) [NEW]
├── browser_recordings/<conversation-uuid>/  63M, 2 recordings          [NEW]
├── implicit/<uuid>.pb                    41M — implicit context capture [NEW]
├── code_tracker/                        284K                            [NEW]
│   ├── active/<repo>_<sha1>/<filehash>_<Filename.ext>   pre-edit file snapshots
│   └── history/
├── daemon/ls_<hex>.{json,log}           language-server daemon state    [NEW]
├── annotations/<uuid>.pbtxt             300K                            [NEW]
├── mcp/  + mcp_config.json(.bak)                                        [PARTIAL]
├── skills/  prompting/  scratch/  knowledge/  bin/
├── agyhub_summaries_proto.pb            112K                            [NEW]
├── antigravity_state.pbtxt              app state (text-format proto)   [NEW]
├── user_settings.pb                                                     [NEW]
└── installation_id
```
`antigravity-cli/` additionally has: `conversation_summaries.db` (**the find**),
`history.jsonl`, `log/`, `mcp/`, `builtin/`, `plugins/`, `cache/`, `implicit/`,
`scratch/`, `updater/`, `settings.json`, `keybindings.json`, `jetski_state.pbtxt`,
`import_manifest.json`, `presence/`.
`antigravity-ide/` adds `html_artifacts/` and `context_state/` (both empty here).

### `conversation_summaries.db` — 131 rows, one table
```sql
conversation_summaries(
  conversation_id PK, title, preview, step_count, last_modified_time,
  workspace_uris, status, source, project_id, agent_name,
  parent_conversation_id, nesting_depth,
  battle_id, winning_conversation_id,
  not_fully_idle, killed,
  last_user_input_time, last_user_input_step_index, app_data_dir)
```
This is a **derived index over the `.pb` conversations** — everything TT wants without
touching protobuf. `battle_id` + `winning_conversation_id` record Antigravity running
competing agent attempts and picking a winner. `nesting_depth` + `parent_conversation_id`
give a delegation tree. `killed` / `not_fully_idle` give run outcomes.

### Gemini CLI core stores
- `tmp/<sha256-of-project-path>/`
  - `chats/session-<ISO>-<short>.json` → `{sessionId, projectHash, startTime, lastUpdated, messages}` — **50 project dirs**. TT reads `logs.json` (empty list here); the `chats/` sibling is the real transcript store. **PARTIAL → NEW.**
  - `logs.json` → list, empty on this machine.
- `history/<project-slug>/.project_root` → a single line with the absolute repo path.
  33 project slugs. This is the **project-hash → real path resolver** for the `tmp/` dirs.
- `config/mcp_config.json` and `config/plugins/{google-antigravity-sdk,chrome-devtools-plugin}`.
- `trustedFolders.json` — per-folder trust decisions (mirrors Codex `trust_level`).
- `state.json`, `projects.json`, `settings.json`, `GEMINI.md` (global memory).
- `google_accounts.json` / `oauth_creds.json` — **credential files, keys only, never read values.**

`antigravity_state.pbtxt` (text proto, safe to read): `post_onboarding.completed_steps[]`,
`seen_nuxs.uids[]`, `agent_onboarding_completed`, `last_selected_agent_model`
(e.g. `MODEL_PLACEHOLDER_M20`), `migrate_convos_into_projects`, `installation_uuid`.

### Dashboard candidates (ranked)
1. **Conversation index from `conversation_summaries.db`** — title, step_count, status,
   agent_name, workspace, killed, last input time. Replaces protobuf parsing entirely
   and covers all three surfaces (each has its own copy / `app_data_dir` column).
2. **Agent battles** — group by `battle_id`, mark `winning_conversation_id`. Unique to
   Antigravity; no other harness records competitive attempts. Great differentiator.
3. **Delegation tree** — `parent_conversation_id` + `nesting_depth`.
4. **Artifact gallery** — `brain/<uuid>/` walkthrough/plan/task markdown *plus* the
   `ep*_screenshot_*.webp` episodic screenshots. TT already reads the markdown; the
   screenshots turn it into a visual session replay.
5. **Code tracker diffs** — `code_tracker/active/<repo>_<sha>/` holds pre-edit file
   snapshots keyed by repo + commit → "what did the agent change here".
6. **Browser recordings** — count/size per conversation; link out.
7. **Playground projects** — codename, size, mtime.
8. **Disk-cost panel** — this cluster is ~12G. `antigravity-browser-profile` (5.2G) and
   `antigravity-backup` (922M) are pure reclaimable space. A "reclaim disk" view is a
   real user benefit no other TT surface offers.

### Cross-harness parallels
| Slot | Antigravity / Gemini CLI |
|---|---|
| background jobs | `daemon/ls_*.json`, `presence/` |
| schedules/cron | none found |
| memory | `GEMINI.md`, `implicit/*.pb`, `knowledge/` |
| todos | `task.md` in brain |
| checkpoints | `code_tracker/active/**`, `.resolved.N` artifact versions |
| plan artifacts | `implementation_plan.md`, `walkthrough.md`, `task.md` |
| MCP + tools | `config/mcp_config.json`, `<surface>/mcp/`, `extensions/`, `plugins/` |
| quota | none on disk |
| permissions | `trustedFolders.json` |
| subagents | `parent_conversation_id`, `nesting_depth`, `battle_id` |
| hooks | none |
| model config | `last_selected_agent_model` in `antigravity_state.pbtxt`, `settings.json` |
| browser state | `browser_recordings/`, `antigravity-browser-profile/` |

### Gotchas
- **Three surfaces + a backup** all with identical layout. Dedupe by `installation_id`
  and label by surface, or sessions triple-count. `antigravity-backup/` must stay excluded.
- `conversations/*.pb` and `implicit/*.pb` are **binary protobuf without a public schema**.
  Prefer `conversation_summaries.db`. `*.pbtxt` files are text-format and safe to parse.
- `tmp/` dir names are a **hash of the project path**; resolve via `history/<slug>/.project_root`.
- `settings.json.orig` exists alongside `settings.json` — read the live one.
- `oauth_creds.json`, `google_accounts.json` are live credentials. Existence only.
- `.tempmediaStorage/dom_*.txt` contains full page DOM of sites visited. Never surface.
- Gemini CLI is discontinued (2026-06-18) in favour of Antigravity — weight the CLI
  surface as legacy, Antigravity as live.

---

# OpenCode / Hermes / Omnigent — survey

## OpenCode
**Correction:** `~/.opencode` (160M) is an *install* dir only — `bin/opencode` (104M) and
`node_modules/` (57M) + `package.json`. **No user data.** Same for `~/.config/opencode`
(node_modules only). All data is in `~/.local/share/opencode/`:

```
~/.local/share/opencode/
├── snapshot/<sha1>/<sha1>          39M — git-like object store (checkpoints)  [NEW]
├── opencode.db (+wal/shm)          26M                                        [PARTIAL]
├── storage/session_diff/<ses_id>.json  5.0M — per-session diffs               [NEW]
├── log/<ISO>.log                  620K                                        [NEW]
├── tool-output/tool_<id>           240K — 3 spilled large tool outputs         [NEW]
├── auth.json                       [keys only — SENSITIVE]
└── repos/                          (empty)
```

`opencode.db` tables + rows: `project` 6, `session` 51, `message` 865, `part` 3987,
`todo` **26**, `session_message` 80, `permission` 0, `session_share` 0, `workspace` 0,
`event`/`event_sequence` 0, `account`/`account_state`/`control_account` 0.

```sql
project(id, worktree, vcs, name, icon_url, icon_color, time_created, time_updated,
        time_initialized, sandboxes, commands, icon_url_override)
message(id, session_id, time_created, time_updated, data)          -- data = JSON blob
part(id, message_id, session_id, time_created, time_updated, data)
permission(project_id, time_created, time_updated, data)
```
TT already queries `session`/`message`/`part`/`todo`. **NEW:** `project.sandboxes`,
`project.commands`, `project.vcs`, and the whole `storage/`+`snapshot/`+`tool-output/` tree.

Dashboard candidates: (1) **todo board** — 26 live todos, OpenCode is the only harness
besides Hermes with a first-class todo table; (2) **session diffs** — `storage/session_diff/`
gives changed-files-per-session without git; (3) **snapshot store size** — 39M of
checkpoint objects, a reclaim candidate; (4) project sandbox config.

Gotchas: data dir moves with `XDG_DATA_HOME`. `message.data`/`part.data` are JSON blobs,
not columns — parse, don't index. `snapshot/` is content-addressed with no manifest.

## Hermes — `~/.hermes`, 3.8G, 156432 files
```
hermes-agent/   3.4G  |  hermes-office/ 859M  |  node/ 189M  |  bin/ 49M   [runtime, SKIP]
profiles/        97M  [COVERED]        logs/          32M  [NEW]
skills/          24M  [COVERED]        state.db       17M  [PARTIAL]
state-snapshots/ 16M  [NEW]            sessions/      14M
models_dev_cache.json 4.1M [NEW]       pets/         3.4M
kanban.db       112K  [PARTIAL]        projects.db    44K  [NEW]
pastes/         104K  [NEW]            cache/ plugins/ hooks/ cron/ desktop-plugins/
config.yaml (+5 dated .bak)            gateway_state.json, gateway-starts.log
context_length_cache.yaml [NEW]        channel_directory.json, desktop.json
auth.json/.bak/.lock [SENSITIVE]       google_client_secret.json, google_token.json [SENSITIVE]
gateway.pid/.lock, install_id, interrupt_debug.log, image_cache/, audio_cache/, assets/
```

**Verified:** `backend/main.py` only ever selects from `sessions` and `messages` in
`state.db` (plus `cron_specs`/`cron_runs`, `tasks`/`task_runs`, `steps`, `gen_metadata`).
Every other `state.db` table is unmined:

`session_model_usage` (**23 rows**) — the single most valuable unmined table in Hermes:
```sql
session_model_usage(
  session_id → sessions(id), model, billing_provider, billing_base_url, billing_mode,
  task, api_call_count, input_tokens, output_tokens, cache_read_tokens,
  cache_write_tokens, reasoning_tokens,
  estimated_cost_usd, actual_cost_usd, cost_status, cost_source,
  first_seen, last_seen)
```
It carries **both estimated and actual USD**, plus `cost_source`/`cost_status` — an
independent oracle to validate TT's own cost math against (satisfies the project's
"independent recompute" rule for free).

`async_delegations` (0 rows) — `delegation_id, origin_session, origin_ui_session_id,
parent_session_id, state, dispatched_at, completed_at, updated_at, event_json,
result_json, delivery_state, delivery_attempts, delivered_at, owner_pid,
owner_started_at, task_json, delivery_claim, delivery_claimed_at, origin_session_id`.
A full async subagent-dispatch ledger with delivery guarantees.

`gateway_routing` (0) — `scope, session_key, entry_json, updated_at`.
`system_prompts` (**24**), `delivery_obligations`, `gateway_hygiene_state`,
`session_turn_leases`, `compression_locks`, `messages_fts` + `messages_fts_trigram` (FTS5).

`projects.db` (**NEW**, unread): `projects(id, …, created_at, archived)`,
`project_folders(project_id, path, label, is_primary, added_at)`, `project_meta(key, value)`.
This is Hermes's own project registry — TT currently infers projects from cwd.

`models_dev_cache.json` — 4.1M models.dev catalogue keyed by provider
(`hpc-ai`, `ai-router`, `mixlayer`, `qiniu-ai`, `neuralwatt`, `cloudflare-workers-ai`, …).
A large **local** pricing/context-window source, already on disk, no network needed.

`context_length_cache.yaml` — per-model context windows.
`state-snapshots/<YYYYMMDD-HHMMSS>-pre-update/` — pre-upgrade state backups (1 here, 16M).
`logs/` — `agent.log` + rotated `.1`/`.2`, `errors.log(.1/.2)`, `desktop.log`, `curator/`.

Dashboard candidates: (1) **cost reconciliation** — Hermes `actual_cost_usd` vs TT's
computed cost, per session/model; (2) **project registry** from `projects.db` with real
folder mappings; (3) **model catalogue + context limits** from `models_dev_cache.json` +
`context_length_cache.yaml`; (4) async delegation ledger; (5) error-rate feed from
rotated logs; (6) 3.4G `hermes-agent/` runtime as a disk-reclaim line.

Gotchas: `HERMES_HOME` relocates everything (TT already honours it). `hermes-agent/`,
`hermes-office/`, `node/`, `bin/` are ~4.5G of *runtime*, not data — never walk them.
FTS5 shadow tables inflate the table list. `google_token.json`, `auth.json` are live creds.

## Omnigent — `~/.omnigent`, 612M, 50 files
```
logs/             597M  ← 97% of the dir                              [NEW]
chat.db (+wal/shm) 10M                                                [PARTIAL]
artifacts/ag_<32hex>/<64hex>   156K  + artifacts/.cache/ag_<id>/       [NEW]
daemons/  config.yaml  local_server.{pid,sig,logpath}                  [NEW]
```
`chat.db` tables + rows: `conversations` 7, `conversation_items` 777,
`conversation_labels` 39, `agents` **11**, `users` 1, `session_permissions` 4,
`hosts` 1, `user_daily_cost` **1**, `files` 0, `policies` 0, `account_tokens` 0,
`comments` 0, + `conversation_items_fts*` (FTS5).

```sql
agents(id, created_at, name, bundle_location, version, description, updated_at,
       session_id → conversations(id))     -- 11 agent bundles; template rows have NULL session_id
conversation_labels(conversation_id, key, value, updated_at)
files(id, created_at, filename, bytes, content_type, session_id)
users(id, is_admin, password_hash, created_at, last_login_at)   [password_hash: never read]
session_permissions(user_id, conversation_id, …)
```
**`user_daily_cost`** and **`policies`** are the notable unmined tables — a per-user daily
cost rollup and a policy store, matching `backend/omnigent_policy.py` already on your branch.

Dashboard candidates: (1) **agent bundle registry** — 11 named agents with versions and
descriptions; (2) `user_daily_cost` as a cost cross-check; (3) `conversation_labels`
as free session tagging; (4) **597M of logs** as a reclaim line + error feed;
(5) artifacts store (`ag_<id>/<sha256>` content-addressed).

Gotchas: `logs/` is 597M — never walk it, stat only. `users.password_hash` and
`account_tokens` must never be read. Multi-user schema (`users`, `session_permissions`,
`hosts`) means Omnigent can be shared — filter to the local user.
