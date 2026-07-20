---
type: Feature
title: Schedules (read-only)
description: Scheduled-job visibility; the CRUD UI exists but is intentionally disabled behind DISABLED-MUTATIONS markers.
resource: /backend/main.py
tags: [feature, schedules, cron]
timestamp: 2026-07-02
---

# Schedules

Scheduled-job (cron) health is shown read-only (most visibly the Hermes
cron-health tile flagging at-risk schedules).

**The schedules page is read-only by decision.** Mutation endpoints and CRUD
UI were built but are commented out under `# DISABLED-MUTATIONS:` markers in
`backend/main.py`. To re-enable, uncomment those blocks; do not reimplement.
