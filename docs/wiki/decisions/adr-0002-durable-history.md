---
type: Decision
title: ADR-0002 Durable SQLite rollup for analytics history
description: Accepted 2026-06-13; own SQLite store of raw facts merged with live scans, tiered retention, because agents prune their own transcripts.
resource: /docs/adr/0002-durable-history-rollup.md
tags: [decision, analytics, sqlite]
timestamp: 2026-07-02
---

# ADR-0002: Durable SQLite rollup

**Accepted** 2026-06-13 (issue #83, discussion #27). Long date ranges were
structurally impossible from live scans because agents prune transcripts
(~30 days). Chosen: local SQLite of **raw facts** (not derived insights, so
config changes apply retroactively), merged with the live scan at read,
tiered retention (core rollup always; transcripts opt-in; summaries persist).

Rejected: live-scan only (feature impossible), archive-everything default
(disk-heavy, un-asked-for copying), storing derived insights (freezes power
config), per-request Python filtering (latency).

Consequences and limits on the [history store page](../subsystems/history-store.md).
