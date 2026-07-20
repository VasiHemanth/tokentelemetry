---
type: Convention
title: Local-first, no user-machine network calls
description: No new outbound calls from user machines; data that needs refreshing is refreshed at build/CI time and shipped in releases.
tags: [convention, privacy, local-first]
timestamp: 2026-07-02
---

# Local-first

The brand promise: logs, prompts, tokens, and costs never leave the user's
machine. Enforced as a design rule, not just marketing.

**Why:** privacy is the product's main differentiator against cloud
observability tools.

**How to apply:** never add outbound network calls that run on user
machines. Data that goes stale ([pricing](../subsystems/pricing.md)) is
refreshed in CI and ships as committed files through normal updates. The
one deliberate exception is opt-out anonymous, content-free usage stats
(`backend/telemetry.py`, `DO_NOT_TRACK=1`, redaction tested in
`test_telemetry_redaction.py`); any future product telemetry must be
off-by-default (`docs/design/product-telemetry.md`).
