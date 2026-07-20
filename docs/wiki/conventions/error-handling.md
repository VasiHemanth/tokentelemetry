---
type: Convention
title: Classify errors, never dump them
description: Any summarizer-backend failure must pass through classify() into a titled card with a plain message and actionable hint; raw text only behind a disclosure.
tags: [convention, errors, ux]
timestamp: 2026-07-02
---

# Classify errors, never dump them

A user must never see a bare stack trace, `HTTP 4xx ...`, or a provider JSON
blob as an error message.

**Why:** raw provider errors are unreadable to the target user and erode the
polished-local-tool feel.

**How to apply:** adapters raise `SummarizerError` preserving detail;
`backend/summarizers/errors.py::classify()` buckets it (ordered patterns,
first match wins); the frontend renders the resulting `error_info` as
`SummaryErrorCard`. Hints say what to DO (switch model, check
`ollama serve`, set an env var), not what failed. Prefer graceful
degradation over erroring (openai_compat's clean-payload retry). Adding a
category touches three layers; follow the
[playbook](../playbooks/add-summarizer-error-category.md).

Mechanics: [summarizers subsystem](../subsystems/summarizers.md).
