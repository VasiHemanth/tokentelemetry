# Qoder — filesystem survey

Scope: `~/.qoder` and `~/Library/Application Support/com.qoder.app.stable`, on a
fresh install with two sessions. Paths are written with a `/Users/dev/`
placeholder; the real account name never appears here.

Credential and account files are reported as existing only — never opened.

Qoder is Alibaba's AI coding IDE. Two surfaces ship together: a CLI harness and
an Electron app. They are **not** two data sets — see "One set of sessions".

---

## What this harness is

`~/.qoder` is laid out exactly like `~/.claude`: `projects/<slugged-cwd>/<uuid>.jsonl`,
`shell-snapshots/snapshot-zsh-<ms>-<rand>.sh`, per-session `state.json` and
`subagents/`. Records carry `cwd`, `gitBranch`, `isSidechain`, `parentUuid`,
`sessionId`, `version`, `userType` and `entrypoint` — Claude Code's schema
verbatim. Qoder's CLI is a Claude Code derivative.

Versions on the surveyed install: CLI `1.1.31`, app `0.1.2`.

### Directory map

```
~/.qoder/                        20 MB
├── projects/                    696 KB  — the sessions
│   └── -Users-dev-Documents-Qoder-2026-08-30-<short>/
│       ├── <session-uuid>.jsonl          # the transcript
│       ├── <session-uuid>/
│       │   ├── state.json                # ENCRYPTED (see below)
│       │   ├── compression-v2/state.json # compaction state, encrypted
│       │   └── subagents/
│       │       ├── agent-a<type>-<hash>.jsonl       # child transcript
│       │       └── agent-a<type>-<hash>.meta.json   # {agentType, toolUseId,
│       │                                            #  description, invocationName}
│       └── memory/                       # empty on this install
├── plugins/                     10 MB   — installed_plugins_v2.json + cache/ + data/
├── bin/                        6.5 MB   — bundled qoder-computer-use — SKIP, runtime
├── logs/                       1.2 MB   — runs/, sessions/, qoder-context.log
├── .models/                    112 KB   — default (plaintext), catalog-v6 (ENCRYPTED)
├── shell-snapshots/                     — same shape as Claude Code's
├── .cache/                              — dns-cache.json, endpoint-cache.json
├── entry/qoder                          — launcher script; reads only HOME
├── settings.json                        — {"enabledPlugins": {...}}
├── installation_id
├── .auth/                               — NEVER READ
└── .qoder-app-status.json               — NEVER READ (see Secrets)

~/Library/Application Support/com.qoder.app.stable/   40 MB
├── main.sqlite (+ -wal, -shm)   1.9 MB + 4.4 MB WAL
├── memoryMigration.sqlite, sessionMigration.sqlite
├── qoder-data.v1.json
├── auth.v1.dat, auth.machine-id, Cookies   — NEVER READ
└── Cache/, GPUCache/, blob_storage/, …     — Electron runtime
```

---

## The finding that matters: no token counts, credits instead

Every assistant record carries a `usage` object in Anthropic's shape, and every
token counter in it is **zero**:

```json
{"input_tokens":0,"output_tokens":0,"cache_read_input_tokens":0,
 "cache_creation_input_tokens":0,
 "server_tool_use":{"web_search_requests":0,"web_fetch_requests":0},
 "service_tier":"standard","inference_geo":"","iterations":[],"speed":"standard",
 "credits":1.5205821428571429,"original_credits":3.0411642857142858,
 "billable":true,"request_id":"<uuid>","context_usage_ratio":0.026787}
```

This held for all 22 assistant turns across every session and subagent
transcript on this install. `credits` is the only spend Qoder records.
`original_credits` is consistently 2× `credits`, which looks like a list price
against a charged price, though nothing on disk states the relationship.

**Tokens cannot be reconstructed.** `context_usage_ratio` is a fraction of an
unknown denominator: `runtime-config.contextWindow` is `null`, and the IDE's
`chat_session_context_usage` snapshot reports `"totalTokens":0,"maxTokens":0`
alongside a non-zero `percentage`. There is no local number to scale by.

Measured spend on this install:

| | credits |
|---|---|
| Root sessions (2) | 6.5609 |
| Subagent transcripts (2) | 6.3803 |
| Total | 12.9412 |

Delegation is 49% of spend — worth surfacing, because a parent-only view halves
the apparent cost of a Qoder session.

---

## One set of sessions, two surfaces

`main.sqlite` looks like a second session store and is not. Its
`chat_session_messages.source` is `sdk-projection`, its message ids are the CLI
transcript's own uuids (`13bd5674-…` appears in both), and its two
`chat_sessions.session_id` values are the two CLI session uuids. Scanning both
would double-count every session.

What the DB adds that the JSONL lacks:

- `chat_sessions.title` — a real title ("better-harness specialty vs claude")
  where the JSONL has only the first prompt
- `durationMs` / `turnCount` per assistant message
- `session_kind` ∈ {`standard`, `sideChat`, `automationExecution`} and
  `product_mode` ∈ {`coding`, `general`}

