---
type: Feature
title: Analytics
description: Cross-agent token/cost analytics with date-range filters served from durable history merged with the live scan.
resource: /website/content/docs/features/analytics.mdx
tags: [feature, analytics]
timestamp: 2026-07-02
---

# Analytics

`/analytics` in the app. Aggregates tokens, cost, models, and agents over
time.

- Date ranges beyond each agent's own transcript retention work because reads
  come from the [history store](../subsystems/history-store.md) merged with
  the live scan (historical-only windows skip scanning entirely).
- Start-from-now caveat: only sessions on disk at first install are captured;
  the UI states this.
- Ecosystem buckets from [delegation telemetry](../subsystems/delegation-telemetry.md):
  `by_skill`, `by_mcp_server`, `by_subagent_type`, plus a `delegation` totals
  bucket. Delegated usage is exposed separately, never silently merged.
- Energy/CO2/savings figures recompute at read time from
  [power config](../subsystems/power-cost.md).
