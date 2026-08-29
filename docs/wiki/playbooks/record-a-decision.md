---
type: Playbook
title: Record a decision (ADR)
description: When and how to write an ADR; copy the template, number it, link issue/discussion/design doc, ship it in the feature PR.
tags: [playbook, process, adr]
timestamp: 2026-07-02
---

# Record a decision

Write an ADR for any decision that shapes architecture, storage, security
posture, or process (see `docs/adr/README.md`).

1. Copy `docs/adr/0000-template.md` to the next number:
   `docs/adr/000N-short-slug.md`.
2. Fill Status (Proposed/Accepted), Date, Deciders, and Related links
   (issue, discussion, `docs/design/` doc).
3. Context = the forces, including rejected alternatives and why. Decision =
   one paragraph. Consequences = the honest list, including the negative
   ones and how to undo.
4. Commit it in the feature PR, add the design doc to the
   `docs/design/README.md` index, and add a `decisions/` page here.

Existing: [0001](../decisions/adr-0001-record-decisions.md),
[0002](../decisions/adr-0002-durable-history.md),
[0003](../decisions/adr-0003-docs-site-fumadocs.md).
