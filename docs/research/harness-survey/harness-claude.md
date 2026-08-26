# Claude Code harness survey — `~/.claude` (4.0G, 182500 files), `~/.claude.json` (+`.backup`), `~/.claudecode`

## Claude Code — `~/.claude`, 4.0G, ~182500 files
**Agent identity / still active?** Yes — actively used right now (this survey runs inside it). CLI version seen in job/session state: `2.1.243`–`2.1.246`. Latest mtimes are live (daemon.log, sessions/*.json updated at survey time).

### Directory map
```
~/.claude/
├── jobs/                     3.3G  # 48 background-agent job dirs (fleet/bg tasks), see below — NEW
│   └── <short-id>/{state.json, timeline.jsonl, tmp/}   # tmp/ = scratch workspace (repo clones, logs, node_modules); NOT durable data
├── projects/                 570M  # 51 dirs, one per encoded cwd — session transcripts (COVERED) + workflows/subagents sidecars (NEW, see below)
│   └── -Users-...-<project>/
│       ├── <session-uuid>.jsonl          # transcript (COVERED, brief says don't read bodies)
│       ├── <session-uuid>/               # sidecar dir, same name as a transcript, NOT always present
│       │   ├── workflows/wf_<id>.json           # Workflows feature run summary — NEW
│       │   ├── workflows/scripts/<name>-wf_<id>.js  # generated workflow script — NEW
│       │   └── subagents/workflows/wf_<id>/agent-<hash>.{jsonl,meta.json}, journal.jsonl  # per-subagent trace, same shape as /sessions/{id}/subagents/{aid}/trace (COVERED)
│       └── bridge-pointer.json           # rare (1 of 51 project dirs) — points at a claude.ai cloud "environment" bridging this local project — NEW
├── plugins/                   88M
│   ├── installed_plugins.json           # COVERED (literal in brief)
│   ├── blocklist.json, known_marketplaces.json, plugin-catalog-cache.json  # marketplace/plugin metadata caches — NEW, low value
│   ├── cache/<marketplace>/<plugin>/<version>/   # git-cloned plugin source (openai-codex, grok-mcp, naluforge-gemini, manim-skill, claude-plugins-official, tokentelemetry)
│   ├── marketplaces/<name>/              # full git clones of marketplace repos (bulk of the 88M)
│   └── data/<agent>-<plugin>/state/<project-slug>/{state.json, jobs/task-*.{json,log}}  # per-plugin runtime job state — NEW (see Codex-plugin schema below); only openai-codex has non-empty data currently
├── file-history/              53M   # NEW — per-session file-edit checkpoint/rewind store
│   └── <session-uuid>/<file-content-hash>@v<N>   # raw file snapshot, one per (file, edit revision); no manifest/index file found mapping hash→original path in the dir itself (path likely only recoverable via the transcript's Edit/Write tool_use records)
├── uploads/                   11M   # NEW, small — per-session pasted/attached images: <session-uuid>/<hash>-<original-name>.jpeg
├── skills/                  2.5M   # user + plugin skills, SKILL.md (COVERED, literal)
├── history.jsonl             844K  # NEW-ish — global CLI prompt-recall log, 2564 lines, ALL projects/sessions (not just current cwd)
├── backups/                  704K  # rotating ~/.claude.json.backup.<epoch-ms> snapshots — plumbing, not dashboard-worthy
├── session-env/               672K  # NEW, low value — per-session generated SessionStart hook shell scripts (export CODEX_COMPANION_*, CLAUDE_PLUGIN_DATA env vars)
├── telemetry/                 648K  # NEW, low value — Anthropic's own 1p_failed_events.<session>.<event>.json (internal product-analytics retry queue, e.g. "chrome_bridge_connection_started")
├── cache/                     612K  # cache/changelog.md, cache/my-closed-issues.json (gh issue cache, empty)
├── daemon.log                 276K  # supervisor log — low value
├── debug/                      56K  # per-session debug .txt logs + "latest" symlink/pointer — low value, may contain stack traces
├── paste-cache/                44K  # NEW — cached clipboard paste bodies keyed by hash, plain .txt (privacy-sensitive, contents not inspected)
├── sessions/                   24K  # NEW — live process registry: <pid>.json (session/daemon liveness) + <pid>.<hash>.key (auth key, not read)
├── daemon/                     20K  # NEW — supervisor state: roster.json (live worker registry, richest cross-reference to jobs/), control.key (not read), auth/, dispatch/ (transient, empty), attach-journal/<gestureId>.json
├── shell-snapshots/            16K  # COVERED per brief (don't read bodies)
├── agents/                     16K  # 2 user subagent defs (analytics-architect.md, telemetry-implementer.md) — COVERED (same as project .claude/agents)
├── statsig/                    12K  # Anthropic's internal feature-flag/telemetry client cache (session_id, stable_id, failed_logs) — not user-facing, skip
├── todos/                     8.0K  # NEW-ish — TodoWrite tool state, <session>-agent-<agent>.json, array of {content,status,activeForm}; both observed files were empty ([])
├── tasks/                     4.0K  # NEW, low value — per-session background-task coordination: <session-uuid>/{.lock, .highwatermark}
├── stats-cache.json            20K  # NEW — Claude Code's own precomputed usage/activity cache (see schema below) — high value, essentially free aggregate stats
├── gh-pr-status-cache.json     20K  # NEW, repo-scoped — cached `gh pr` status per PR URL (number, title, state, checks, review, additions/deletions)
├── mcp-needs-auth-cache.json   4.0K # NEW, tiny — MCP servers pending auth: {name: {timestamp, id}}
├── daemon.status.json          4.0K # supervisor liveness snapshot (workers currently {} = none running standalone)
├── daemon-auth-status.json     4.0K # {"status":"auth_required","since":<epoch>} — auth gate state
├── daemon-auth-cooldown        4.0K # opaque cooldown marker, not read
├── daemon.lock                 4.0K # pid lock file
├── settings.json               4.0K # global config: model, effortLevel, theme, editorMode, enabledPlugins, statusLine, tui/voice flags — COVERED (literal); no hooks/permissions keys present globally (those live in per-project .claude/settings.json)
├── chrome/chrome-native-host   4.0K # Chrome extension native-messaging host binary/manifest for claude-in-chrome — plumbing
├── CLAUDE.md                   4.0K # global user instructions — COVERED
├── statusline-command.sh        —   # user's custom statusline script
├── ide/                          0B  # empty
└── downloads/                    0B  # empty
```

### Store inventory
| Path | Format | What it holds | Cadence | Retention/cleanup | Coverage |
|---|---|---|---|---|---|
| `jobs/<id>/state.json` | JSON | Background/fleet agent job: state, tempo, inFlight, fan (running sub-tasks), children (linked PRs/issues), tokens, output.result, intent, name, sessionId, template (`claude`/`bg`), cliVersion, cwd, timestamps, bridgeSessionId | on every state change | 48 jobs accumulated since Jun 2026, no visible auto-prune | **NEW** |
| `jobs/<id>/timeline.jsonl` | JSONL | State-transition log for the job: `{at, state, detail, text}` per line | append per transition | grows with job | **NEW** |
| `jobs/<id>/tmp/**` | mixed | Scratch workspace the job used (repo clones, logs, patch files, even a full node_modules-style `eslint10/`) — this is *why* jobs/ is 3.3G (two jobs alone are 2.9G) | per job | never cleaned — pure disk bloat, not queryable data | not applicable (noise) |
| `plugins/data/<agent>-<plugin>/state/<slug>/state.json` | JSON | Per-project runtime state for a Claude Code plugin (only `codex-openai-codex` populated): `{version, config:{stopReviewGate}, jobs:[{id, kind, kindLabel, title, workspaceRoot, jobClass, summary, sessionId, status, phase, logFile, threadId, turnId, timestamps}]}` | per Codex-rescue invocation | not observed to prune | **NEW** |
| `file-history/<session>/<hash>@v<N>` | raw file bytes | Checkpoint/rewind snapshots — one blob per file per edit revision within a session | on every file-modifying tool call | no visible cap/rotation; scales with edit volume | **NEW** |
| `daemon/roster.json` | JSON | Live process supervisor registry of all currently-tracked daemon workers, keyed by job short-id: pid, procStart, sessionId, sockets, cliVersion, dispatch (launch args, isolation, env), decModes, firedInteractiveMarks, rvAuth/ptyAuth (**redacted**) | rewritten on worker start/stop | ephemeral (current state only) | **NEW** |
| `sessions/<pid>.json` | JSON | One record per live Claude Code process: pid, sessionId, cwd, startedAt, version, peerFeatures, kind (`bg`), entrypoint, messagingSocketPath, agent, jobId, status | per process lifecycle | pruned when process exits (2-3 present at survey time) | **NEW** |
| `stats-cache.json` | JSON | Precomputed usage rollup: `dailyActivity[]` (date, messageCount, sessionCount, toolCallCount), `dailyModelTokens[]` (date, tokensByModel), `modelUsage{model: {inputTokens, outputTokens, cacheReadInputTokens, cacheCreationInputTokens, webSearchRequests, costUSD, contextWindow, maxOutputTokens}}`, `totalSessions`, `totalMessages`, `longestSession`, `firstSessionDate`, `hourCounts{0-23}` | recomputed periodically (`lastComputedDate`) | rolling, no expiry seen | **NEW** (duplicates what TT derives from transcripts, but is a free precomputed cross-check / fast path) |
| `~/.claude.json` → `projects.<path>` | JSON | Per-project last-session cache: `allowedTools, mcpServers, enabledMcpjsonServers/disabledMcpjsonServers, hasTrustDialogAccepted, exampleFiles, lastCost, lastAPIDuration(WithoutRetries), lastToolDuration, lastDuration, lastLinesAdded/Removed, lastTotal{Input,Output,CacheCreationInput,CacheReadInput}Tokens, lastTotalWebSearchRequests, lastFpsAverage, lastFpsLow1Pct, lastModelUsage, lastSessionId, lastSessionMetrics` | on session end | 38 projects tracked | PARTIAL (metrics duplicate transcript data; `lastFps*` terminal-render perf is genuinely new) |
| `~/.claude.json` → `cachedUsageUtilization` | JSON | Anthropic subscription rate-limit state: `{fetchedAtMs, accountUuid (redact), utilization: {five_hour: {utilization%, resets_at, limit/used/remaining_dollars}, seven_day: {...}}}` | refreshed periodically | single snapshot, overwritten | **NEW — high value** (this is the "usage/quota/rate-limit state" cross-harness parallel) |
| `~/.claude.json` → `skillUsage` / `pluginUsage` / `agentLastUsed` | JSON | Feature-adoption counters: `{name: {usageCount, lastUsedAt[, lastUsedNumStartups]}}` | incremented on use | cumulative since install | **NEW** |
| `~/.claude.json` → `routineFiredWatermark` | ISO string | High-water mark for the cloud "Routines" (scheduled cloud agents) feature | updated when a routine fires | single value; routine *definitions* are NOT stored locally (cloud-hosted per the `/schedule` skill) | **NEW but thin** (watermark only, no local schedule store) |
| `~/.claude.json` → `githubRepoPaths`, `closedIssuesLastChecked`, `metricsStatusCache` | JSON | Misc caches: repo→local-path map, last gh-issue-check timestamp, telemetry-enabled flag+timestamp | ad hoc | small | **NEW**, low value |
| `todos/<session>-agent-<agent>.json` | JSON | TodoWrite tool state: array of `{content, status, activeForm}` | overwritten per TodoWrite call | often ends as `[]` once all todos complete/cleared | **NEW-ish** |
| `projects/<proj>/<session>/workflows/wf_<id>.json` | JSON | "Workflows" feature run record: `runId, timestamp, taskId, script, scriptPath, result{...arbitrary}, agentCount, durationMs, summary, workflowName, status, startTime, phases[{title,detail}], defaultModel, workflowProgress[], totalTokens, totalToolCalls` | one per workflow run | 512 files across 40 session dirs — real, recurring feature | **NEW — high value** |
| `projects/<proj>/bridge-pointer.json` | JSON | `{sessionId, environmentId, source, pid, procStart}` — pointer to a claude.ai cloud "environment" bridged to this local project | written when a cloud/remote bridge session attaches | rare (1 of 51 projects) | **NEW** |
| `history.jsonl` | JSONL | Global prompt-input recall log across ALL projects: `{display, pastedContents, timestamp, project, sessionId}` per submitted prompt | append per prompt | 2564 lines, unbounded | PARTIAL (literal name is in brief's list, but likely referring to per-harness history files elsewhere, not this global CLI recall log specifically) |
| `gh-pr-status-cache.json` | JSON | `{prUrl: {number, title, state, checks:{passed,failed,pending}, review, additions, deletions}}` | refreshed by `gh`-calling skills (e.g. bug-audit) | repo-scoped, small | **NEW**, low general value |
| `mcp-needs-auth-cache.json` | JSON | `{serverName: {timestamp, id}}` — MCP servers pending OAuth | on auth prompt | tiny | **NEW**, low value |
| `telemetry/1p_failed_events.*.json` | JSON (one object per file) | Anthropic's own internal product-analytics event that failed to upload, e.g. `event_type, event_data{event_name, client_timestamp, model, session_id, user_type, betas, env}` | on failed telemetry POST | 9 files present | **NEW**, low value (Anthropic-internal, not user data) |

### Schemas
**`jobs/<id>/state.json`** (elided):
```json
{
  "state": "done|blocked|working|stopped",
  "detail": "<elided-str>", "tempo": "idle|blocked",
  "inFlight": {"tasks": 1, "queued": 0, "kinds": ["local_bash"], "drainableMonitors": 0},
  "fan": [{"id": "...", "kind": "shell", "label": "<elided>", "startedAt": 0}],
  "tokens": 0,
  "output": {"result": "<elided-str>"},
  "needs": "<elided-str>",
  "children": [{"id": "272", "href": "https://github.com/.../pull/272", "kind": "pr"}],
  "linkScanOffset": 0, "linkScanPath": "<elided-str>",
  "template": "claude|bg",
  "respawnFlags": ["--allowed-tools", "..."],
  "bgIsolation": "none", "providerEnv": {},
  "intent": "<elided-str>", "name": "<elided-str>", "nameSource": "auto",
  "sessionId": "<uuid>", "resumeSessionId": "<uuid>", "daemonShort": "<8hex>",
  "cliVersion": "2.1.243", "cwd": "<elided-str>", "originCwd": "<elided-str>",
  "bridgeSessionId": "cse_<id>", "bridgeOwnerAccountUuid": "<redacted>",
  "bridgeOwnerOrganizationUuid": "<redacted>", "bridgeOutboundOnly": false,
  "bridgeSessionSeq": 609, "backend": "daemon",
  "createdAt": "iso", "updatedAt": "iso", "firstTerminalAt": "iso",
  "suggestedReply": "<elided-str>"
}
```

**`jobs/<id>/timeline.jsonl`** (one line, elided): `{"at": "iso", "state": "done", "detail": "<elided-str>", "text": "<elided-str>"}`

**`plugins/data/codex-openai-codex/state/<slug>/state.json`** (elided):
```json
{
  "version": 1, "config": {"stopReviewGate": false},
  "jobs": [{
    "createdAt": "iso", "updatedAt": "iso", "id": "task-<id>", "kind": "task",
    "kindLabel": "rescue", "title": "Codex Task", "workspaceRoot": "<elided-str>",
    "jobClass": "task", "summary": "<elided-str>", "write": false,
    "sessionId": "<uuid>", "status": "completed", "startedAt": "iso",
    "phase": "done", "pid": null, "logFile": "<elided-str>",
    "threadId": "<uuid>", "turnId": "<uuid>", "completedAt": "iso"
  }]
}
```

**`daemon/roster.json`** (elided, per worker):
```json
{
  "proto": 1, "supervisorPid": 0, "updatedAt": 0,
  "workers": {
    "<short-id>": {
      "pid": 0, "procStart": "<str>", "sessionId": "<elided>",
      "rendezvousSock": "<elided>", "ptySock": "<elided>", "cliVersion": "2.1.243",
      "startedAt": 0, "attempt": 1, "cwd": "<elided>",
      "dispatch": {
        "proto": 1, "short": "<id>", "nonce": "<8hex>", "sessionId": "<elided>",
        "createdAt": 0, "source": "fleet", "cwd": "<elided>",
        "launch": {"mode": "resume|prompt", "sessionId": "<elided>", "transcriptPath": "<elided>", "fork": false, "flagArgs": ["..."], "restoresTranscript": true},
        "env": {"CLAUDE_BG_ISOLATION": "none"}, "isolation": "none",
        "respawnFlags": ["..."], "seed": {"intent": "", "name": "<elided>"},
        "cols": 208, "rows": 54
      },
      "decModes": [1000, 1002],
      "firedInteractiveMarks": [{"kind": "content_paint", "msgsLoaded": 0, "msgsInJsonl": 0, "msgsRenderedAtFirstPaint": 0}],
      "rvAuth": "<redacted>", "ptyAuth": "<redacted>"
    }
  }
}
```

**`sessions/<pid>.json`**:
```json
{
  "pid": 0, "sessionId": "<uuid>", "cwd": "<elided>", "startedAt": 0,
  "procStart": "<str>", "version": "2.1.246", "peerProtocol": 1,
  "peerFeatures": ["notify_idle", "artifact_yield"], "kind": "bg",
  "entrypoint": "cli", "pidDomain": "darwin", "messagingSocketPath": "/tmp/cc-socks/<pid>.sock",
  "name": "<id>", "nameSince": 0, "agent": "claude", "jobId": "<id>",
  "spare": true, "status": "idle", "updatedAt": 0, "statusUpdatedAt": 0
}
```
(sibling `<pid>.<sha256>.key` file exists per session — not read, name pattern matches "key" so treated as credential-adjacent.)

**`stats-cache.json`** top-level keys: `version, lastComputedDate, dailyActivity[], dailyModelTokens[], dailyModelTokensVersion, modelUsage{}, totalSessions, totalMessages, longestSession{sessionId,timestamp,duration,messageCount}, firstSessionDate, hourCounts{}`.
- `dailyActivity[]` item: `{date, messageCount, sessionCount, toolCallCount}`
- `dailyModelTokens[]` item: `{date, tokensByModel: {model: tokens}}`
- `modelUsage` item: `{inputTokens, outputTokens, cacheReadInputTokens, cacheCreationInputTokens, webSearchRequests, costUSD, contextWindow, maxOutputTokens}`

**`~/.claude.json`** top-level keys (89 total; dashboard-relevant subset): `projects{}` (38 entries, per-project cache — see table above), `cachedUsageUtilization`, `skillUsage`, `pluginUsage`, `agentLastUsed`, `routineFiredWatermark`, `githubRepoPaths`, `closedIssuesLastChecked`, `metricsStatusCache`, `oauthAccount` (**redacted**), `machineID`/`remoteControlMachineId` (**redacted, treat as identifiers**). Remainder (~70 keys) are onboarding/UI-hint booleans and counters (`hasSeenTasksHint`, `tipsHistory`, `announcementImpressions`, etc.) — not dashboard-worthy.

**`projects/<proj>/<session>/workflows/wf_<id>.json`** (elided):
```json
{
  "runId": "wf_<id>", "timestamp": "iso", "taskId": "<id>",
  "script": "<elided-str>", "scriptPath": "<elided-str>",
  "result": {"...": "workflow-specific arbitrary JSON payload"},
  "agentCount": 6, "logs": [], "durationMs": 637029,
  "summary": "<elided-str>", "workflowName": "reconcile-token-gap",
  "status": "completed", "startTime": 0,
  "phases": [{"title": "Ground-truth", "detail": "<elided-str>"}],
  "defaultModel": "claude-opus-4-8[1m]",
  "workflowProgress": [{"type": "workflow_phase", "index": 1, "title": "Ground-truth"}],
  "totalTokens": 264769, "totalToolCalls": 51
}
```

**`todos/<session>-agent-<agent>.json`**: `[{"content": "<elided>", "status": "pending|in_progress|completed", "activeForm": "<elided>"}]` (both sampled files were `[]`).

**`~/.claudecode/settings.json`**: 0 bytes — empty/vestigial file, directory appears unused (single file, last touched Mar 18).

### Dashboard candidates
Ranked by (user value × ease of extraction):
1. **Background jobs table** (jobs/, cross-referenced with daemon/roster.json + sessions/*.json for live ones): id, name, state, template (claude/bg), tokens, created/updated, linked PR/issue children, cwd. High value — directly answers "what has my fleet of background agents been doing." Easy: just `state.json` per dir, 48 rows.
2. **Subscription usage/quota panel** (`~/.claude.json.cachedUsageUtilization`): 5-hour and 7-day utilization %, reset times. High value, trivial extraction (single cached object), and is the exact "usage/quota/rate-limit state" the brief asks every harness to have an equivalent of.
3. **Workflows panel** (`projects/**/workflows/wf_*.json`, 512 runs across 40 sessions): name, status, phases, agentCount, totalTokens, totalToolCalls, durationMs. Distinct from ordinary Task-tool subagent delegation (which is already covered) — this is a named, phased, scriptable orchestration feature. Medium-high value, moderate extraction (glob + json load, no transcript parsing needed).
4. **Feature-usage / adoption strip** (`skillUsage`, `pluginUsage`, `agentLastUsed` in `~/.claude.json`): top skills/plugins by usageCount and lastUsedAt. Easy extraction, decent "what am I actually using" value.
5. **Checkpoint/rewind coverage indicator** (`file-history/<session>/`): count of snapshots and distinct files touched per session, as a proxy for "how much this session edited/rewound." Medium value, easy count-only extraction (don't need to read blob contents — file names alone give hash@version counts per session dir).
6. **Precomputed stats cross-check** (`stats-cache.json`): use as a fast validation source against TT's own transcript-derived totals (totalSessions/totalMessages/modelUsage) — not new user-facing data, but a free correctness check per the "verify before reporting" house rule.
7. **Live daemon/process panel** (`sessions/*.json`, `daemon/roster.json`, `daemon.status.json`): "N Claude Code processes currently running," cwd, idle/spare status. Novelty value only (transient), lower priority.
8. Low priority / skip: telemetry/1p_failed_events (Anthropic-internal), statsig/ (Anthropic-internal), gh-pr-status-cache.json (repo-specific gh cache), paste-cache/debug/session-env (plumbing, some privacy-sensitive).

### Cross-harness parallels
- **Background jobs**: `jobs/<id>/state.json` + `daemon/roster.json` (live) — richest of any harness surveyed so far; has explicit state machine (done/blocked/working/stopped), linked PR/issue children, and fan-out task tracking.
- **Schedules/cron**: only a watermark (`routineFiredWatermark`) — actual "Routines" (the `/schedule` skill's cloud cron) definitions are NOT stored locally; they live server-side on claude.ai. Nothing to mine beyond the watermark.
- **Memory**: no dedicated local memory store analogous to Hermes' MEMORY.md/SOUL.md at the ~/.claude root; the closest per-project analog is CLAUDE.md (covered) and the auto-memory files under `~/.claude/projects/.../memory/MEMORY.md` referenced in the system context (project-scoped, not harness-global).
- **Todos**: `todos/<session>-agent-<agent>.json` — TodoWrite tool state, ephemeral, resets to `[]` on completion.
- **Checkpoints/rewind**: `file-history/<session>/<hash>@v<N>` — genuine checkpoint store, no manifest found mapping hash back to file path within the dir itself.
- **Plan artifacts**: not found as a distinct store; ExitPlanMode plans live inline in the transcript (covered).
- **MCP + tools inventory**: `~/.claude.json` → `projects.<path>.{mcpServers, enabledMcpjsonServers, disabledMcpjsonServers, allowedTools}` — covered via existing settings/.mcp.json parsing, but this per-project cache is a secondary source of the same facts plus enable/disable state.
- **Usage/quota/rate-limit state**: `~/.claude.json.cachedUsageUtilization` — five_hour/seven_day utilization % and reset timestamps. This is the standout NEW find matching this exact ask.
- **Permissions/config**: `settings.json` (global, no hooks here) + per-project `allowedTools`/trust flags in `~/.claude.json`.
- **Subagents**: `projects/<proj>/<session>/subagents/workflows/wf_<id>/agent-<hash>.{jsonl,meta.json}` — same shape as the existing `/sessions/{id}/subagents/{aid}/trace` endpoint (covered), but now also reachable/groupable via the parent `wf_<id>.json` workflow record.
- **Hooks**: none at `~/.claude` root; hook scripts and settings live in per-project `.claude/settings.json` / `.claude/hooks/` (project-local, already how this repo's own hooks work).
- **Model config**: `settings.json.model/effortLevel`, `~/.claude.json.modelAccessCache/orgModelDefaultCache/additionalModelCostsCache`.
- **Worktrees**: none at `~/.claude` root — worktrees live under each project's own `<repo>/.claude/worktrees/` (this survey itself runs from one: `.../tokentelemetry/.claude/worktrees/harness-data-survey`).
- **IDE integration**: `~/.claude/ide/` is empty (0B) at survey time; `chrome/chrome-native-host` is the claude-in-chrome extension's native-messaging host.
- **Sandbox/remote environment state**: `bridge-pointer.json` (rare, 1/51 projects) + `bridgeSessionId`/`bridgeOwnerAccountUuid` fields inside job `state.json` — points at claude.ai cloud "environments" bridging local sessions.

### Gotchas
- `jobs/` is 3.3G but ~2.9G of that is disposable `tmp/` scratch (git clones, node_modules-like dirs, logs) inside just two job dirs — do not treat job dir size as data volume; only `state.json` + `timeline.jsonl` are durable/structured.
- Session sidecar dirs under `projects/<proj>/<session-uuid>/` (workflows, subagents) only exist for sessions that used the Workflows feature or spawned Task-tool subagents — most session UUIDs have only the `.jsonl` transcript and no sidecar dir. A scanner must `os.path.isdir` check per session rather than assuming the sidecar exists.
- `sessions/*.key` and `daemon/{control.key,rvAuth,ptyAuth}` are auth/handshake secrets for the local daemon's Unix-socket protocol — never read or surface these; filenames matching `*.key` were deliberately not opened during this survey.
- `~/.claude.json` also has a rotating backup family at `~/.claude/backups/.claude.json.backup.<epoch-ms>` (separate from the single `~/.claude.json.backup` in $HOME) — five were seen accumulated within one minute of activity, suggesting frequent-write backup churn; not useful as a data source, just a durability mechanism.
- `~/.claudecode/` (note: no dot before "code", different from `~/.claude`) contains only a 0-byte `settings.json` — this looks like a stale/decoy directory from an old install path; do not confuse with `~/.claude`.
- `file-history/` snapshot files carry no extension and `file` reports them generically (e.g. "CSV text") based on content sniffing — a scanner should treat them as opaque blobs keyed by `<hash>@v<N>`, not try to parse by extension.
- `stats-cache.json`'s `modelUsage.costUSD` was `0` for the sampled model — Claude Code's own cost cache does not appear to populate cost the way TT's own pricing pipeline does; don't treat this field as authoritative cost.
- Workflow run files (`wf_*.json`) embed an arbitrary, workflow-defined `result` object (schema varies per `workflowName`) — treat as opaque/passthrough JSON in the dashboard rather than trying to normalize its shape.
- `history.jsonl` is genuinely global (spans every project this machine has used Claude Code in, keyed per-line by `project`), not per-project — if surfaced, must be filtered by the `project` field to scope to one harness/project view.
