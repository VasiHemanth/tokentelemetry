---
type: Convention
title: Count-once invariant and honest n/a
description: Every token appears in aggregates exactly once, and signals a harness does not record render as "not recorded", never zero or estimated.
tags: [convention, telemetry, trust]
timestamp: 2026-07-02
---

# Count-once invariant, honest n/a

Two trust rules from `DESIGN.md` that govern all telemetry work:

1. **Count once.** Every token is in project/analytics aggregates exactly
   once. Where children are already sessions (opencode, hermes, grok, codex,
   antigravity), parent-side delegated sums are display-only. Where subagent
   usage was counted nowhere (claude-code), it joins aggregates as a separate
   `delegated` bucket, and the totals increase is announced in
   [UPDATE.json](update-json-feed.md), never discovered.
2. **Honest n/a.** If an agent's logs don't record a signal, render
   "not recorded by <agent>". No fake zeros, no estimates (cursor subagent
   tokens are the canonical case). Cache figures follow source semantics:
   `cached` = high-water-mark of `cache_read_input_tokens` per transcript.

Corollaries: no silent historical changes, model-correct pricing (cost each
file by its own model), existing aggregate keys stay byte-identical when new
buckets are added.
