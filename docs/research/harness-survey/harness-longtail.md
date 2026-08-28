# Harness long-tail survey — delta vs BRIEF.md

Scope: dirs assigned in the task, plus a `ls -d ~/.[a-z]*` sweep for anything
agent-shaped that wasn't listed. Everything below is NEW relative to BRIEF.md
unless marked COVERED. Auth/credential files are reported as key structure
only — values are never shown (`<redacted>`).

---

## pi (xAI coding CLI) — `~/.pi/agent`, 238M, 19290 files
**What agent is this?** `settings.json` has `"defaultProvider": "xai-auth", "defaultModel": "grok-4.3"`; `npm/package.json` depends on `pi-mcp-adapter` / `pi-xai-oauth`; `auth.json` has an `xai-auth` OAuth block plus a `cerebras` API-key block. This is xAI's "pi" coding agent CLI (separate product from the `~/.grok` Grok CLI already covered).
**Still active?** Yes — latest session `2026-07-14T01:34:45Z` (education_video project). 28 session files across 8 projects, spanning 2026-04-26 to 2026-07-14.

### Directory map
```
~/.pi/agent/
├── npm/                    # bundled node runtime + node_modules (mcp adapter, oauth) — SKIP, runtime
├── bin/                    # bundled `fd`, `rg` binaries — SKIP, runtime
├── skills/                 # 8 skills: durable-objects, wrangler, agents-sdk, cloudflare,
│                           #   cloudflare-email-service, workers-best-practices, sandbox-sdk,
│                           #   web-perf, turnstile-spin — identical set to ~/.claude skills (synced)
├── sessions/               # per-cwd session transcripts (see below)
│   └── --Users-<slugged-cwd>--/<ISO-ts>_<uuidv7>.jsonl
├── mcp-cache.json          # {version, servers} — cached MCP server metadata
├── mcp-npx-cache.json
├── mcp.json                # {"mcpServers": {name: {command,args}}} — user MCP config
├── trust.json              # {<absolute-project-path>: true} — per-dir trust grants
├── settings.json           # {lastChangelogVersion, defaultProvider, defaultModel, theme, packages, defaultThinkingLevel}
└── auth.json               # per-provider credential blobs — REDACTED
```

### Store inventory
| Path | Format | What it holds | Cadence | Retention/cleanup | Coverage |
|---|---|---|---|---|---|
| `sessions/<slug>/<ts>_<uuid>.jsonl` | JSONL | Full conversation transcript, one session per file | Per session | No visible pruning | NEW |
| `settings.json` | JSON | Provider/model defaults, thinking level, installed packages | On change | n/a | NEW |
| `trust.json` | JSON | dir → trusted bool | Per project first-run | Grows unbounded | NEW |
| `mcp.json` | JSON | User's configured MCP servers (command+args) | On edit | n/a | NEW |
| `mcp-cache.json` / `mcp-npx-cache.json` | JSON | `{version, servers}` cached tool/schema metadata per MCP server | Refreshed on MCP connect | n/a | NEW |
| `auth.json` | JSON | OAuth (xai-auth: refresh/access/expires/tokenEndpoint/tokenType) + API key (cerebras: type/key) | On login | n/a | NEW (structure only) |
| `skills/*/SKILL.md` | Markdown | Same Cloudflare skill pack seen under `~/.claude/skills` | Static/synced | n/a | NEW (cross-harness skill sync signal) |

