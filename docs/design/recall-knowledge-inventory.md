# Recall knowledge inventory

Where each supported agent keeps the material the project index embeds:
skills, commands, agent definitions, artifacts and plans, images, instruction
and memory Markdown, and MCP server configuration. Source code is out of scope.

Built from three sources per agent: TokenTelemetry's existing scanners, the
agent's own documentation (Nov 2026), and read-only inspection of a real machine.
`Verified` says which. Rows marked **unverified** are checked live by the indexer
(missing paths are skipped and counted, never fatal).

Paths use `~` for the home directory and `<project>` for the project root.

## Rules that apply to every agent

- **Project link.** A project-scope item belongs to the project whose root
  contains it. A user-scope item (global skill, agent, command, MCP server) is
  indexed for a project only if a session in that project used it (tool name,
  skill name, `subagent_type`, slash command, `mcp__<server>__` tool), which
  TokenTelemetry already records per session.
- **MCP config.** Index server name, transport, command and tool names only.
  Never index values of `env`, `headers`, token-bearing `args`, or URL query
  strings.
- **Images.** Inline base64 image blocks in transcripts and image files an agent
  saved (screenshots, generated media) are embedded as images. They cannot be
  redacted, so image indexing has its own switch.
- **Never index** (credentials or raw pasted/snapshotted file contents):
  `~/.claude/.credentials.json`, `~/.claude/paste-cache/`, `~/.claude/file-history/`,
  `~/.codex/auth.json`, `~/.codex/history.jsonl`, Gemini `oauth_creds.json` and
  `tmp/<hash>/shell_history`, `*.orig` / backup settings files (for example
  `~/.qwen/settings.json.orig`), any `auth*.json`, `providers.json`,
  `credentials*`, `.env*`, and agent extension code (TypeScript/JS plugins are
  code, not definitions).
- **Legacy.** Gemini CLI was discontinued on 2026-06-18 (Antigravity replaced it);
  its data is still indexed for history but no new layout work is planned.

## Per agent

### Claude Code

