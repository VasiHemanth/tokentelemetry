# TokenTelemetry wiki

Second brain for the project: an [OKF v0.1](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
bundle maintained by the `/brain` skill (`.claude/skills/brain/SKILL.md`).
Humans edit sources; the wiki is recompiled from them. History in
[log.md](log.md).

## Start here

* [TokenTelemetry](overview.md) - Local-first observability dashboard for AI coding agents and autonomous agents; reads session logs from disk, no SDK or cloud.

## Harnesses

* [Claude Code](harnesses/claude-code.md) - Richest-signal harness; JSONL transcripts under ~/.claude/projects with full cache fields, subagent rollup, skill and MCP usage.
* [OpenAI Codex CLI](harnesses/codex.md) - Rollout-file transcripts under ~/.codex; subagent threads detected via thread_source markers; session index is unreliable.
* [Cursor](harnesses/cursor.md) - Agent transcripts under ~/.cursor/projects; subagent spawns are detectable but carry no token usage at all.
* [GitHub Copilot CLI](harnesses/copilot.md) - Session state under ~/.copilot/session-state; basic token/session signals, no delegation or per-call tool signal.
* [Qwen CLI](harnesses/qwen.md) - Alibaba's coding agent; scanned from ~/.qwen, also usable as a summarizer backend. No delegation signal.
* [OpenCode](harnesses/opencode.md) - SQLite-backed sessions; child sessions are first-class rows linked by session.parent_id, so delegated usage is already counted.
* [Vibe](harnesses/vibe.md) - Scanned from ~/.vibe; sessions and tokens only, no delegation or per-call tool signal.
* [Antigravity (Google)](harnesses/antigravity.md) - Gemini CLI's successor; brain transcripts under ~/.gemini/antigravity, CLI data under ~/.gemini/antigravity-cli, subagents linked via INVOKE_SUBAGENT.
* [Gemini CLI (legacy)](harnesses/gemini-cli.md) - Google's discontinued CLI agent; still scanned from ~/.gemini but treated as legacy, superseded by Antigravity.
* [Grok Build (xAI)](harnesses/grok-build.md) - Sessions under ~/.grok/sessions; subagents on by default with rich meta.json spawn records, children are sibling sessions.
* [Cline](harnesses/cline.md) - Two stores; a CLI SQLite db at ~/.cline/data/db/sessions.db and the VS Code extension's taskHistory.json. Added in PR #120.
* [SmallCode](harnesses/smallcode.md) - Project-local traces at <project>/.smallcode/traces/<id>.json; the only harness whose data lives in the repo, not the home dir. Added in PR #120.
* [Hermes Agent (Nous Research)](harnesses/hermes.md) - Autonomous agent with a dedicated /hermes dashboard; state.db + agent.log under ~/.hermes, 38 source platforms, cron and gateway health.

## Subsystems

* [Session scanner](subsystems/scanner.md) - The core pipeline in backend/main.py; live-scans every harness's on-disk logs into a unified session list with a 30s cache and 100-session cap.
* [Durable history store](subsystems/history-store.md) - SQLite rollup at ~/.tokentelemetry/history.db so analytics survive each agent's transcript pruning; raw facts stored, insights recomputed at read.
* [Pricing](subsystems/pricing.md) - Costing from a bundled, committed pricing_data.json; refreshed by a CI-only models.dev sync that opens a review PR. Zero runtime network.
* [Summarizers](subsystems/summarizers.md) - Pluggable session-summary backends (claude, codex, gemini, qwen, antigravity, ollama, openai_compat) with a strict classify-don't-dump error pipeline.
* [Remote access auth](subsystems/remote-auth.md) - Token gate for non-loopback access; RemoteAuthMiddleware requires a bearer token on remote requests, loopback always exempt, CORS is not the boundary.
* [Power, energy and CO2 costing](subsystems/power-cost.md) - Local-electricity and subscription costing; energy = configured watts x session latency, recomputed at read time from stored raw facts.
* [Delegation and ecosystem telemetry](subsystems/delegation-telemetry.md) - Per-session subagent, skill, and MCP attribution; capability varies by harness, tokens are never invented, aggregates never double-count.
* [CLI launcher](subsystems/cli.md) - bin/cli.js starts backend (default port 8000) and frontend (3000); flags for ports, host, origins, auth token, data dir.
* [Frontend dashboard](subsystems/frontend.md) - Next.js 16 App Router app in frontend/; routes for dashboard, analytics, sessions, projects, hermes, local-models, settings.

## Features

* [Analytics](features/analytics.md) - Cross-agent token/cost analytics with date-range filters served from durable history merged with the live scan.
* [Session traces](features/traces.md) - Per-session drill-in; tool calls, reasoning steps, artifacts, delegated-work cards, skills and MCP usage.
* [Projects](features/projects.md) - Groups sessions by working directory/project across agents, with per-project totals.
* [Hermes dashboard](features/hermes-dashboard.md) - Dedicated /hermes surface; sources, skills, memory, cron health, gateway health, cost anomalies.
* [AI session summaries](features/summarization.md) - One-click session summaries via a user-picked backend (installed CLIs, Ollama, or any OpenAI-compatible endpoint) with classified errors.
* [Local models](features/local-models.md) - Inventory of local models from Ollama and Hugging Face caches, with electricity-cost context.
* [Schedules (read-only)](features/schedules.md) - Scheduled-job visibility; the CRUD UI exists but is intentionally disabled behind DISABLED-MUTATIONS markers.

## Decisions

* [ADR-0001 Record architecture decisions](decisions/adr-0001-record-decisions.md) - Architecture decisions are recorded as ADRs in docs/adr/, one per decision, committed in the feature PR.
* [ADR-0002 Durable SQLite rollup for analytics history](decisions/adr-0002-durable-history.md) - Accepted 2026-06-13; own SQLite store of raw facts merged with live scans, tiered retention, because agents prune their own transcripts.
* [ADR-0003 Docs and resources site with Fumadocs](decisions/adr-0003-docs-site-fumadocs.md) - Docs built with Fumadocs inside the existing website/ Next.js app, statically exported to tokentelemetry.com/docs on GitHub Pages.

## Playbooks

* [Add a new harness](playbooks/add-a-harness.md) - Steps to support a new agent; verify real data shapes first, add scanner constants and parser, fixture tests, honest capability flags, docs.
* [Add a summarizer error category](playbooks/add-summarizer-error-category.md) - Three files must change together; errors.py pattern + copy, the TS category union, and the ERROR_ICONS record.
* [Ship a feature to main](playbooks/ship-a-feature.md) - The maintainer loop; branch, ADR/design doc in the PR, UPDATE.json entry for feat: commits, pass the pre-push gates, PR, board card.
* [Write scanner tests](playbooks/write-scanner-tests.md) - Fixture pattern for backend tests; monkeypatch the module-level dir constants and build a tmp tree mirroring the harness's real layout.
* [Run TokenTelemetry locally](playbooks/run-locally.md) - Start backend and frontend for development; default ports 8000/3000, data dir override, common env vars.
* [Record a decision (ADR)](playbooks/record-a-decision.md) - When and how to write an ADR; copy the template, number it, link issue/discussion/design doc, ship it in the feature PR.

## Analyses

* [graphify vs the tokentelemetry plugin](analyses/graphify-vs-tt-plugin.md) - Comparison of the graphify knowledge-graph skill and the tokentelemetry second-brain plugin: cousins, not twins; a map vs a field guide, and how they compose.
* [How to prove the brain saves tokens, ranked approaches](analyses/brain-savings-approaches.md) - Depth-and-breadth assessment of eight measurement approaches, grounded in a real 2-arm pilot on education_video and a 51-session trace audit; adherence, not wiki quality, is the current bottleneck.
* [Four token-optimization techniques beyond the current seeds](analyses/next-token-optimization-techniques.md) - Data-mined candidates attacking conversation shape (turn batching, tool-result diet, scout delegation, checkpoint-restart), the waste pools ponytail, caveman, headroom and the wiki do not touch.
* [Multi-harness session mining for the plugin](analyses/multi-harness-session-mining.md) - How to extend the plugin's session_scan beyond Claude Code to every harness TokenTelemetry parses, with a per-harness feasibility matrix and three build options.

## Ideas

* [Prove the brain saves tokens](ideas/prove-brain-token-savings.md) - Benchmark the brain-init/compile/skillsmith pipeline and surface a payback metric; replace the domain-profile menu with a census-driven dynamic schema.

## Conventions

* [Local-first, no user-machine network calls](conventions/local-first.md) - No new outbound calls from user machines; data that needs refreshing is refreshed at build/CI time and shipped in releases.
* [Count-once invariant and honest n/a](conventions/count-once-invariant.md) - Every token appears in aggregates exactly once, and signals a harness does not record render as "not recorded", never zero or estimated.
* [UPDATE.json is a curated feature feed](conventions/update-json-feed.md) - Committed release feed rendered as the in-app update drawer; every feat: push must update it, fixes and chores must not pollute it.
* [Pre-push and pre-merge gates](conventions/pre-push-gates.md) - Three automated gates; UPDATE.json enforcement on feat: pushes, a local Claude review of the branch diff, and a CI npm-audit on package.json changes.
* [Classify errors, never dump them](conventions/error-handling.md) - Any summarizer-backend failure must pass through classify() into a titled card with a plain message and actionable hint; raw text only behind a disclosure.