### Schemas
**Session JSONL** — one record per line, `type` discriminates:
```
session:               {type, version, id, timestamp, cwd}
model_change:           {type, id, parentId, timestamp, provider, modelId}
thinking_level_change:  {type, id, parentId, timestamp, thinkingLevel}
message:                {type, id, parentId, timestamp, message: {role, content: [...], timestamp}}
  content[].text:        {type:"text", text, textSignature}
  content[].thinking:     {type:"thinking", thinking, thinkingSignature}
  content[].toolCall:     {type:"toolCall", id, name, arguments}   # tool names seen: LS, bash, edit, mcp, read, write
```
No `tool_result`/usage/token-count events were observed in sampled sessions — cost/token accounting is not locally derivable from these files alone (unlike Claude Code's transcript which embeds usage).

**auth.json** (keys only):
```json
{"cerebras": {"type":"<redacted>","key":"<redacted>"},
 "xai-auth": {"type":"<redacted>","refresh":"<redacted>","access":"<redacted>","expires":"<redacted>","tokenEndpoint":"<redacted>","tokenType":"<redacted>"}}
```

### Dashboard candidates
1. **Session list + tool-call histogram** (high value, easy) — parse `type:"message"` → count `toolCall.name` per session; same shape as other harnesses' tool-mix panels.
2. **Provider/model timeline** (high value, easy) — `model_change` events show provider (xai-auth/cerebras) + model switches within a session.
3. **MCP server inventory** (medium value, easy) — `mcp.json` + `mcp-cache.json` give configured servers and their cached tool schemas, same shape as Claude Code's `.mcp.json`.
4. **Trusted-project list** (low value, trivial) — `trust.json` keys.

### Cross-harness parallels
- MCP + tools inventory: `mcp.json` / `mcp-cache.json` (like Claude's `.mcp.json`)
- Permissions/config: `trust.json` (per-dir trust, like Claude Code's project trust)
- Model config: `settings.json` (`defaultProvider`, `defaultModel`, `defaultThinkingLevel`)
- No jobs/schedules, no memory file, no todos/plan artifacts, no checkpoint/rewind system observed.

### Gotchas
- Session directory names are the cwd with `/` → `-` and wrapped in leading/trailing `--` (e.g. `--Users-dev-Documents-Developer-tokentelemetry--`) — same encoding scheme as `~/.grok/sessions`, but note the wrapping dashes differ slightly (Grok doesn't double-wrap) — a shared regex won't work as-is.
- No token/cost data in transcripts; if TokenTelemetry wants cost for `pi`, it needs its own pricing table matched against `model_change.modelId` and turn counts, not extracted usage numbers.
- `npm/` (228M) is a bundled Node runtime + `pi-mcp-adapter`/`pi-xai-oauth` — pure bundled deps, skip entirely.

---

## Prime Agent — `~/.prime/agent`, 268M, 13982 files
**What agent is this?** `~/.prime/agent/logs/agent.jsonl` literally logs `"component":"coding-agent.daemon-supervisor"` and `"msg":"Prime Agent daemon supervisor ... listening on .../prime-agent-501/daemon.sock"`. `settings.json`: `defaultProvider: "openai-codex", defaultModel: "gpt-5.4"`. `auth.json` has an `openai-codex` OAuth block. This is "Prime Agent" — a coding CLI with a **persistent, daemon-hosted Python kernel per session** (unique among everything surveyed).
**Still active?** Yes — latest session `2026-08-08 11:50 IST`. Only 2 session files total (lightly used compared to `pi`).

### Directory map
```
~/.prime/agent/
├── kernel-venv/                    # bundled Python venv for the persistent kernel — SKIP, runtime (265M)
├── bin/                            # bundled `fd` — SKIP, runtime
├── sessions/                       # <uuidv7>.jsonl per session (top-level, not per-cwd like pi)
├── session-artifacts/<session-id>/
│   ├── kernel-state.json           # {version, savedNames, skipped, bytes, pythonVersion, timestamp}
│   ├── kernel-state.dill           # pickled (dill) Python objects — the actual persisted variables
│   └── harness/harness_state.json  # {schema, entries, refinements}
├── session-leases/                 # empty (0 files) — presumably lock files while a session is live
├── daemon-workers/<worker-id>/
│   ├── command-journal.jsonl       # empty in this snapshot
│   ├── snapshot-cache/             # empty in this snapshot
│   └── supervisor-config/          # empty in this snapshot
├── logs/
│   ├── agent.jsonl                 # structured daemon/supervisor log
│   ├── daemon.sock.<hash>.log
│   └── worker-<host>-<id>.sock.<hash>.log
├── settings.json                   # {onboardingShown, defaultProvider, defaultModel, recentModels, defaultThinkingLevel}
└── auth.json                       # openai-codex OAuth block — REDACTED
```

### Store inventory
| Path | Format | What it holds | Cadence | Retention/cleanup | Coverage |
|---|---|---|---|---|---|
| `sessions/<uuid>.jsonl` | JSONL | Conversation transcript incl. `agent_status`/`custom` events | Per session | none seen | NEW |
| `session-artifacts/<id>/kernel-state.json` | JSON | Metadata about the pickled Python kernel state (which variable names were persisted, size, python version) | Per checkpoint (kernel save) | overwritten each save | NEW |
| `session-artifacts/<id>/kernel-state.dill` | Python dill pickle (binary) | The actual persisted Python objects/variables from the agent's code-execution sandbox | Per checkpoint | overwritten | NEW (binary, not parseable as JSON — flag existence only) |
| `session-artifacts/<id>/harness/harness_state.json` | JSON | `{schema, entries, refinements}` — looks like an edit/refinement journal | Per turn(?) | n/a | NEW |
| `daemon-workers/<id>/command-journal.jsonl` | JSONL | (empty in this snapshot) shell/tool command journal per daemon worker | streaming | n/a | NEW |
| `logs/agent.jsonl` | JSONL | Structured supervisor/worker lifecycle log (pid, socket paths, session-worker start/stop) | Continuous | not rotated in this snapshot | NEW |

### Schemas
**Session JSONL** event types seen: `session, thinking_level_change, service_tier_change, session_state, model_change, message, agent_status, custom`.
```
session:            {type, version, id, timestamp, cwd, rlmDepth}
service_tier_change: {type, id, parentId, timestamp, serviceTier}
session_state:        {type, id, parentId, timestamp, state:{status}}
agent_status:          {type, id, parentId, timestamp, status:{summary, taskState, basedOnMessageCount}}
custom:                {type, id, parentId, timestamp, customType, data}
  # customType "prime-agent.refinement": data keys = [id, summary, rationale, expectedOutcome, appliedEdits, harnessStatePath, scope]
```
`taskState` values observed: `needs_input` (others presumably `running`/`done`/etc., not sampled). `rlmDepth` on the session record suggests recursive/nested agent invocation depth is tracked per-session.

**kernel-state.json**:
```json
{"version": "...", "savedNames": ["<list>"], "skipped": "...", "bytes": "...", "pythonVersion": "...", "timestamp": "..."}
```
**harness_state.json**: `{"schema": "...", "entries": [...], "refinements": [...]}`

**auth.json** (keys only): `{"openai-codex": {"type":"<redacted>","access":"<redacted>","refresh":"<redacted>","expires":"<redacted>","accountId":"<redacted>"}}`

### Dashboard candidates
1. **"Live Python kernel" badge + variable inventory** (very high value, unique-to-Prime, medium ease) — `kernel-state.json`'s `savedNames` list shows what variables persist across turns in the sandbox; this is a genuinely distinctive feature no other harness has (closest analog: Jupyter notebook state). Surfacing "N variables carried across M turns" would be a strong differentiator panel.
2. **Task-state timeline** (high value, easy) — `agent_status.status.taskState` (`needs_input`/etc.) + `basedOnMessageCount` gives a lightweight progress/blocked indicator per session.
3. **Refinement journal** (medium value, easy) — `custom` events with `customType:"prime-agent.refinement"` carry `summary`/`rationale`/`expectedOutcome`/`appliedEdits` — essentially a structured "why I made this edit" log, similar in spirit to a plan artifact.
4. **Daemon/worker health** (low value, easy) — `logs/agent.jsonl` gives daemon uptime, worker start/stop, socket paths — useful for a "is Prime's background daemon running" status chip.

### Cross-harness parallels
- Checkpoints/rewind: `kernel-state.dill` + `kernel-state.json` — closest thing in this whole survey to a literal execution-state checkpoint (pickled interpreter state, not just file diffs).
- Plan artifacts: `harness_state.json` refinements array.
- Background jobs / daemon: `daemon-workers/<id>/` (supervisor-config, snapshot-cache, command-journal) — Prime runs a persistent daemon with worker processes per session, closer to Hermes's cron/kanban daemon model than pi's stateless-CLI model.
- Model config: `settings.json` (`defaultProvider: openai-codex`, `defaultModel: gpt-5.4`).
- No memory file (SOUL.md/MEMORY.md equivalent) observed.

### Gotchas
- `kernel-state.dill` is a Python `dill` pickle, not JSON — never `eval`/unpickle untrusted data; for a scanner, only read `kernel-state.json` sidecar for metadata.
- `daemon-workers/`, `session-leases/`, and the worker's `command-journal.jsonl`/`snapshot-cache`/`supervisor-config` were all empty in this snapshot — they're clearly populated only while a daemon is actively running; a scanner needs to handle the empty/transient case gracefully.
- `kernel-venv` (265M) is a full bundled Python virtualenv — skip entirely, matches the exclusion rule for runtimes.

---

## Kimi CLI — `~/.kimi`, 28K, 7 files
**What agent is this?** `logs/kimi.log` literally logs `kimi_cli.cli:_run` and `kimi_cli.app:create`. Moonshot AI's Kimi coding CLI.
**Still active?** Barely — only log entries from `2026-02-06`, `user-history` shows just `/login` then `exit`. This install looks abandoned/trial-only.

### Directory map
```
~/.kimi/
├── device_id                       # opaque device id string
├── latest_version.txt              # "1.8.0"
├── kimi.json                       # {"work_dirs": [{path, kaos, last_session_id}]}
├── config.toml                     # [models] [providers] [loop_control] [services] [mcp.client] — all empty/default
├── sessions/<session-id>/          # EMPTY directory (0 files) despite dir existing
├── logs/kimi.log                   # plain-text loguru-style log
├── user-history/<session-id>.jsonl # {"content": "<slash-command-or-message>"} per line
└── credentials/kimi-code.json      # OAuth token blob — REDACTED
```

### Store inventory
| Path | Format | What it holds | Cadence | Coverage |
|---|---|---|---|---|
| `kimi.json` | JSON | Registered work directories (`kaos: "local"` tag, last session id) | On project open | NEW |
| `config.toml` | TOML | `default_model`, `default_thinking`, `loop_control` (max_steps_per_turn=100, max_retries_per_step=3, max_ralph_iterations=0, reserved_context_size=50000), `mcp.client.tool_call_timeout_ms` | On edit | NEW |
| `user-history/<id>.jsonl` | JSONL | `{"content": str}` — raw user input log (slash commands + messages) | Per input | NEW |
| `logs/kimi.log` | loguru text | CLI lifecycle log (session creation, config load) | Continuous | NEW |
| `credentials/kimi-code.json` | JSON | `access_token, refresh_token, expires_at, scope, token_type` | On login | NEW (structure only) |

### Schemas
`user-history/*.jsonl`: `{"content": "<user-typed string>"}`
`kimi.json`: `{"work_dirs": [{"path": str, "kaos": str, "last_session_id": str|null}]}`

### Dashboard candidates
Given this install is essentially unused (login + exit only, empty sessions dir), the realistic dashboard value today is low. If a user actively adopts Kimi CLI:
1. **loop_control config display** (low effort) — `max_steps_per_turn`/`reserved_context_size` are useful "agent behavior" config to surface alongside other harnesses' permission/config panels.
2. **Work-dir registry** (trivial) — `kimi.json.work_dirs` for a project list, same idea as other harnesses' project indices.
Session transcripts themselves (the actual conversation data) were not observed — the `sessions/<id>` directory exists but is empty, so the real per-turn transcript format is unconfirmed from this machine.

### Cross-harness parallels
- Config/permissions: `config.toml` `[loop_control]` (step/retry caps, context reservation) — Kimi's equivalent of other harnesses' agent-behavior limits.
- MCP: `[mcp.client] tool_call_timeout_ms` only — no server list configured yet.

### Gotchas
- `sessions/<hash>/` exists but is empty — don't assume a non-empty sessions dir means there's data; check file count.
- This is a different product from `~/.kimi-work` (kimi-slides PPT tool) and `~/.kimi-webbridge` (a webbridge helper binary) — three unrelated dirs share the `kimi` name prefix.

---

## kimi-slides (PPT tool) — `~/.kimi-work`, 137M, 30 files
**What agent is this?** `bin/kimi-tools/install-state`: `release_version=2.2.8-4b26a3be`, `asset_base_url=https://statics.moonshot.cn/kimi-ppt-cli-native/...`. This is **not a coding agent** — it's Moonshot's bundled `kimi-slides` PPT-generation CLI tool (native binary) that Kimi CLI (or another agent) shells out to, plus a 26-font asset cache for slide rendering.
**Still active?** Install marker present, no usage logs to date-check.

### Directory map
```
~/.kimi-work/bin/
├── kimi-slides -> kimi-tools/kimi-slides    # symlink to native binary
└── kimi-tools/
    ├── kimi-slides            # the actual native binary (bulk of the 137M)
    ├── install-state          # key=value: schema_version, release_version, platform, binary_sha256, fonts_version, fonts_installed, asset_base_url
    └── fonts/                 # 26 .ttf files (CJK + display fonts) + fonts.json manifest
```

### Store inventory
Purely a bundled tool install — no session/usage/telemetry data. **Coverage: N/A (not agent data)**.

### Dashboard candidates
None directly — this is infrastructure a coding agent invokes, not a source of sessions/cost/tokens. At most, a scanner could note "kimi-slides tool installed, vX.Y.Z" as a capability flag if TokenTelemetry ever inventories companion tools per harness.

### Gotchas
- Don't mistake this for Kimi CLI's own data dir (`~/.kimi`) — same vendor, different product, different directory.

---

## kimi-webbridge — `~/.kimi-webbridge`, 9.1M
**What is this?** Bundled binary (`bin/kimi-webbridge`, version file `3.1.6|9556880|<epoch-ms>`) + `identity.json` (`{"device_id": "<redacted>"}`). A native helper binary, likely bridging Kimi's web/browser surface to the local machine. No session or usage data.
**Coverage:** N/A (not agent data) — flag existence only.

---

## reins (browser-automation driver for coding agents) — `~/.reins`, 660K, 26 files
**What is this?** `extension/manifest.json`: `"name": "reins", "description": "Drive your real, logged-in browser from your coding agent (via the reins CLI)."` This is **infrastructure used BY coding agents** (like `browseros` and the `claude-in-chrome` MCP), not a standalone LLM harness — it has no model, no tokens, no cost. It's a local WebSocket daemon (port file → `8765`) + Chrome MV3 extension + screenshot capture.
**Still active?** Yes — daemon logs through `2026-08-08`.

### Directory map
```
~/.reins/
├── port                              # plain text: "8765" (daemon's local WS port)
├── logs/daemon-YYYY-MM-DD.log        # one log file per day, plain text
├── shots/shot-<ISO-ts>.png           # screenshots taken during automation runs
└── extension/                        # Chrome MV3 extension (manifest.json, service worker, popup/offscreen/settings/status bundles, icons)
```

### Store inventory
| Path | Format | What it holds | Cadence | Coverage |
|---|---|---|---|---|
| `logs/daemon-*.log` | plain text | Connection lifecycle: `connection from origin=chrome-extension://<id>`, `browser connected (bN: Google Chrome)`, `connection closed`, `shutting down (SIGTERM)` | Daily rotation | NEW |
| `shots/*.png` | PNG | Screenshots captured during a driven-browser session | Per capture | NEW |
| `port` | text | Active daemon port | On daemon start | NEW |

### Dashboard candidates
Low standalone value (no cost/tokens/sessions of its own). Possible: a small "browser automation active" indicator (daemon up/down from log tail + last-shot timestamp) surfaced wherever a coding agent's tool-use panel shows browser-driving activity — but this needs correlating with the *calling* agent's transcript to be meaningful, which `reins` itself doesn't record.

### Cross-harness parallels
This is reins's version of `claude-in-chrome`/`browseros`: a real-browser automation bridge. Not comparable to jobs/memory/todos categories — it's a tool, not an agent.

### Gotchas
- No user/session identity, no conversation content, no tokens — don't try to derive cost from this dir.

---

## Vercel Skills registry (`.agents`/`.agent`) — `~/.agents` (328K, 45 files), `~/.agent` (328K via symlink, effectively 0 unique)
**What is this?** `.agents/.skill-lock.json`: `"skills": {"remotion-best-practices": {"source": "remotion-dev/skills", "sourceType": "github", ...}, "find-skills": {"source": "vercel-labs/skills", ...}}` and `"lastSelectedAgents": ["amp","antigravity","cline","codex","cursor","deepagents","firebender","gemini-cli","github-copilot","kimi-cli","opencode","warp","claude-code","qwen-code","mistral-vibe"]`. This is **Vercel Labs' cross-agent "skills" package manager** — it installs the same SKILL.md packages into every supported agent's skills directory. `~/.agent/skills/app-store-screenshots` is literally a symlink to `~/.agents/skills/app-store-screenshots` (legacy path alias).
**Still active?** `.skill-lock.json` last updated `2026-03-02`.

### Directory map
```
~/.agents/
├── .skill-lock.json           # {version, skills:{name:{source,sourceType,sourceUrl,skillPath,skillFolderHash,installedAt,updatedAt}}, dismissed, lastSelectedAgents}
└── skills/
    ├── tt-hot-topics-post/    # TokenTelemetry's own social-posting skill (self-reference, not another agent's data)
    ├── remotion-best-practices/SKILL.md + rules/
    ├── app-store-screenshots/{SKILL.md, mockup.png}
    ├── find-skills/SKILL.md
    ├── tt-threads-post/
    └── tt-social-post/

~/.agent/
└── skills/app-store-screenshots -> ../../.agents/skills/app-store-screenshots   # symlink only
```

### Store inventory
| Path | Format | What it holds | Coverage |
|---|---|---|---|
| `.skill-lock.json` | JSON | Installed cross-agent skills + their GitHub source + the 15-agent list this installer knows about | NEW |

### Dashboard candidates
1. **"Skills shared across agents" panel** (medium value, easy) — `lastSelectedAgents` is a ready-made list of every agent this tool can push skills to; cross-reference against which of those 15 agents TokenTelemetry actually finds installed locally, to show "skills synced to N/15 agents you have."
2. Otherwise low value — this is package-manager metadata, not usage/session data.

### Cross-harness parallels
Skills/plugin inventory — but it's a *meta*-registry above individual harnesses, not a harness itself. Worth linking from each covered agent's "skills" tab if that agent's name appears in `lastSelectedAgents` and the skill hash matches what's installed under that agent's own skills dir (e.g. the identical Cloudflare skill set was found duplicated under `~/.pi/agent/skills` and `~/.openclaw/skills` — likely synced by this same tool or a shared convention).

### Gotchas
- `~/.agent` (singular) is legacy/alias — don't double-count it as a separate registry; it's a symlink forest into `~/.agents`.

---

## agent-harness (unidentified, minimal) — `~/.agent-harness`, 8K, 2 files
**What is this?** Could not positively identify. `VERSION` = `"1"`. `aliases.json` = `{}` (empty object). No process name, README, or log tying it to a specific product; grepped the TokenTelemetry repo for "agent-harness" and only found unrelated generic prose (not a self-reference). Owned by the same user, dir created 2026-04-24.
**Still active?** Empty state file — can't tell from content alone; mtime is its creation date, no further writes observed.

### Directory map
```
~/.agent-harness/
├── VERSION       # "1"
└── aliases.json  # "{}"
```

### Store inventory
Nothing populated yet — `aliases.json` is presumably meant to map agent short-names → CLI invocation targets (a generic "harness alias" file), but it's empty on this machine. **Coverage: NEW but empty — flag for re-check after the owning tool is actually used.**

### Dashboard candidates
None until populated.

### Gotchas
- Don't confuse with `~/.agents` (Vercel skills registry, above) — similar name, unrelated tool, no evidence of a relationship.

---

## .agent — see "Vercel Skills registry" above (confirmed symlink alias, not empty as the brief's byte count suggested — it contains one symlinked skills subdir).

---

## headroom (context-compression tool) — `~/.headroom`, 4K, 1 file
**What is this?** `session_stats.jsonl` contains compression telemetry: `{"type":"compress","input_tokens":2086,"output_tokens":180,"savings_percent":91.4,"strategy":"router:log:0.07","timestamp":<epoch>,"pid":<int>}`. This is a **context-compression middleware** (likely sits between an agent and the model, compressing prompts/context before sending) — not an agent itself.
**Still active?** Single entry, `2026-06-13`.

### Directory map
```
~/.headroom/
└── session_stats.jsonl   # one JSON object per compression event
```

### Store inventory
| Path | Format | What it holds | Coverage |
|---|---|---|---|
| `session_stats.jsonl` | JSONL | Per-compression-event: input/output token counts, savings %, strategy identifier, pid | NEW |

### Schemas
```json
{"type":"compress","input_tokens":int,"output_tokens":int,"savings_percent":float,"strategy":"router:log:<float>","timestamp":float,"pid":int}
```

### Dashboard candidates
1. **Token-savings panel** (medium value, trivial extraction) — directly reports tokens saved via compression; if this tool sits in front of one of TokenTelemetry's tracked harnesses, "headroom saved you N tokens (X%) this session" is a ready-made stat with zero inference needed.

### Cross-harness parallels
None — this is a cost-optimization proxy, categorically different from a coding-agent harness. Worth a small standalone "optimization tools" section rather than shoehorning into the per-agent panel taxonomy.

### Gotchas
- Only one event recorded on this machine — schema is confirmed but real-world volume/rotation behavior is unverified.

---

## BrowserOS (AI browser agent) — `~/.browseros`
**What agent is this?** `SOUL.md` (`# SOUL.md — Who You Are ... _You're not a chatbot. You're becoming someone._`) matches the Hermes-style persona-file pattern already covered for Hermes. `db/browseros.sqlite` schema (`agent_definitions`, `oauth_tokens`, `produced_files`, drizzle migrations) confirms a Chromium-based AI browser agent product named BrowserOS with pluggable model adapters.
**Still active?** DB last touched `2026-06-25`; `memory/`, `sessions/`, `tool-output/` are all present but **empty (0B)** — installed, not actively used.

### Directory map
```
~/.browseros/
├── SOUL.md                 # persona/identity file (Hermes-pattern)
├── memory/                 # EMPTY (0 files)
├── sessions/                # EMPTY (0 files)
├── tool-output/             # EMPTY (0 files)
├── skills/builtin/          # 11 built-in skills, each a dir with SKILL.md:
│                            #   read-later, compare-prices, deep-research, fill-form, extract-data,
│                            #   summarize-page, monitor-page, screenshot-walkthrough, manage-bookmarks,
│                            #   organize-tabs, find-alternatives, save-page
└── db/
    ├── browseros.sqlite      # see schema below — all data tables empty (0 rows), only migrations table populated (4 rows)
    ├── browseros.sqlite-shm
    └── browseros.sqlite-wal
```

### Store inventory
| Path | Format | What it holds | Coverage |
|---|---|---|---|
| `db/browseros.sqlite: agent_definitions` | SQLite table | Per-agent config: `id, name, adapter, model_id, reasoning_effort, permission_mode, session_key, pinned, adapter_config_json, created_at, updated_at` | NEW (0 rows) |
| `db/browseros.sqlite: oauth_tokens` | SQLite table | `browseros_id, provider, access_token, refresh_token, expires_at, email, account_id, updated_at` — REDACT values always | NEW (0 rows) |
| `db/browseros.sqlite: produced_files` | SQLite table | Files the agent produced per turn: `id, agent_definition_id, session_key, turn_id, turn_prompt, path, size, mtime_ms, created_at, detected_by` | NEW (0 rows) |
| `SOUL.md` | Markdown | Persona/identity, same role as Hermes's SOUL.md | NEW |
| `skills/builtin/*/SKILL.md` | Markdown | 11 built-in browser-automation skills | NEW |

### Dashboard candidates
1. **Agent definitions + adapter/model config** (high value once populated, easy) — `agent_definitions` schema alone tells you the multi-agent pattern (name, adapter, model_id, reasoning_effort, permission_mode) — this is BrowserOS's version of a per-agent config panel.
2. **Produced-files ledger** (high value once populated, easy) — `produced_files` is essentially a structured "what did the agent create" audit trail keyed by turn — directly analogous to a session's file-diff summary.
3. Currently nothing to show — all data tables are empty on this machine; a scanner should treat "installed but 0 rows" as its own state (distinct from "not installed").

### Cross-harness parallels
- Memory: `SOUL.md` (+ empty `memory/` dir, presumably per-agent memory files land there once used)
- Subagents: `agent_definitions` table (multiple named agent configs, each with its own adapter/model/permission_mode)
- Permissions: `permission_mode` column (`'approve-all'` default)
- MCP/tools: `skills/builtin/*` (11 skills)
- Usage/quota: none observed (no token/cost columns in schema)

### Gotchas
- `oauth_tokens` table holds live tokens (columns confirmed, 0 rows currently) — treat schema-only reporting as a hard rule even if rows appear later.
- Empty directories (`memory/`, `sessions/`, `tool-output/`) exist by default at install time — don't infer "no BrowserOS install" from empty dirs; check the DB's migration table instead for a reliable "is this actually installed" signal.

---

## .claudecode — `~/.claudecode`, 1 file (0 bytes)
**What is this?** A directory (not a single file as the byte-count in the assignment suggested) containing one empty `settings.json` (0 bytes), created `2026-03-18`. No other content, no logs, no version marker. Likely a stray/misconfigured path — possibly created by a tool that expected `~/.claude` but was typo'd or namespaced differently, or an abandoned early install of some "Claude Code"-adjacent tool. Not conclusively identifiable.
**Coverage:** N/A — inert, empty. No dashboard value; flag as a known-benign stray directory if a future scan encounters it, so it isn't mistaken for a real harness.

---

## DeepSeek Harness (dsh) — `~/.dsh`
**What agent is this?** Confirmed directly from the TokenTelemetry codebase: `backend/main.py` already defines `DSH_DIR = ~/.dsh`, scans `~/.dsh/sessions/<slugged-cwd>/<session-id>/session.jsonl.zstd`, and separately maintains `DSH_LIFECYCLE_FILE = data_dir()/dsh_lifecycle.jsonl` (TokenTelemetry's OWN data dir, populated via `integrations/dsh-lifecycle-plugin` — a plugin DSH loads that reports back to TokenTelemetry, not a DSH-native file). Node modules include `@deepseek-ai/*` packages confirming DeepSeek's own harness. Session scanning (COVERED). This entry maps everything else in `~/.dsh` that main.py does NOT currently touch.
**Still active?** Yes — latest session `2026-08-16 23:34 IST`.

### Directory map
```
~/.dsh/
├── settings.yaml            # ui-onboarding, llm-pi-ai.providers (google/mistral apiKeyEnv), agent-default-model
├── .credentials.yaml        # GOOGLE_API_KEY / MISTRAL_API_KEY — REDACTED
├── storages/
│   ├── workspace.json       # {unit:{name,version}, global:{initialized, workspaceIds[], archivedSessionIds[]}, tables:{workspaces:{<id>:{path,title,sessionIds[],createdAt,updatedAt}}}}
│   └── session_projcache.json  # same {unit, global, tables} shape — per-session project cache
├── sessions/--Users-<slugged-cwd>--/{session-<uuid>|<uuid>}/session.jsonl.zstd   # COVERED by main.py
└── profiles/                # user-defined sandbox "profiles" (bundle/patch composition)
    ├── web/                 # {cordis.yml (base, empty []), cordis.patch.yml (+.bak-tt), package.json (+.bak-tt), pnpm-workspace.yaml}
    ├── node_modules/        # bundled deps for the "web" profile — SKIP, runtime (includes @deepseek-ai, @anthropic-ai, @mistralai, openai, @modelcontextprotocol, express, react, etc. — a full JS agent-tooling stack)
    └── python-architect/    # {package.json (empty scaffold), venv/} — SKIP, runtime
```

### Store inventory
| Path | Format | What it holds | Coverage |
|---|---|---|---|
| `settings.yaml` | YAML | Default model/provider (`agent-default-model: {provider: mistral, model: mistral-medium-3.5}`), onboarding state, per-provider API-key env var names | NEW |
| `.credentials.yaml` | YAML | `GOOGLE_API_KEY`, `MISTRAL_API_KEY` — REDACTED | NEW (structure only) |
| `storages/workspace.json` | JSON | Workspace registry: path, title, session-id list, timestamps per workspace | NEW |
| `storages/session_projcache.json` | JSON | Same `{unit,global,tables}` shape, session-to-project cache | NEW |
| `profiles/<name>/cordis.yml` + `cordis.patch.yml` | YAML | Sandbox "profile" composition — base tree + patch overlay defining a named dev environment DSH can spin agents into | NEW |
| `sessions/.../session.jsonl.zstd` | zstd-compressed JSONL | Full session transcript | **COVERED** (main.py already decompresses and scans) |

### Schemas
**Session JSONL** (decompressed, for context — confirms richer event types than what BRIEF's literal-file list implies main.py currently extracts):
```
session:                {type, version, id, createdAt, cwd, delegationDepth, agentPreset}
permission/preset:       {type, seq, time, data:{preset}}
sandbox/mode:            {type, seq, time, data:{mode}}
approval/policy:         {type, seq, time, data:{policy}}
agent/inbox/spliced:     {type, seq, time, data:{target, start, inserted:[...]}}
```
Note `agentPreset` (e.g. `"standard"`) and `delegationDepth` on the session header — worth checking whether main.py's current DSH scan already extracts these (they look valuable for a "preset used" / "sub-agent depth" column and may be an easy addition rather than new discovery).

**workspace.json** table entry: `{path, title, sessionIds: [...], createdAt, updatedAt}`

### Dashboard candidates
1. **Sandbox profiles panel** (medium-high value, easy) — `profiles/*/cordis.yml` + `package.json` describe named, reusable dev-environment presets (e.g. "web", "python-architect") that DSH can launch agents into — this is DSH's equivalent of a "workspace/environment templates" feature, worth its own tab.
2. **Workspace registry cross-check** (medium value, easy) — `storages/workspace.json` gives titles+paths for all known workspaces, which can enrich the project list already built from session cwd-slugs with human-readable titles.
3. **Provider/model default** (low value, trivial) — `settings.yaml`'s `agent-default-model` for a one-line "default model" fact.
4. Session-level `agentPreset`/`delegationDepth`/`permission/preset`/`sandbox/mode`/`approval/policy` events — verify whether the existing DSH scanner in main.py surfaces these; if not, this is a low-effort enrichment of an already-covered store rather than a new one.

### Cross-harness parallels
- Config/permissions: `sandbox/mode`, `approval/policy`, `permission/preset` events per session — DSH's per-turn sandbox/approval state machine.
- Plan/environment artifacts: `profiles/*/cordis.yml` (environment-as-code templates).
- Subagents: `delegationDepth` field on the session header.

### Gotchas
- `profiles/*/node_modules` and `profiles/python-architect/venv` are large bundled runtimes (most of the 309M under `profiles/`) — skip, matches exclusion rule.
- Two session-id naming conventions coexist under the same cwd-slug dir: `session-<uuid>` and bare `<uuid>` — a scanner must handle both.
- `dsh_lifecycle.jsonl` (mentioned in BRIEF) is **not** inside `~/.dsh` at all — it's written by TokenTelemetry's own plugin integration into TokenTelemetry's data dir. Don't go looking for it under `~/.dsh`.

---

## HeyGen Hyperframes (video-template registry) — `~/.hyperframes`, 40K
**What is this?** `config.json`: `telemetryEnabled, anonymousId, commandCount, latestVersion`. Cache filenames are literal GitHub raw URLs (`https___raw_githubusercontent_com_heygen_com_hyperframes_main_registry__examples__*.json`) for a "hyperframes" template registry (kinetic-type, swiss-grid, vignelli, decision-tree, nyt-graph, etc. — data-viz/motion-graphics templates). This pairs with the `remotion-best-practices` skill seen in the Vercel skills registry — likely a Remotion-based video-template CLI a coding agent shells out to, not an agent itself.
**Coverage:** N/A (not agent/session data) — flag only.

### Directory map
```
~/.hyperframes/
├── config.json     # {telemetryEnabled, anonymousId, telemetryNoticeShown, commandCount, lastUpdateCheck, latestVersion}
└── cache/          # 9 cached registry/example JSON files, named after their source GitHub raw URL
```

### Dashboard candidates
None for cost/session tracking. Possible tiny "commandCount" usage-frequency stat if TokenTelemetry ever inventories companion CLI tools, but not a priority.

---

## galileo — `~/.galileo`, empty
Empty directory, 0 files, 0 bytes. No content to identify or map. Confirmed not a stray/rename artifact of anything else surveyed here.

---

## Reddit Devvit CLI — `~/.devvit`, 8K
**What is this?** `token` + `session-id` — Reddit's Devvit developer-platform CLI auth state. Not a coding agent; a deployment tool for building Reddit apps. **Coverage: N/A** — flag existence, redact `token` contents.

---

## cua-driver (Computer-Use Agent driver) — `~/.cua-driver`, 8K
**What is this?** `.installation_recorded`, `.telemetry_id`, empty `packages/` dir. Matches the "cua" (Computer Use Agent) driver install marker pattern — a macOS sandboxed computer-use framework, likely `trycua/cua`. No session data present; `packages/` is empty on this machine (nothing installed yet).
**Coverage:** N/A — install markers only, no usage data to mine currently.

---

## promptfoo (LLM eval framework) — `~/.promptfoo`, ~1.4M total (db 532K + logs 720K + cache 108K)
**What is this?** Not a coding agent — an **LLM evaluation/red-teaming framework** the user runs standalone (e.g. to compare model outputs, cost, latency). Genuinely rich, structured cost/performance data that nothing else in this survey has in this exact shape.
**Still active?** Yes — DB last written `2026-08-13`.

### Directory map
```
~/.promptfoo/
├── promptfoo.yaml            # top-level eval config (not sampled in depth)
├── promptfoo.db (+ -shm/-wal)  # SQLite, see schema below
├── evalLastWritten           # marker file
├── cache/cache.json          # cached provider responses (keyed cache, not sampled for content — could hold prompt text)
└── logs/promptfoo-{debug,error}-<timestamp>.log   # ~18 debug + 18 error logs from a single 2026-08-13 session
```

### Store inventory
| Table | Row count | Key columns | Coverage |
|---|---|---|---|
| `evals` | 5 | `id, created_at, description, results, config, author, prompts, vars, is_redteam, runtime_options` | NEW |
| `eval_results` | 26 | `id, eval_id, prompt_idx, test_idx, provider, latency_ms, cost, response, error, success, score, grading_result, named_scores, metadata, failure_reason` | NEW |
| `prompts` | 1 | (not sampled in detail) | NEW |
| `datasets` | 1 | (not sampled in detail) | NEW |
| `traces` | 0 | tracing/span support present but unused | NEW |
| `spans` | 0 | — | NEW |
| `model_audits` | 0 | red-team model-audit table, unused | NEW |
| `evals_to_datasets` / `evals_to_prompts` / `evals_to_tags` / `tags` | (join tables) | — | NEW |

### Schemas
`eval_results` has **per-row cost and latency already computed** (`cost REAL, latency_ms INT, provider TEXT, success INT, score REAL`) — this is the only surveyed store with ready-made per-call cost data outside TokenTelemetry's own tracked harnesses.

### Dashboard candidates
1. **"Model comparison" panel** (high value, easy) — `eval_results` grouped by `provider` gives cost/latency/success-rate comparison across models/providers the user has benchmarked — directly complements TokenTelemetry's own per-agent cost tracking with an explicit "which model did I evaluate as cheapest/fastest/most successful" view.
2. **Eval history list** (medium value, easy) — `evals` table (5 rows: id, created_at, description, author, is_redteam flag) as a simple timeline.
3. Given only 5 evals / 26 results on this machine, this is a light-usage tool for this user — reasonable as an optional "LLM eval activity" card rather than a full sub-dashboard, unless promptfoo usage is heavier for other users.

### Cross-harness parallels
Not an agent — no jobs/memory/todos/subagents concept applies. Its unique contribution is **usage/quota state analog**: explicit, already-computed cost-per-call across providers.

### Gotchas
- `cache/cache.json` may contain cached prompt/response text (not opened in depth here to respect the "never quote prompts/responses" rule) — a scanner extracting from this file must not surface raw prompt/response content in any UI, only aggregate stats from the DB's `cost`/`latency_ms`/`success` columns.
- Debug/error logs are verbose (36 files from one work session) — likely need age-based pruning awareness if surfaced.

---

## mcp-auth (OAuth token store — STRUCTURE ONLY) — `~/.mcp-auth`
**What is this?** Standard `mcp-remote` (the reference MCP OAuth proxy) token cache directory.
**Content:** `~/.mcp-auth/mcp-remote-0.1.37/` — currently **empty** (0 files) on this machine; the versioned subdirectory exists (created when `mcp-remote` first ran) but holds no cached token files at scan time.
**Security note followed:** no file inside was opened; only directory shape and the versioned-subdir naming convention (`mcp-remote-<version>/`) are reported, per the hard security rule. If populated, this directory is known (from the `mcp-remote` project convention) to contain per-server OAuth token JSON files — none should ever have their contents read or surfaced by a scanner beyond "N tokens cached."

### Dashboard candidates
"N cached MCP OAuth sessions" count only (directory entry count), never token contents or server URLs if those appear in filenames.

---

## Flagged but NOT in the assigned list (found via `ls -d ~/.[a-z]*` sweep)

These weren't assigned, so they're mapped lightly (structure/identification only) rather than exhaustively — flagging for a follow-up pass:

### `~/.antigravity` (553M) and `~/.antigravity-ide` (543M)
These are **top-level** dirs distinct from the already-covered `~/.gemini/{antigravity,antigravity-cli,antigravity-ide}/brain` path in BRIEF.md. Structure (`extensions/`, `argv.json`, binary name matching dir name) shows these are the **VS-Code-fork IDE's own profile directories** (installed extensions: Python, Go, Java toolchain, PHP, gemini-cli-vscode-ide-companion, etc.) — i.e., Antigravity-the-IDE's application data, not Antigravity-the-agent's conversation/brain data. The actual chat/session data for an Electron/VS-Code-fork app like this typically lives under `~/Library/Application Support/<AppName>/User/{globalStorage,workspaceStorage}` (macOS), not under this dot-dir — that location was **not checked** in this pass and is a solid lead for whoever picks up Antigravity coverage next, since BRIEF's `~/.gemini/antigravity*/brain` path may not be the only (or even primary) place Antigravity persists conversations.

### `~/.openclaw` (2.4M)
`claw3d/settings.json`: `{"adapter": "hermes", "url": "ws://localhost:18789", "token": ""}`. This is a **3D visualization/companion front-end that connects to Hermes** (already-covered harness) over a local WebSocket — not an independent agent. `workspace/` is empty; `skills/` duplicates the same Cloudflare skill set seen under `~/.pi/agent/skills` (same cross-agent skill-sync pattern as the Vercel registry above). No standalone dashboard value — at most, link it as "Hermes companion UI" if Hermes's panel wants to note companion apps.

### `~/.lmstudio` (~18.6G total, mostly model weights)
LM Studio — a local-inference runtime (Ollama's peer/competitor). `models/` (17G, GGUF weights — excluded per traversal rules), `extensions/`/`apps/`/`bin/` (bundled runtime, excluded). Checked `.internal/ui-state/` for chat history — it only holds window-position UI state, **not** conversation data; LM Studio's actual chat/conversation store (if any persists outside its Electron app-support dir) was not found under `~/.lmstudio` in this pass. `credentials/` has `lmstudio-hub.json` + `mcp-oauth`/`ng-mcp-oauth` subdirs (unopened, OAuth-shaped, redact on sight). Given this repo is mid-flight on `feat/local-model-insights`, LM Studio is worth a dedicated follow-up: it's a second local-inference engine alongside Ollama that BRIEF doesn't mention at all, and its real usage/session data likely lives outside the home-dot-dir convention (check `~/Library/Application Support/LM Studio` next).

No other unlisted dot-dirs in the sweep looked coding-agent-shaped — the rest (`.anydesk`, `.azcopy`, `.azuredatastudio`, `.bundle`, `.cargo`, `.docker`, `.EasyOCR`, `.electron-gyp`, `.expo`, `.fx`, `.ivy2`, `.jupyter`, `.matplotlib`, `.pgadmin`, `.pyenv`, `.rustup`, `.ServiceHub`, `.streamlit`, `.swiftpm`, `.thumbnails`, `.vscode-shared`, `.zsh_sessions`, etc.) are generic dev-tool/OS/shell state, not coding-agent harnesses.
