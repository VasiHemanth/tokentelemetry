---
type: Feature
title: Hermes dashboard
description: Dedicated /hermes surface; sources, skills, memory, cron health, gateway health, cost anomalies.
resource: /website/content/docs/features/hermes.mdx
tags: [feature, hermes, autonomous-agent]
timestamp: 2026-07-02
---

# Hermes dashboard

`/hermes` in the app; the shape-specific surface for
[Hermes Agent](../harnesses/hermes.md), which runs across 38 platforms
rather than a terminal. Surfaces: overview with per-API-call latency and
cache-hit %, inline `delegate_task` subagent cards, skills page (90+ skills
with platform conditions), memory page (`MEMORY.md` / `USER.md` with
char-limit bars), cron-health tile, gateway-health pill, cost anomaly
detection.

A launcher plugin also embeds TT links inside Hermes's own dashboard (port
9119); details on the [harness page](../harnesses/hermes.md).
