# Changelog

All notable changes to TokenTelemetry will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

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
