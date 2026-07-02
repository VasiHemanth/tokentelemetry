---
type: Playbook
title: Add a summarizer error category
description: Three files must change together; errors.py pattern + copy, the TS category union, and the ERROR_ICONS record.
tags: [playbook, summarization, errors]
timestamp: 2026-07-02
---

# Add a summarizer error category

All three layers or it won't compile / won't render:

1. `backend/summarizers/errors.py`: add the pattern tuple to `_PATTERNS`
   (order matters, first match wins; put more specific wording before
   broader, e.g. `too_large` sits before `quota`) and the
   `title`/`message`/`hint` branch. Hints must say what to DO.
2. `frontend/src/lib/summarizer.ts`: add the category to the
   `SummaryErrorInfo["category"]` union.
3. `SummaryPanel.tsx`: add an icon to `ERROR_ICONS` (total `Record`; TS
   fails the build if missing, which is the safety net).

Context: [error-handling convention](../conventions/error-handling.md),
[summarizers subsystem](../subsystems/summarizers.md).
