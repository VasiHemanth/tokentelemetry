# Changelog

All notable changes to TokenTelemetry will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- ZCode (Z.ai) support: sessions, tokens, cost, tool calls, plans, subagent delegation and traces read locally from `~/.zcode/cli/db/db.sqlite` (override the location with `ZCODE_DATA_DIR`)

### Fixed
- Cursor on-demand spend: a genuine zero on an individual spend field no longer falls back to the team pool's figure, so a team member with on-demand spend disabled is no longer shown the pool's usage as their own; a fully-zeroed individual reading now shows a $0 row instead of disappearing
- `/analytics`: a session whose live rescan came back as a zero-value stub (e.g. its on-disk transcript was pruned) no longer overwrites that session's real, previously-persisted totals in the response; only a genuine live session can still update the merged view

## [1.0.0] - 2026-04-27

### Added
- Initial public release of TokenTelemetry
- Local observability dashboard for AI coding agents
- Support for 9 agents: Claude Code, Gemini CLI, Codex, Cursor, GitHub Copilot, Qwen, OpenCode, Vibe, Antigravity
- Real-time token usage tracking and cost estimates
- Session trace waterfall with reasoning + tool call breakdown
- Per-project insights: heatmaps, model leaderboards, agent distribution
- Analytics: cumulative token usage per agent/model over time
- Plans view for captured plan-mode outputs
- FastAPI backend + Next.js frontend
- One-command install via `install.sh` (macOS/Linux) and `start.bat` (Windows)
- 100% local — no signup, no cloud, no telemetry
- MIT open source license
- Website at https://tokentelemetry.com
