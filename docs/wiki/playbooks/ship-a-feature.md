---
type: Playbook
title: Ship a feature to main
description: "The maintainer loop; branch, ADR/design doc in the PR, UPDATE.json entry for feat: commits, pass the pre-push gates, PR, board card."
tags: [playbook, process, releases]
timestamp: 2026-07-02
---

# Ship a feature to main

1. Branch from main. For anything non-trivial, write the ADR
   ([record a decision](record-a-decision.md)) and/or a design doc in
   `docs/design/`, committed in the same PR.
2. Implement with tests. Follow the standing conventions:
   [local-first](../conventions/local-first.md),
   [count-once](../conventions/count-once-invariant.md),
   [error handling](../conventions/error-handling.md).
3. If any commit is `feat:`, add a release entry to the top of
   [UPDATE.json](../conventions/update-json-feed.md) (user-benefit wording;
   the pre-push hook blocks you otherwise). Mixed branches: one entry for
   the feature, fixes ride free. Mis-labeled non-user-visible `feat:`:
   re-label to `refactor:`/`chore:` instead.
4. Push; the [gates](../conventions/pre-push-gates.md) run (UPDATE.json
   check + local Claude diff review; CI npm-audit if a `package.json`
   changed).
5. PR to main; track on GitHub Projects board #1. If totals or historical
   numbers change meaning, the UPDATE.json entry must say so explicitly.
6. After merge: `/brain ingest` the merged diff so this wiki stays current.
