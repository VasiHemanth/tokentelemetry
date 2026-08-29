---
type: Convention
title: UPDATE.json is a curated feature feed
description: "Committed release feed rendered as the in-app update drawer; every feat: push must update it, fixes and chores must not pollute it."
resource: /UPDATE.json
tags: [convention, releases]
timestamp: 2026-07-02
---

# UPDATE.json

Committed at the repo root (source code, not generated). Rendered as the
in-app update drawer (up to 6 newest releases, 1-5 highlights each).

**Why curated:** the banner is only valuable when it announces things users
care about. Forcing entries for every fix/chore would train users to ignore
it; forgetting entries for real features means users on old versions never
hear about them.

**Schema:** `releases[]` newest-first with `tag` (ISO date), `title`
(<=50 chars), `highlights[]` of `{title, description, href?}`; internal
`href` renders as an in-app `<Link>`, external opens a new tab.
Descriptions explain why a non-technical user should care.

**Enforcement:** `.claude/hooks/enforce-update-json.py` denies any push
containing a `feat:` commit whose branch diff doesn't touch UPDATE.json;
see [pre-push gates](pre-push-gates.md) and the
[ship-a-feature playbook](../playbooks/ship-a-feature.md).

Test pollution note: clear `~/.tokentelemetry/.update-check.json` after
manually seeding it.
