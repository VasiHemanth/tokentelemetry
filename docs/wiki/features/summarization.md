---
type: Feature
title: AI session summaries
description: One-click session summaries via a user-picked backend (installed CLIs, Ollama, or any OpenAI-compatible endpoint) with classified errors.
resource: /website/content/docs/features/summarization.mdx
tags: [feature, summarization]
timestamp: 2026-07-02
---

# AI session summaries

Configured in Settings (backend picker + test-connection); generated from
session detail. Backends and the error pipeline live in the
[summarizers subsystem](../subsystems/summarizers.md).

- Backend options: installed agent CLIs (claude, codex, gemini, qwen,
  antigravity), local Ollama, or any OpenAI-compatible endpoint.
- Failures always render as a classified card (title, plain message,
  actionable hint, raw behind a disclosure), never a stack trace
  ([error handling](../conventions/error-handling.md)).
- Summaries persist in the [history store](../subsystems/history-store.md)
  even after the agent prunes the underlying transcript.
- Docs: `website/content/docs/configuration/configure-summarizer.mdx`.
