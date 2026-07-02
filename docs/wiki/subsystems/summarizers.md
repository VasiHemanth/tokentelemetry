---
type: Subsystem
title: Summarizers
description: Pluggable session-summary backends (claude, codex, gemini, qwen, antigravity, ollama, openai_compat) with a strict classify-don't-dump error pipeline.
resource: /backend/summarizers
tags: [subsystem, backend, summarization, errors]
timestamp: 2026-07-02
---

# Summarizers

Adapters in `backend/summarizers/`: `claude.py`, `codex.py`, `gemini.py`,
`qwen.py`, `antigravity.py`, `ollama.py`, `openai_compat.py`, base class in
`base.py`. Endpoint plumbing in `backend/summaries.py`.

## Error pipeline (never dump raw errors in the UI)

Rule of record: [summarizer error handling](../conventions/error-handling.md).
Three layers, all of which must change together when adding a category:

1. Adapters raise `SummarizerError` keeping status + provider body in the
   message so the classifier can match.
2. `errors.py::classify()` buckets via ordered `_PATTERNS` (first match wins;
   `too_large` before `quota` because token-budget 413s carry rate-limit
   wording) into categories: `auth`, `too_large`, `quota`, `model`,
   `timeout`, `network`, `no_output`. Returns
   `{category, title, message, hint, raw}` with per-backend hints
   (e.g. ollama network hint: "Is `ollama serve` running?"; timeouts:
   `TT_<BACKEND>_TIMEOUT` override).
3. Frontend renders `error_info` via `SummaryErrorCard`
   (`SummaryPanel.tsx`); `ERROR_ICONS` is a total Record so TS fails the
   build on a missing category. Category union lives in
   `frontend/src/lib/summarizer.ts`.

Prefer graceful degradation: `openai_compat` retries once with a clean
OpenAI-only payload when a strict gateway 400s on a non-standard field.
Playbook: [add an error category](../playbooks/add-summarizer-error-category.md).
