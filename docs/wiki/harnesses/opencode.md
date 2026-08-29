---
type: Harness
title: OpenCode
description: SQLite-backed sessions; child sessions are first-class rows linked by session.parent_id, so delegated usage is already counted.
resource: /backend/main.py
tags: [harness, coding-agent, delegation, sqlite]
timestamp: 2026-07-02
---

# OpenCode

- **Data:** SQLite state (sessions table with `parent_id`).
- **Signals:** tokens, model, tool counts.
- **Delegation:** children ARE sessions and already appear in aggregates.
  TokenTelemetry only annotates the hierarchy: `parent_session_id` on
  children, `child_session_ids` plus display-only delegated sums on parents.
  Never fold child sums into totals; that double-counts
  ([count-once](../conventions/count-once-invariant.md)). Locally verified:
  5 of 12 sessions were children (`DESIGN.md`).