Both surveyed rows are `standard`, and the two `chat_sessions.session_id`
values are exactly the two transcript ids — no IDE-only session exists on this
install.

**Known limitation.** TokenTelemetry therefore takes sessions from the JSONL
alone and uses the DB only for titles. If `sideChat` or `automationExecution`
sessions turn out not to write a transcript, they would be invisible. That
cannot be observed here, so the union-and-dedupe that would cover it is
deliberately not built rather than written against a shape nobody has seen.
Re-check this the first time a Qoder side chat or scheduled automation runs.

### `main.sqlite` tables worth knowing about

`chat_sessions`, `chat_session_messages`, `chat_session_context_usage`,
`chat_session_recaps`, `chat_session_highlights`, `chat_session_search_fts*`,
`turn_file_change_{sets,files,operations,patches}`, `scheduled_tasks` +
`scheduled_task_settings` + `scheduled_task_run_logs`, `managed_worktrees` +
`managed_worktree_sessions`, `mcp_connection_profiles`, `byok_model_profiles`,
`plugin_inventory_*`, `marketplace_*`, `workspaces`, `remote_ssh_hosts`,
`account_profiles`.

On this install `workspaces`, `scheduled_tasks` and `turn_file_change_sets` are
all empty — real schemas with nothing in them yet, which is a distinct state
from "not supported".

---

## Encrypted at rest (opaque, not missing)

- **`.models/<uid>/catalog-v6`** — base64 ciphertext. So the model ids in
  transcripts (`qmodel_38max`, `qfmodel`) cannot be mapped to real model names
  offline, and there is no published price list to cost them against.
- **`projects/*/<uuid>/state.json`** — each item is `{c, u, n, p, t}` where `p`
  is a ciphertext payload and `t` an auth tag. Resumable context, todos and
  compaction state are unreadable.

---

## Record types in the transcript

Beyond Claude Code's `user` / `assistant`:

| Type | Contents |
|---|---|
| `workspace-directories` | `directories[]` — line 1 of every file, the reliable project source |
| `runtime-config` | `model`, `reasoningEffort`, `contextWindow` (null), `timestamp` in **epoch ms** |
| `last-prompt` | `lastPrompt` — the most recent user prompt |
| `active-leaf` | `leafUuid`, `explicit` — conversation-tree pointer |
| `attachment` | harness-injected context, four kinds (below) |

`user` records are three different things: a human turn (`origin.kind ==
"human"`, with a parallel `humanInput.text`), a tool result (content is
`tool_result` blocks, no origin), or a harness injection. Only the first two
belong in a trace.

### Attachment kinds observed

| `attachment.type` | Payload | Note |
|---|---|---|
| `skill_listing` | `names[]`, `skillCount`, `content` (~2.5 KB) | the injected skill catalogue — availability, not usage |
| `critical_system_reminder` | `serverNames[]`, `content` (~1.7 KB) | MCP servers offered to the session |
| `agent_listing_delta` | `addedTypes`, `addedLines`, `removedTypes` | subagent roster changes |
| `hook_output` | `hookEventName`, `output` | hook results |

None is a user turn. None carried a file body on this install, but an
attachment type that does is plausible, so a consumer should allowlist known
kinds rather than denylist these four.

### The injected prompt prefix

The first human prompt begins with a `<system-reminder>…</system-reminder>`
block naming the enabled plugins, in **both** `message.content[0].text` and
`humanInput.text`. Rendered verbatim it reads as if the user typed the
harness's instructions.

---

## The directory slug is not reversible

`-Users-dev-Documents-Qoder-2026-08-30-d5db2e1b` came from
`/Users/dev/Documents/Qoder/2026-08-30/d5db2e1b`. Slashes became dashes and the
dashes already in the path were left alone, so the slug has several valid
readings. Use `cwd` from the records, or `workspace-directories.directories[0]`.

---

## Secrets — existence only, never read

- `~/.qoder/.auth/**`
- `~/Library/Application Support/com.qoder.app.stable/auth.v1.dat`,
  `auth.machine-id`, `Cookies`
- `main.sqlite` tables `byok_model_credentials`, `mcp_oauth_credentials`

**`~/.qoder/.qoder-app-status.json` holds the account holder's real name and
email address in plaintext.** It is not read at all — not for a version string,
not for anything. `installation_id` and `.models/default`'s `uid` are stable
account-scoped identifiers and are equally out of bounds.

`main.sqlite` must be opened read-only; the app holds a 4.4 MB WAL while running.

---

## No relocation env var

`~/.qoder/entry/qoder` references only `HOME`, `PATH`, `LC_ALL` and
`VSCODE_IPC_HOOK_CLI`. There is no `QODER_HOME` upstream, so the root is fixed
at `~/.qoder`. TokenTelemetry still honours `QODER_HOME` / `QODER_IDE_HOME` so
tests can point the scan at a fixture tree.