| What | Scope | Path | Format | Secrets | Project link | Verified |
|---|---|---|---|---|---|---|
| Skills | project | `<project>/.claude/skills/<name>/SKILL.md` | Markdown with YAML frontmatter | none | Path is inside the project. | disk |
| Skills | user | `~/.claude/skills/<name>/SKILL.md (+ references/ etc); also plugin skills under ~/.claude/plugins/{cache,marketplaces}/**/skills/<name>/SKILL.md` | Markdown with YAML frontmatter (name, description, optional allowed-tools) | none | User skills are global. Tie to a project by session transcripts in ~/.claude/projects/<slug>/ containing a Skill tool_use with that name, or by the skill listing in the session. Plugin skills: install | disk |
| Commands / prompts | project | `<project>/.claude/commands/**/*.md (subdir becomes namespace)` | Markdown, optional frontmatter (description, argument-hint, allowed-tools, model) | none | Path inside project. | docs |
| Commands / prompts | user | `~/.claude/commands/**/*.md; plugin commands in ~/.claude/plugins/**/commands/*.md` | Markdown with optional frontmatter | none | Global; link via transcripts that contain a <\command-name> block or slash-command user message in the project's session. | docs |
| Agent definitions | project | `<project>/.claude/agents/*.md` | Markdown with YAML frontmatter | none | Path inside project. | disk |
| Agent definitions | user | `~/.claude/agents/*.md; plugin agents in ~/.claude/plugins/**/agents/*.md` | Markdown with YAML frontmatter (name, description, tools, model) | none | Global. Tie via Task/Agent tool_use blocks (subagent_type) in the project's session jsonl and subagent sidechain files under ~/.claude/projects/<slug>/<session-id>/subagents/ (subagents dir layout unv | disk |
| Artifacts & plans | project | `<project>/.claude/plans/ (only if plansDirectory is set); <project>/docs, DESIGN.md etc. are ordinary repo files` | Markdown | none | Path inside project. | **unverified** |
| Artifacts & plans | user | `~/.claude/plans/*.md (plan mode default, overridable with plansDirectory setting); ~/.claude/tasks/<session-uuid>/ (task list state); ~/.claude/jobs, ~/.claude/scheduled-tasks` | Plan: Markdown with random-word filenames. Tasks: per-session directories (contents not inspected). | none | tasks/<uuid> matches the session id of ~/.claude/projects/<slug>/<uuid>.jsonl, which gives the project. Plans have no project key; link via the ExitPlanMode tool_use in a project session transcript (a | docs |
| Images | user | `Inline in ~/.claude/projects/<slug>/<session-id>.jsonl as user message content blocks {type:'image', source:{type:'base64', media_type, data}}; pasted text spills to ~/.claude/paste-cache/<hash>.txt; ~/.claude/file-history/<session-id>/ holds file snapshots; ~/.claude/uploads` | Base64 inside JSON lines; pasted images may also be referenced as '[Image #N]' text in the prompt | none | The containing jsonl lives in the project's slug dir (slug = project path with / and . replaced by -). Each line also carries cwd. | **unverified** |
| Instruction .md | project | `<project>/CLAUDE.md, <project>/.claude/CLAUDE.md, <project>/CLAUDE.local.md, <project>/.claude/rules/*.md, nested <subdir>/CLAUDE.md; @imports inside files` | Markdown | none | Path inside project. | disk |
| Instruction .md | user | `~/.claude/CLAUDE.md, ~/.claude/rules/*.md` | Markdown | none | Global; applies to every project (loaded into every session). | disk |
| Memory | project | `~/.claude/projects/<slug>/memory/MEMORY.md plus topic *.md files (auto memory, keyed by project path slug)` | Markdown with frontmatter per memory file, MEMORY.md as index | none | Slug of the dir is the project path (slashes and dots become '-'); git worktrees of the same repo may share or have separate slugs (unverified). | disk |
| MCP config | project | `<project>/.mcp.json (team-shared) and per-project entries in ~/.claude.json under projects[<abs project path>].mcpServers (local scope); enabledMcpjsonServers/disabledMcpjsonServers lists` | JSON. Per server: type, command, args, env, url, headers (headersHelper) | env (values: API tokens), headers (Authorization etc.), args (tokens passed as flags), url (query string tokens such as ?key=). Index key na | Key of projects{} in ~/.claude.json is the absolute project path; .mcp.json is inside project. | disk |
| MCP config | user | `~/.claude.json top-level mcpServers (user scope); plugin MCP in ~/.claude/plugins/**/.mcp.json; ~/.claude/settings.json may hold enabledPlugins` | JSON | env, headers, args, url query string | Global. Tie via mcp__<server>__ tool_use names in the project's sessions. | disk |

Not supported by this agent: Standalone user-level generated-image store (Claude Code does not generate images; only pasted inline images in transcripts), Dedicated artifacts store: published Artifacts live on claude.ai, not locally.

Notes: TT code: main.py CLAUDE_DIR = ~/.claude (line 558); agent_retention.py reads ~/.claude/settings.json cleanupPeriodDays; quotas.py reads ~/.claude/.credentials.json (secret, do not index); history_store.py notes ~/.claude/projects is pruned after cleanupPeriodDays (default 30), so the index should snapshot. Official docs were not fetched live (no web search run); doc-based entries come from model knowledge and are marked accordingly.

### Codex

| What | Scope | Path | Format | Secrets | Project link | Verified |
|---|---|---|---|---|---|---|
| Skills | project | `<project>/.agents/skills/<name>/SKILL.md (documented repo scan location, cwd up to repo root)` | Markdown with YAML frontmatter | none | Path inside project. | docs |
| Skills | user | `~/.codex/skills/<name>/SKILL.md (plus references/); plugin skills under ~/.codex/plugins/cache/**` | Markdown with YAML frontmatter (name, description) | none | Global. Tie via session rollout (~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl, session_meta carries cwd) that reads or invokes the skill. | disk |
| Commands / prompts | user | `~/.codex/prompts/*.md (custom prompts, deprecated in favor of skills)` | Markdown with optional frontmatter (description, argument-hint) | none | Global; no project-level custom prompts exist. | docs |
| Agent definitions | user | `~/.codex/agents/*.toml (custom agents/subagents) and [agents] table in config.toml` | TOML | none | Global; project-level <project>/.codex/agents/ may exist (unverified). | **unverified** |
| Artifacts & plans | user | `~/.codex/automations/<name>/ (scheduled automations, e.g. hourly-threads-ai-news-posting); ~/.codex/visualizations/; ~/.codex/goals_1.sqlite; plan items appear in rollout as update_plan function_call` | Automations: dir (contents not inspected). goals: SQLite. | none | Automations may name a cwd in their config (unverified); goals/threads keyed by thread id, join to state_5.sqlite threads.cwd. | disk |
| Images | user | `~/.codex/generated_images/<id>/ (images the agent generated); ~/.codex/attachments/<uuid>/ plus pasted-text-attachments.json; user images inline in rollout as input_image content items (data URL base64) or file refs` | Image files; JSON transcript refs. Rollout content types seen on sample: 'message' payloads with content blocks. | none | Attachment/generated-image uuid maps to a thread/session id; thread cwd is in state_5.sqlite threads table or rollout session_meta.payload.cwd. | **unverified** |
| Instruction .md | project | `<project>/AGENTS.md, <project>/AGENTS.override.md, nested <subdir>/AGENTS.md` | Markdown | none | Path inside project. | disk |
| Instruction .md | user | `~/.codex/AGENTS.md (and AGENTS.override.md); ~/.codex/instructions.md (legacy)` | Markdown | none | Global. | disk |
| Memory | user | `~/.codex/memories/ (markdown memory files); ~/.codex/memories_1.sqlite` | Markdown files plus SQLite | none | Possibly keyed by thread/cwd inside the SQLite (unverified). | disk |
| MCP config | user | `~/.codex/config.toml: [mcp_servers.<name>] (docs spelling). This machine's file shows [mcpServers.github] and [mcpServers.github.env]` | TOML. Per server: command, args, env table, url, bearer_token_env_var, http_headers, env_http_headers, enabled | [...env] table values, http_headers values, args tokens, url query string, inline bearer_token. bearer_token_env_var holds only a variable n | Global config. Project trust is keyed by [projects."<abs path>"] tables in the same file (trust_level); project-scoped <project>/.codex/config.toml also supported (documented, absent in TT repo). | disk |

Not supported by this agent: Project-level skills dir not present on disk (only documented as .agents/skills), User custom prompts/commands: ~/.codex/prompts absent here, deprecated upstream, Dedicated plan-file store: plans live only as update_plan calls in rollouts.

Notes: TT code: main.py CODEX_DIR = ~/.codex; billing_mode.py and quotas.py read ~/.codex/auth.json (secret). Sessions: ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl; history.jsonl keys: session_id, ts, text; session_index.jsonl maps thread id to thread_name. ~/.codex/rules/default.rules holds allow-list command prefix rules (user may have pasted commands with secrets in them, so exclude from indexing). Official docs were not fetched live.

### Gemini CLI

| What | Scope | Path | Format | Secrets | Project link | Verified |
|---|---|---|---|---|---|---|
| Skills | project | `<project>/.gemini/skills/<name>/SKILL.md (also .agents/skills alias per docs)` | Markdown with YAML frontmatter | none | Path inside project. | docs |
| Skills | user | `~/.gemini/skills/<name>/SKILL.md; extension skills under ~/.gemini/extensions/<ext>/skills/` | Markdown with YAML frontmatter | none | Global; link via session in ~/.gemini/tmp/<hash>/chats that activated the skill. | disk |
| Commands / prompts | project | `<project>/.gemini/commands/**/*.toml` | TOML | none | Path inside project. | docs |
| Commands / prompts | user | `~/.gemini/commands/**/*.toml (subdir gives namespace, e.g. git/commit.toml -> /git:commit)` | TOML with prompt and description fields | none | Global. | docs |
| Agent definitions | project | `<project>/.gemini/agents/*.md and ~/.gemini/agents/*.md (subagents, experimental)` | Markdown with frontmatter (name, description, tools, model) | none | Project path inside project; user level global. | **unverified** |
| Artifacts & plans | project | `~/.gemini/tmp/<project-hash>/ (chats/session-*.json, logs.json, shell_history, plans/ in recent versions)` | Session JSON; logs.json; plans (plan mode) as markdown if enabled | none | Compute sha256(project abs path) to find tmp dir, or use ~/.gemini/projects.json (path -> name). Session JSON also stores projectHash. | disk |
| Images | user | `Inline in chats/session-*.json message parts as inlineData {mimeType, data(base64)} or @file references; clipboard images saved by CLI under ~/.gemini/tmp/<hash>/images/ (unverified)` | JSON with base64 parts | none | Via tmp/<hash> directory. | **unverified** |
| Instruction .md | project | `<project>/GEMINI.md and nested <subdir>/GEMINI.md (context.fileName in settings can add AGENTS.md)` | Markdown, @import syntax | none | Path inside project. | docs |
| Instruction .md | user | `~/.gemini/GEMINI.md` | Markdown | none | Global. | disk |
| Memory | user | `~/.gemini/GEMINI.md under '## Gemini Added Memories' (written by save_memory tool)` | Markdown bullets inside GEMINI.md | none | Global only. | docs |
| MCP config | user | `~/.gemini/settings.json -> mcpServers.<name>; also project <project>/.gemini/settings.json; extension gemini-extension.json mcpServers` | JSON. Per server: command, args, env, cwd, url, httpUrl, headers, timeout, trust, includeTools, excludeTools | env values, headers values, args tokens, url/httpUrl query strings. ~/.gemini/oauth_creds.json, google_accounts.json, jetski-standalone-oaut | Project settings file inside <project>/.gemini; user file is global. | disk |

Not supported by this agent: Local plan/artifact files outside tmp/<hash> (plan mode support depends on version, unverified), Native generated-image store (Gemini CLI text-only; images only as inline input), Gemini CLI is discontinued 2026-06-18 per project memory; treat as legacy, data frozen.

Notes: TT code: main.py GEMINI_DIR = ~/.gemini; billing_mode.py checks oauth_creds.json; quotas.py refreshes the token (secret). Retention hint in agent_retention.py: ~/.gemini/settings.json chat history maxAge. Official docs not fetched live; shared dir ~/.gemini also hosts antigravity*, so filter by subdir.

### Antigravity

| What | Scope | Path | Format | Secrets | Project link | Verified |
|---|---|---|---|---|---|---|
| Skills | project | `<project>/.agents/skills/<name>/SKILL.md or <project>/.agent/skills/ (workspace skills, per Antigravity docs)` | Markdown with YAML frontmatter | none | Path inside project. | **unverified** |
| Skills | user | `~/.gemini/antigravity/skills/<name>/SKILL.md and ~/.gemini/antigravity-cli/skills/<name>/SKILL.md` | Markdown with YAML frontmatter | none | Global; tie via conversation transcript referencing the skill. | disk |
| Commands / prompts | user | `Workflows: <project>/.agents/workflows/*.md (slash-invoked), ~/.gemini/antigravity/global_workflows/ (per docs recall)` | Markdown | none | Project path inside project. | **unverified** |
| Artifacts & plans | user | `~/.gemini/antigravity/brain/<conversation-uuid>/ ; ~/.gemini/antigravity-cli/brain/<uuid>/ ; ~/.gemini/antigravity-ide/brain/<uuid>/ (antigravity-backup mirrors, exclude)` | Per-conversation dir with implementation_plan.md, task.md, walkthrough.md (names vary), each with .metadata.json {artifactType: ARTIFACT_TYPE_TASK\|..., summary | none | Dir name = conversation uuid. Project/cwd comes from conversations/<uuid>.db via _antigravity_db_meta / _antigravity_cli_meta (main.py ~1345, ~1694) or heuristic _antigravity_infer_project from file p | disk |
| Images | user | `~/.gemini/antigravity*/brain/<uuid>/*.png\|*.webp (screenshots, previews, agent-captured); ~/.gemini/antigravity/browser_recordings/<uuid>/ (browser sub-agent recordings); html_artifacts/ (empty here)` | Image files directly in the brain dir (e.g. ep03_hook_scene_<ts>.png, .webp), recordings dir | none | Same uuid-to-project mapping as brain/. Transcript references them as file paths in artifact markdown. | disk |
| Instruction .md | project | `<project>/.agents/rules/*.md or <project>/.agent/rules/*.md, <project>/AGENTS.md, <project>/GEMINI.md` | Markdown | none | Path inside project. | **unverified** |
| Instruction .md | user | `~/.gemini/GEMINI.md (shared global rules with Gemini CLI)` | Markdown | none | Global. | **unverified** |
| Memory | user | `~/.gemini/antigravity/knowledge/ and ~/.gemini/antigravity-cli/knowledge/ (Knowledge Items); ~/.gemini/antigravity/conversation_summaries.db; implicit/ ; context_state/` | Knowledge items as dirs of markdown plus metadata (shape not inspected); summaries in SQLite | none | Knowledge items cite source conversation ids; conversation uuid then maps to project. | **unverified** |
| MCP config | user | `~/.gemini/antigravity/mcp_config.json (app/IDE); ~/.gemini/antigravity-cli/mcp/ and settings.json for CLI (dir exists, contents not inspected)` | JSON {mcpServers:{name:{command,args,env,disabled,serverUrl/url,headers}}} | env values, headers, args tokens, url/serverUrl query string. Also mcp_config.json.bak duplicate (skip). jetski-standalone-oauth-token, oaut | Global per surface. antigravity-cli/settings.json trustedWorkspaces lists project paths (trust only, not MCP). | disk |

Not supported by this agent: Subagent definition files: child agents are spawned by parent via INVOKE_SUBAGENT steps (main.py ~6978), no definition files found, Project-level artifacts: all plans/tasks live in the user-level brain/, never in the repo, Separate memory markdown files (knowledge dir empty or unverified).

Notes: TT code: main.py ANTIGRAVITY_BRAIN_DIR, ANTIGRAVITY_CLI_DIR, _antigravity_cli_meta, _antigravity_db_meta (project cwd from conversations/<uuid>.db), antigravity_usage.conversation_files (excludes antigravity-backup), _antigravity_goal_detect (transcript goals). Conversations are SQLite at antigravity*/conversations/<uuid>.db (newer) or protobuf (older). There is also ~/.gemini/antigravity-browser-profile (browser cookies, never index) and ~/.antigravity (editor extensions, argv.json). ~/.antigravity-cli is empty. Official docs not fetched live.

### Cursor

| What | Scope | Path | Format | Secrets | Project link | Verified |
|---|---|---|---|---|---|---|
| Skills | project | `<project>/.cursor/skills/<name>/SKILL.md ; <project>/.cursor/skills-cursor/<name>/SKILL.md` | Markdown + YAML frontmatter | none | Inside the repo, so already project-bound. | TT code |
| Skills | user | `~/.cursor/skills/<name>/SKILL.md ; ~/.cursor/skills-cursor/<name>/SKILL.md (built-in/managed set)` | Markdown + YAML frontmatter (name, description) | none | Project copy at <project>/.cursor/skills/ and <project>/.cursor/skills-cursor/ (TT reads only the latter). Cursor also reads .claude/skills and .agents/skills per docs (unverified). For user-level ski | disk |
| Commands / prompts | project | `<project>/.cursor/commands/*.md` | Plain Markdown prompt files; no frontmatter required | none | Project-level only; user-level ~/.cursor/commands is the analog, tie by session cwd. | **unverified** |
| Agent definitions | user | `~/.cursor/agents/*.md ; <project>/.cursor/agents/*.md` | Markdown + YAML frontmatter (name, description, model, readonly...) | none | Project dir is bound; user dir tie by session cwd. | TT code |
| Artifacts & plans | user | `~/.cursor/projects/<slug-or-ts>/canvases/ ; ~/.cursor/projects/<slug>/terminals/*.txt ; ~/.cursor/projects/<slug>/agent-transcripts/<sid>/` | canvases dir (empty here), terminal captures as .txt, transcripts JSONL | none | ~/.cursor/projects/<slug> is a per-workspace key (slugged path, or a timestamp id for unsaved windows). Map slug back to cwd via TT's project resolver in main.py. | disk |
| Images | user | `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb and workspaceStorage/<hash>/state.vscdb (platform base CURSOR_BASE: ~/.config/Cursor on Linux, %APPDATA%\Cursor on Windows)` | SQLite key-value (cursorDiskKV/ItemTable); pasted images appear as bubble fields/blobs inside JSON values | none | workspaceStorage/<hash>/workspace.json holds the folder URI for the hash. | **unverified** |
| Instruction .md | project | `<project>/.cursor/rules/*.mdc ; <project>/.cursorrules (legacy) ; <project>/AGENTS.md (root and nested)` | MDC: YAML frontmatter (description, globs, alwaysApply) + Markdown | none | Inside repo. User rules live in Cursor settings (sqlite state), not a file. | TT code |
| Memory | user | `none as files` | n/a | none | n/a | **unverified** |
| MCP config | user | `~/.cursor/mcp.json ; <project>/.cursor/mcp.json` | JSON {mcpServers:{<name>:{command,args,env \| url,headers}}} | env (values), headers (values e.g. Authorization), args (inline tokens), url query strings; also remote 'url' for oauth servers may embed ke | Project file is repo-bound; user file applies to all projects. | TT code |

Not supported by this agent: memory as files (app-state only), dedicated generated-images dir not found.

Notes: Cursor has no token usage data per prior knowledge. ~/.cursor/plugins/{cache,local} exists (plugin bundles); not inspected. Docs sources: cursor.com/docs/rules, cursor.com/docs/skills.

### GitHub Copilot (VS Code chat + Copilot CLI)

| What | Scope | Path | Format | Secrets | Project link | Verified |
|---|---|---|---|---|---|---|
| Skills | project | `<project>/.github/skills/<name>/SKILL.md ; <project>/.claude/skills/ ; <project>/.agents/skills/` | Markdown + YAML frontmatter | none | Repo-bound. | docs |
| Skills | user | `~/.copilot/skills/<name>/SKILL.md ; ~/.agents/skills/<name>/SKILL.md` | Markdown + YAML frontmatter | none | Project copies: <project>/.github/skills, .claude/skills, .agents/skills. User skills tie to a project via CLI sessions whose workspace.yaml cwd is the project. | disk |
| Commands / prompts | project | `<project>/.github/prompts/*.prompt.md (VS Code user prompts: ~/Library/Application Support/Code/User/prompts/*.prompt.md)` | Markdown + YAML frontmatter (description, mode/agent, tools) | none | Repo-bound for project files. | docs |
| Agent definitions | project | `<project>/.github/agents/<name>.md (also *.agent.md in VS Code); user: VS Code user profile prompts dir` | Markdown + YAML frontmatter (description, tools, model) | none | Repo-bound for project files. | docs |
| Artifacts & plans | user | `~/.copilot/session-state/<session-uuid>/{workspace.yaml,events.jsonl,checkpoints/index.md,files/,research/}` | workspace.yaml (cwd etc), JSONL events, Markdown checkpoints, free-form files/ and research/ dirs (empty in the sample) | none | workspace.yaml records the working dir; TT derives project via parsed['project_path'] (main.py ~9494). | disk |
| Artifacts & plans | user | `~/.copilot/session-store.db ; ~/.copilot/data.db ; ~/.copilot/repo-metadata-cache.db` | SQLite | none | session-store likely carries cwd/repo per session; verify schema. | **unverified** |
| Images | user | `~/.copilot/media-cache/ ; VS Code chat: ~/Library/Application Support/Code/User/workspaceStorage/<hash>/chatSessions/*.json and chatEditingSessions` | media-cache dir (empty here); VS Code chatSessions JSON may reference attached images as variables/blobs | none | workspaceStorage/<hash>/workspace.json maps hash to folder. | **unverified** |
| Instruction .md | project | `<project>/.github/copilot-instructions.md ; <project>/.github/instructions/*.instructions.md ; <project>/AGENTS.md` | Markdown; .instructions.md has YAML frontmatter applyTo glob | none | Repo-bound. | TT code |
| Instruction .md | user | `~/.copilot/copilot-instructions.md` | Markdown | none | Tie via session cwd. | **unverified** |
| Memory | user | `none confirmed` | n/a | none | n/a | **unverified** |
| MCP config | user | `~/.copilot/mcp-config.json (CLI) ; <project>/.vscode/mcp.json and VS Code user mcp.json (VS Code) ; <project>/.mcp.json` | CLI: JSON {mcpServers:{<name>:{type,command,args,env,tools}}}. VS Code: {servers:{...}, inputs:[...]} | env values, headers values, args (tokens or user path segments), url query strings; VS Code 'inputs' prompt for secrets but defaults may be  | <project>/.vscode/mcp.json is repo-bound; CLI user file is global. | disk |

Not supported by this agent: local memory files (server-side only, unverified).

Notes: Also in ~/.copilot: config.json (not valid JSON on this machine, may hold auth, never index), settings.json (experimental flag), installed-plugins/ (empty), extensions/ (empty). Never index ~/.config/github-copilot/apps.json or hosts.json (OAuth tokens, read by quotas.py). TT sources: main.py COPILOT_CLI_DIR, VSCODE_BASE.

### Cline

| What | Scope | Path | Format | Secrets | Project link | Verified |
|---|---|---|---|---|---|---|
| Skills | user | `~/.cline/skills/<name>/SKILL.md ; project: <project>/.cline/skills/<name>/SKILL.md, also .clinerules/skills/ and .claude/skills/` | Markdown + YAML frontmatter | none | Project dirs are repo-bound; user tie by session cwd. | docs |
| Commands / prompts | project | `<project>/.clinerules/workflows/*.md ; ~/Documents/Cline/Workflows/` | Markdown, invoked as /name.md | none | Repo-bound for project. | **unverified** |
| Agent definitions | user | `none confirmed` | n/a | none | n/a | **unverified** |
| Artifacts & plans | user | `~/.cline/data/sessions/<ts_id>/ and ~/.cline/data/db/sessions.db (CLI); VS Code ext: ~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/tasks/<id>/{api_conversation_history.json,ui_messages.json}` | CLI: per-session dirs plus SQLite; extension: JSON files | none | Session row/metadata carries cwd; TT scanner resolves project from it. | TT code |
| Images | user | `Extension api_conversation_history.json content blocks type:'image' with source.base64; ui_messages.json 'images' arrays of data URIs` | base64 inline in JSON | none | Per-task, inherits the task's cwd. | **unverified** |
| Instruction .md | project | `<project>/.clinerules (file) or <project>/.clinerules/*.md\|*.txt ; <project>/AGENTS.md` | Markdown/text | none | Repo-bound. | docs |
| Instruction .md | user | `~/Documents/Cline/Rules/ (VS Code extension global rules)` | Markdown | none | Tie by session cwd. | **unverified** |
| Memory | project | `<project>/memory-bank/*.md (convention, not built-in)` | Markdown | none | Repo-bound. | **unverified** |
| MCP config | user | `~/.cline/data/settings/cline_mcp_settings.json (override env CLINE_MCP_SETTINGS_PATH); extension: globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json; project: <project>/.cline/mcp.json (one source)` | JSON {mcpServers:{<name>:{command,args,env \| url,headers,disabled,autoApprove}}} | env, headers, args, url query. Also ~/.cline/data/settings/providers.json holds API keys: never index. | User file is global; project file repo-bound. | docs |

Not supported by this agent: custom agent definition files (unverified), built-in memory.

Notes: ~/.cline/data/db/{sessions,teams,cron}.db are SQLite; cron specs read by _cline_loop_specs. Treat providers.json as secret.

### Qwen Code CLI

| What | Scope | Path | Format | Secrets | Project link | Verified |
|---|---|---|---|---|---|---|
| Skills | user | `~/.qwen/skills/<name>/SKILL.md ; <project>/.qwen/skills/<name>/SKILL.md` | Markdown + YAML frontmatter | none | Project copy repo-bound; user skills tie via session cwd under ~/.qwen/projects/<slug>. | TT code |
| Commands / prompts | user | `~/.qwen/commands/*.toml ; <project>/.qwen/commands/*.toml (subdirs make namespaced commands)` | TOML (prompt, description), Gemini-CLI lineage | none | Repo-bound for project. | **unverified** |
| Agent definitions | user | `~/.qwen/agents/*.md ; <project>/.qwen/agents/*.md` | Markdown + YAML frontmatter | none | Repo-bound for project. | **unverified** |
| Artifacts & plans | user | `~/.qwen/todos/ ; ~/.qwen/projects/<slugged-cwd>/chats/<uuid>.jsonl ; ~/.qwen/tmp/` | JSON todo files; JSONL chats | none | Slug is the cwd with separators replaced by dashes; reverse it (ambiguous when dirs contain dashes, so also read cwd from the JSONL records). | disk |
| Images | user | `inside ~/.qwen/projects/<slug>/chats/*.jsonl` | Gemini-style parts: inlineData{mimeType,data base64} or fileData | none | Per chat file, slug gives project. | **unverified** |
| Instruction .md | project | `<project>/QWEN.md (root and nested) ; ~/.qwen/QWEN.md (user) ; AGENTS.md possibly` | Markdown | none | Repo-bound. | docs |
| MCP config | user | `~/.qwen/settings.json (mcpServers) ; <project>/.qwen/settings.json ; extension qwen-extension.json` | JSON mcpServers:{<name>:{command,args,env,cwd \| url \| httpUrl,headers,timeout,includeTools,excludeTools}} | env values, headers values, args, url/httpUrl query strings. ~/.qwen/oauth_creds.json is a credential: never index. | Project settings file repo-bound. | docs |

Not supported by this agent: memory files separate from QWEN.md (unverified).

Notes: ~/.qwen/settings.json.orig is a backup, also may contain config. billing_mode.py reads ~/.qwen OAuth dir presence only.

### Kimi Code

| What | Scope | Path | Format | Secrets | Project link | Verified |
|---|---|---|---|---|---|---|
| Skills | user | `~/.agents/skills/<name>/SKILL.md ; ~/.kimi-code/skills/ (third-party report) ; project .agents/skills or .kimi-code/skills` | Markdown + YAML frontmatter; invoked /skill:<name> | none | Project dirs repo-bound; user tie by session work_dir. | docs |
| Commands / prompts | user | `Plugin commands: <plugin>/commands/*.md` | Markdown | none | Plugin-installed, global. | docs |
| Agent definitions | user | `Markdown agent files discovered by scope (recursive .md scan); explicit --agent-file highest priority` | Markdown with YAML frontmatter (sub-agent profiles) | none | Project scope repo-bound. | **unverified** |
| Artifacts & plans | user | `~/.kimi/sessions/<md5(work_dir)>/<session-uuid>.jsonl ; ~/.kimi/user-history/ ; ~/.kimi/logs/` | JSONL per session | none | Bucket dir is md5 of work_dir; ~/.kimi/kimi.json work_dirs entries have keys path, kaos, last_session_id (forward-hash the project path rather than trust last_session_id). | TT code |
| Images | user | `inside session JSONL` | not inspected (no local session files matched in my probe) | none | Session bucket md5(work_dir). | **unverified** |
| Instruction .md | project | `<project>/AGENTS.md ; <project>/.kimi-code/AGENTS.md ; user: $KIMI_CODE_HOME/AGENTS.md (~/.kimi-code/AGENTS.md) and ~/.agents/AGENTS.md` | Markdown; /init generates it | none | Repo-bound for project. | docs |
| MCP config | user | `~/.kimi-code/mcp.json ; <project>/.kimi-code/mcp.json ; <project>/.mcp.json (third-party) ; on this machine ~/.kimi/config.toml has a [mcp.client] section holding only a timeout` | JSON mcpServers (stdio, HTTP, SSE); config.toml TOML | env, headers, args, url query. ~/.kimi/credentials/kimi-code.json, device_id and config.toml [providers] (api keys) are secrets: never index | Project file repo-bound. | docs |

Not supported by this agent: memory files (unverified).

Notes: Home dir naming: this machine and TT use ~/.kimi (KIMI_HOME override); current docs say ~/.kimi-code (KIMI_CODE_HOME). Scan both.

### OpenCode

| What | Scope | Path | Format | Secrets | Project link | Verified |
|---|---|---|---|---|---|---|
| Skills | project | `<project>/.opencode/skills/<name>/SKILL.md (also reads <project>/.claude/skills/)` | SKILL.md dir | none | Path is inside the project root. | **unverified** |
| Skills | user | `~/.config/opencode/skills/<name>/SKILL.md` | SKILL.md dir with YAML frontmatter | none |  | disk |
| Commands / prompts | project | `<project>/.opencode/commands/*.md; user: ~/.config/opencode/commands/*.md` | Markdown with YAML frontmatter; also definable in opencode.json | none |  | **unverified** |
| Agent definitions | project | `<project>/.opencode/agents/*.md; user: ~/.config/opencode/agents/*.md` | Markdown with YAML frontmatter (model, permissions, prompt body) | none |  | **unverified** |
| Artifacts & plans | project | `<project>/.opencode/plans/*.md (plan mode, unverified); session 'todo' table and 'compaction' parts in opencode.db` | Markdown / SQLite rows | none | opencode.db session.directory / project / project_directory tables key by project path (TT main.py _opencode_db_for_session, ~627-726). | disk |
| Images | user | `~/.local/share/opencode/opencode.db part rows where data.type='file' and mime like image/*; also ~/.local/share/opencode/tool-output, snapshot/` | part.data JSON with mime, url as data:image/png;base64,... or file:///path | none |  | disk |
| Instruction .md | project | `<project>/AGENTS.md walking up from cwd; falls back to <project>/CLAUDE.md if no AGENTS.md; extra files via opencode.json 'instructions' array (globs)` | Markdown | none |  | docs |
| Instruction .md | user | `~/.config/opencode/AGENTS.md (XDG_CONFIG_HOME respected)` | Markdown | none |  | TT code |
| Memory | user | `none dedicated; instruction_blob/instruction_entry tables exist in opencode.db (purpose unverified)` | SQLite | none |  | **unverified** |
| MCP config | user | `~/.config/opencode/opencode.json, opencode.jsonc (also <project>/opencode.json); key 'mcp'` | JSON/JSONC: mcp.<name>{type:local\|remote, command:[...], enabled, environment{}, url, headers{}, oauth} | mcp.<name>.environment (values), mcp.<name>.headers (values, e.g. Authorization), command array elements (tokens in args), url query strings |  | disk |

Notes: Session-to-project: opencode.db session.directory or project/project_directory. User-level skills/agents/commands tie to a project only by usage (tool parts or skill tool calls in that project's sessions). TT main.py _collect_plugins_opencode is a stub. Doc paths are from third-party summaries plus on-disk; official docs are V1/V2 split.

### Grok Build (xAI)

| What | Scope | Path | Format | Secrets | Project link | Verified |
|---|---|---|---|---|---|---|
| Skills | project | `<project>/.grok/skills/<name>/SKILL.md; also reads <project>/.claude/skills` | SKILL.md dir | none |  | docs |
| Skills | user | `~/.grok/skills/<name>/SKILL.md` | SKILL.md dir | none |  | disk |
| Commands / prompts | user | `~/.grok/slash-mru.json (usage list only); custom commands format unverified` | JSON | none |  | **unverified** |
| Agent definitions | project | `<project>/.grok/agents/*.md (unverified); also .claude/agents` | Markdown with frontmatter (assumed) | none |  | **unverified** |
| Artifacts & plans | user | `~/.grok/sessions/<encoded-cwd>/<uuid>/{chat_history.jsonl,summary.json,events.jsonl,updates.jsonl,rewind_points.jsonl,system_prompt.txt,tool_definitions.json,usage.json,images/}` | JSONL/JSON; plan/todo content appears inside chat_history and events (not separate files, unverified) | none | <encoded-cwd> is the URL-encoded absolute cwd (e.g. %2FUsers%2F...); decode and match project path. TT scan_grok in main.py ~3890. ~/.grok/trusted_folders.toml lists trusted project paths. | disk |
| Images | user | `~/.grok/sessions/<encoded-cwd>/<uuid>/images/{1.jpg,2.png,...}` | Image files; chat_history.jsonl references them (66 'type":"image' entries found across sessions) | none |  | disk |
| Instruction .md | project | `<project>/AGENTS.md (and variants), <project>/CLAUDE.md` | Markdown | none |  | docs |
| Memory | user | `~/.grok/memory-v2/global/{MEMORY.md,topics/,observations/,archive/,index.sqlite,memory_state.sqlite}; ~/.grok/memory-v2/workspaces/<name>-<hash>/` | Markdown plus SQLite index | none | workspaces/<basename>-<hash> probably hash of project path (unverified). | disk |
| MCP config | user | `~/.grok/config.toml table [mcp_servers.<name>]; also <project>/.mcp.json via .claude compat (unverified)` | TOML | mcp_servers.<name>.env (values), headers, args (tokens), url query strings. ~/.grok/auth.json and config.toml.bak: never read. |  | disk |

Not supported by this agent: Distinct plan-file directory not found.

Notes: Also ~/.grokbot (separate Grok Bot, no usage data) and worktrees.db. TT code: backend/main.py GROK_BOT_DIR ~847, scan ~3890. Official docs at docs.x.ai/build; config.toml schema not found online.

### Pi Coding Agent

| What | Scope | Path | Format | Secrets | Project link | Verified |
|---|---|---|---|---|---|---|
| Skills | project | `<project>/.pi/skills/ and <project>/.agents/skills/` | SKILL.md dir | none |  | docs |
| Skills | user | `~/.pi/agent/skills/<name>/SKILL.md and ~/.agents/skills/` | SKILL.md dir; root .md files in skills dir also count | none |  | disk |
| Commands / prompts | user | `~/.pi/agent/prompts/*.md; project <project>/.pi/prompts/*.md` | Markdown prompt templates, invoked as /name | none |  | docs |
| Agent definitions | user | `~/.pi/agent/extensions/*.ts (TypeScript extensions; no native subagent definitions)` | TypeScript | none |  | **unverified** |
| Images | user | `~/.pi/agent/sessions/<encoded-cwd>/<ts>_<uuid>.jsonl, content blocks of type image` | Inline base64 image content blocks in message entries | none | Directory name is the encoded cwd (e.g. --Users-name-path--); session header entry also carries cwd. TT scan ~4726 in main.py. | disk |
| Instruction .md | project | `~/.pi/agent/AGENTS.md (global), then AGENTS.md or CLAUDE.md in cwd and parents; SYSTEM.md (replace/append system prompt) per project` | Markdown | none |  | docs |
| MCP config | user | `~/.pi/agent/mcp.json (also mcp-cache.json, mcp-npx-cache.json); likely project .pi/mcp.json (unverified)` | JSON {mcpServers:{<name>:{command,args,...}}} from an MCP adapter package | mcpServers.<name>.env (values), headers, args elements (tokens), url query strings. ~/.pi/agent/auth.json: never read. |  | disk |

Not supported by this agent: memory, plans/artifacts (no dedicated plan files; pi has no built-in plan mode), native subagent definitions.

Notes: Sessions dir name encodes cwd as -- + path with / replaced by - + --. Docs moved npm scope from @mariozechner to @earendil-works; paths stable across 0.68 to 0.83.

### Oh My Pi (omp)

| What | Scope | Path | Format | Secrets | Project link | Verified |
|---|---|---|---|---|---|---|
| Skills | project | `<project>/.omp/skills/<name>/SKILL.md; user ~/.omp/agent/skills/; also reads ~/.agents/skills/` | SKILL.md dir | none |  | **unverified** |
| Commands / prompts | project | `<project>/.omp/commands/<name>.md; user ~/.omp/agent/commands/` | Markdown with YAML frontmatter (the oh-omp fork uses index.ts dirs) | none |  | **unverified** |
| Agent definitions | user | `~/.omp/agent/extensions/ (auto-discovered); omp has subagent/task agents in docs (path unverified)` | TypeScript / Markdown | none |  | **unverified** |
| Images | user | `~/.omp/agent/sessions/<encoded-cwd>/<ts>_<uuidv7>.jsonl` | JSONL, same family as pi | none | Session dir is encoded cwd; session header carries cwd. | TT code |
| Instruction .md | project | `<project>/.omp/AGENTS.md; <project>/AGENTS.md; omp also discovers CLAUDE.md/Codex AGENTS.md formats` | Markdown | none |  | **unverified** |
| MCP config | user | `~/.omp/agent/config.yml (settings); MCP file location unverified, omp reads other tools' MCP configs` | YAML/JSON | Assume env, headers, args, url query strings. |  | **unverified** |

Not supported by this agent: memory (unverified), plans (no plan file dir verified).

Notes: Fork of pi, so formats mirror pi. Official docs (omp.sh/docs, can1357/oh-my-pi) were not reached; I could not confirm anything on disk because omp is not installed here.

### Vibe (Mistral)

| What | Scope | Path | Format | Secrets | Project link | Verified |
|---|---|---|---|---|---|---|
| Skills | project | `<project>/.vibe/skills/<name>/SKILL.md; extra paths via config.toml skill_paths; enabled_skills / disabled_skills` | SKILL.md dir | none |  | docs |
| Skills | user | `~/.vibe/skills/<name>/SKILL.md (VIBE_HOME relocates ~/.vibe)` | SKILL.md dir with YAML frontmatter | none |  | disk |
| Commands / prompts | user | `skills double as slash commands in Vibe; no separate commands dir verified` | n/a | none |  | **unverified** |
| Agent definitions | project | `<project>/.vibe/agents/*.toml; user ~/.vibe/agents/*.toml` | TOML agent profile, selected with --agent or default_agent | none |  | docs |
| Artifacts & plans | user | `~/.vibe/logs/session/session_<date>_<time>_<id>/ (JSON files); ~/.vibe/vibehistory; ~/.vibe/vibe.log` | JSON session logs; TT scan builds sessions from them (main.py ~9292, VIBE_DIR main.py:562). Todo tool exists ([tools.todo]). | none | Session JSON metadata contains the working directory (TT derives project_path from it). Config merged by walking up from cwd. | disk |
| Instruction .md | user | `~/.vibe/AGENTS.md; on disk this machine has ~/.vibe/instructions.md` | Markdown | none | Project AGENTS.md at <project>/AGENTS.md; subdirectory behavior documented inconsistently. | disk |
| MCP config | user | `~/.vibe/config.toml and <project>/.vibe/config.toml (merged, project wins); [[mcp_servers]] array` | TOML array of tables; docs say env var NAME is stored, not key (for 'vibe mcp add') | mcp_servers entries: env, headers, args with tokens, url query strings. [[providers]] may carry api_key_env_var names. Never read ~/.vibe/.e |  | docs |

Not supported by this agent: images (no image storage found), memory (none found), dedicated plan files.

Notes: Mistral docs: docs.mistral.ai/mistral-vibe/terminal/configuration and /vibe/code/cli/configuration-reference. .agents/skills not confirmed for Vibe.

### Muse Code (Meta)

| What | Scope | Path | Format | Secrets | Project link | Verified |
|---|---|---|---|---|---|---|
| Skills | project | `<project>/.agents/skills/<id>/SKILL.md (also scans <project>/.claude/skills, <project>/.codex/skills)` | SKILL.md with frontmatter name/description | none |  | **unverified** |
| Agent definitions | user | `~/.config/muse/settings.json (user settings; a conflicting source says ~/.muse/config.toml)` | JSON (or TOML, sources conflict) | none |  | **unverified** |
| Instruction .md | project | `<project>/AGENTS.md (CLAUDE.md fallback), walked from cwd up to nearest .git; one file per directory level` | markdown | none |  | **unverified** |
| Memory | project | `<project>/.agents/memory/` | markdown (assumed) | none |  | **unverified** |
| MCP config | user | `none known` | n/a | n/a if no MCP |  | **unverified** |

Not supported by this agent: MCP (reported absent at launch, unverified), images (no source found), user-level to project tie: skills import --from claude copies skills, no per-project keying found.

Notes: Product launched 2026-08-05 beta. All evidence is third-party web, nothing on this machine and no TT adapter. Verify against official Meta docs before building a scanner. Project tie is by cwd only (project-local .agents/).

### Prime Agent (Prime Intellect)

| What | Scope | Path | Format | Secrets | Project link | Verified |
|---|---|---|---|---|---|---|
| Skills | user | `Agent Skills standard SKILL.md; exact dirs unknown, other tools' skill folders can be added via settings.json` | SKILL.md | none |  | **unverified** |
| Agent definitions | user | `~/.prime/agent/settings.json` | JSON; keys seen: onboardingShown, defaultProvider, defaultModel, recentModels, defaultThinkingLevel | settings.json has no secrets seen; ~/.prime/agent/auth.json holds credentials and must never be read |  | disk |
| Artifacts & plans | user | `~/.prime/agent/session-artifacts/<session-uuid>/` | unknown (dir exists per session, content not inspected) | none |  | disk |
| Instruction .md | user | `~/.prime/agent/AGENTS.md; project AGENTS.md and CLAUDE.md in cwd and parents` | markdown | none |  | TT code |

Not supported by this agent: slash commands (not verified), MCP config (not found), images (not found), memory files (none found).

Notes: Sessions are ~/.prime/agent/sessions/<uuid>.jsonl; cwd presumably in the session header, so project tie is via session cwd. Do not confuse with the separate `prime` Lab CLI which writes AGENTS.md via `prime lab setup`. A project-level dir (e.g. <project>/.prime) was not found in sources.

### DeepSeek Harness (dsh)

| What | Scope | Path | Format | Secrets | Project link | Verified |
|---|---|---|---|---|---|---|
| Skills | project | `<project>/.dsh/skills/ and <project>/.agents/skills/` | SKILL.md | none |  | **unverified** |
| Skills | user | `~/.dsh/skills/ (rank 400)` | SKILL.md | none |  | TT code |
| Agent definitions | user | `agentPreset in session header (standard, cordis, ...) and agent-preset/selected events; profile config ~/.dsh/profiles/<name>/cordis.yml` | zstd JSONL events + YAML | none |  | TT code |
| Instruction .md | project | `<project>/AGENTS.md and CLAUDE.md` | markdown | none |  | **unverified** |
| MCP config | user | `~/.dsh/settings.yaml (has 3 top-level keys) and plugin-managed config; ~/.dsh/profiles/<name>/ hold per-profile plugin packages (cordis.yml, package.json)` | YAML | API key is kept in ~/.dsh/.credentials.yaml (per web), settings.yaml only references it. Never read credentials. Plugin MCP entries may hold |  | **unverified** |

Not supported by this agent: slash commands (not found), images (not found in sources), memory files (none found), plan files (not found).

Notes: Sessions at ~/.dsh/sessions/<slugged-cwd>/<id>/session[.vN].jsonl.zstd, each header carries cwd, so project tie is via cwd and agentPreset/skills_catalog from the log. ~/.dsh/storages/session_projcache* is a project cache. Tied to project mainly through session logs.

### Qoder

| What | Scope | Path | Format | Secrets | Project link | Verified |
|---|---|---|---|---|---|---|
| Skills | user | `~/.qoder/skills/<name>/SKILL.md (plus assets/, references/, scripts/ subdirs)` | SKILL.md dirs | none |  | disk |
| Commands / prompts | project | `<project>/.qoder/commands/*.md and ~/.qoder/commands/*.md` | markdown | none |  | docs |
| Agent definitions | project | `<project>/.qoder/agents/*.md and ~/.qoder/agents/*.md (project agents need folder trust)` | markdown with frontmatter | none |  | docs |
| Artifacts & plans | user | `~/.qoder/tasks/<session-uuid>/ (task lists); transcripts ~/.qoder/projects/<slugged-cwd>/<uuid>.jsonl with subagents/ subdir` | JSON/JSONL | none |  | disk |
| Images | user | `inline in transcript JSONL, Claude-shaped content blocks (image/base64) (assumed)` | JSONL | none |  | **unverified** |
| Instruction .md | project | `<project>/AGENTS.md, <project>/AGENTS.local.md, <project>/.qoder/rules/**/*.md, ~/.qoder/AGENTS.md` | markdown | none |  | docs |
| Memory | user | `~/.qoder/projects/<slugged-cwd>/memory/ (also ~/.qoder/memory/)` | markdown (dirs present but empty here) | none |  | disk |
| MCP config | project | `<project>/.mcp.json, settings (~/.qoder/settings.json currently only has enabledPlugins), --mcp-config <file>; /mcp-config command edits entries` | JSON (mcpServers) | Claude-style mcpServers: env, headers, args, url query strings. |  | docs |

Not supported by this agent: images as files (none found).

Notes: Plugins at ~/.qoder/plugins (installed_plugins_v2.json with scope/installPath, user-visible flag). IDE keeps ~/Library/Application Support/com.qoder.app.stable/main.sqlite which mirrors JSONL (TT enriches titles only). Project tie: the slugged-cwd dir name and cwd inside transcripts.

### ZCode (Z.ai)

| What | Scope | Path | Format | Secrets | Project link | Verified |
|---|---|---|---|---|---|---|
| Skills | user | `plugin-bundled: ~/.zcode/cli/plugins/cache/zcode-plugins-official/{document-skills,skill-creator,zcode-guide,...}; user-skill dirs disputed (~/.claude/skills vs ZCode-specific)` | SKILL.md; plugin manifest .zcode-plugin/plugin.json can declare skills, commands, mcpServers | none |  | disk |
| Agent definitions | user | `~/.zcode/cli/agents/sess_<id>/ (per-session subagent state)` | unknown, not opened | none |  | disk |
| Artifacts & plans | user | `plans: SQLite todo table in ~/.zcode/cli/db/db.sqlite (TT main.py _scan_zcode, rows content/status keyed by session_id); tool-result files ~/.zcode/cli/artifacts/sess_<id>/*-tool-result-*.json` | SQLite + JSON | none |  | TT code |
| Instruction .md | user | `~/.zcode/AGENTS.md (global) and <project>/AGENTS.md` | markdown | none |  | **unverified** |
| Memory | user | `~/.zcode/v2/setting.json has memoryEnabled flag; memory store location not found` | unknown | none |  | **unverified** |
| MCP config | user | `~/.zcode/cli/config.json (user) and <project>/.zcode/config.json (workspace); desktop uses ~/.zcode/v2/config.json (key: provider) and ~/.zcode/v2/credentials.json` | JSON | v2/credentials.json and provider apiKey in config; MCP entries env, headers, args, url. Never read credentials.json. |  | docs |

Not supported by this agent: images (not found), slash command dir (only via plugin manifest).

Notes: Sessions in SQLite ~/.zcode/cli/db/db.sqlite with session.directory giving project; also ~/.zcode/v2/tasks-index.sqlite, rollout/model-io-*.jsonl (full model I/O, may contain secrets in prompts), v2/setting.json recentProjects. Project tie: session.directory.

### SmallCode

| What | Scope | Path | Format | Secrets | Project link | Verified |
|---|---|---|---|---|---|---|
| Skills | project | `<project>/.smallcode/skills/ plus bundled skills/ in install (brainstorming, debugging, tdd, ...)` | SKILL.md (assumed) | none |  | **unverified** |
| Artifacts & plans | project | `<project>/.smallcode/traces/<session-id>.json` | JSON | none |  | TT code |

Not supported by this agent: user-level data (everything is project-local), MCP, commands, agent definitions, memory, images (no evidence), AGENTS.md (no source says it reads one).

Notes: Ambiguous product name (Zireael, giveen, Doorman11991 repos). Project tie is inherent: traces live inside the project, so no mapping is needed.

### Hermes Agent (Nous Research)

| What | Scope | Path | Format | Secrets | Project link | Verified |
|---|---|---|---|---|---|---|
| Skills | user | `~/.hermes/skills/<category>/<name>/SKILL.md (bundled, agent-created and hub-installed; DESCRIPTION.md per category); per profile ~/.hermes/profiles/<name>/skills/` | agentskills.io SKILL.md with assets/references/scripts | none |  | disk |
| Agent definitions | user | `~/.hermes/profiles/<name>/ (a profile is a full parallel agent home with SOUL.md, skills, memories, config.yaml); ~/.hermes/plugins/<name>/plugin.yaml; ~/.hermes/hooks/` | dirs + YAML | none |  | disk |
| Artifacts & plans | user | `~/.hermes/profiles/<name>/plans/ (empty here), ~/.hermes/kanban.db tasks, ~/.hermes/pastes/paste_*.txt, ~/.hermes/sessions/*.jsonl and request_dump_*.json, ~/.hermes/cron/jobs.json and cron/output` | markdown/txt, SQLite, JSON/JSONL | none |  | disk |
| Images | user | `~/.hermes/images/ and ~/.hermes/image_cache/ (both empty here), ~/.hermes/assets/avatar.png (UI asset, not session content)` | image files, referenced by file path | none |  | disk |
| Instruction .md | project | `<project>/AGENTS.md, .hermes.md, CLAUDE.md, .cursorrules` | markdown | none |  | docs |
| Memory | user | `~/.hermes/memories/{MEMORY.md,USER.md}, ~/.hermes/SOUL.md; same under profiles/<name>/ (memories/, SOUL.md)` | markdown | none |  | TT code |
| MCP config | user | `~/.hermes/config.yaml key mcp_servers.<name> with command/args/enabled (seen), probably url/headers/env for HTTP and env servers; secrets also in ~/.hermes/.env, auth.json, google_token.json (never read)` | YAML | mcp_servers.<n>.env, .headers, .args (tokens, absolute paths with user segment), .url query strings; plus .env file |  | disk |

Not supported by this agent: slash commands as a user dir (not found; skills double as commands is unverified), project-level skills dir (none found; skills are user/profile-level).

Notes: Project tie: sessions in ~/.hermes/state.db carry cwd (cli-only per memory note on the grouping gap), ~/.hermes/projects.db exists (unopened, likely project registry), profiles each have own state.db. Kanban tasks tie via kanban.db. HERMES_HOME env overrides home (TT HERMES_DIR).
