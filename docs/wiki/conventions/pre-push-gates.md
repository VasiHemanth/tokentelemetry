---
type: Convention
title: Pre-push and pre-merge gates
description: "Three automated gates; UPDATE.json enforcement on feat: pushes, a local Claude review of the branch diff, and a CI npm-audit on package.json changes."
resource: /.claude/hooks
tags: [convention, ci, security, hooks]
timestamp: 2026-07-02
---

# Pre-push and pre-merge gates

Solo-maintainer substitute for human review, hardened after issue #91
(vulnerable + unused deps merged un-reviewed).

1. **`enforce-update-json.py`** (PreToolUse hook on Bash): a push/PR from a
   non-main branch containing at least one `feat:` commit must include an
   [UPDATE.json](update-json-feed.md) change in the diff vs `origin/main`.
   Pure fix/chore/docs branches pass silently. Detects pushes via proper
   shell tokenization, not substring match.
2. **`prepush-claude-review.py`** (PreToolUse hook on Bash): sends the
   branch diff to the local `claude` CLI for a focused review (dependency
   hygiene, remote-exposure/auth-bypass regressions, secrets, injection).
   Denies only on an explicit high-confidence `block`; **fails open** on any
   reviewer flakiness. Skips docs/asset-only pushes. Imports the
   push-detection helpers from gate 1.
3. **`.github/workflows/security-audit.yml`** (CI, deterministic):
   `npm audit --omit=dev --audit-level=high` across root/frontend/website on
   PRs touching a `package.json`. Catches contributor PRs the local hooks
   can't see. Lockfiles are gitignored, so CI uses
   `npm install --package-lock-only`; pins + `overrides` live in the
   committed `package.json`.

Last-resort bypass: `claude --no-hooks` (if needed often, the rule is
mis-tuned).
