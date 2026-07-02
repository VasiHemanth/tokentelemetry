---
type: Harness
title: Hermes Agent (Nous Research)
description: Autonomous agent with a dedicated /hermes dashboard; state.db + agent.log under ~/.hermes, 38 source platforms, cron and gateway health.
resource: /llms.txt
tags: [harness, autonomous-agent, delegation, sqlite, nous]
timestamp: 2026-07-02
---

# Hermes Agent

The one autonomous (non-coding) agent, with its own dashboard at `/hermes`.
TokenTelemetry is the only third-party observability tool supporting it.

- **Data:** `~/.hermes` (`HERMES_DIR`, honors `HERMES_HOME`);
  `state.db` (sessions, `sessions.source` = 38 platforms: CLI, Telegram,
  Discord, Slack, cron, webhooks, email, SMS, ...), `logs/agent.log`
  (per-API-call latency, cache-hit %), profiles under `profiles/`, prompt
  snapshot for the skills page, `MEMORY.md` / `USER.md` for the memory page.
- **Dashboard surfaces:** delegate_task subagent cards, 90+ skills with
  platform conditions, memory char-limit bars, cron-health tile (at-risk
  schedules), gateway-health pill, cost anomaly detection (silent
  reasoning-token waste, e.g. MiMo thinking mode), provider-aware pricing
  (same model priced per aggregator: direct / OpenRouter / Together /
  Fireworks). See [Hermes dashboard](../features/hermes-dashboard.md).
- **Delegation:** children are sessions linked by
  `sessions.parent_session_id`; already counted, annotation-only
  ([count-once](../conventions/count-once-invariant.md)). Locally verified:
  12 of 21 sessions were children (`DESIGN.md`).
- **Plugin:** a launcher plugin for Hermes's own dashboard (port 9119) deep-
  links into TT pages; install via
  `hermes plugins install VasiHemanth/tokentelemetry-hermes-plugin` or
  `scripts/install-hermes-plugin.sh`. It is a launcher, not the engine.
