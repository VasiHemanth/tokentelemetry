---
type: Harness
title: OpenAI Codex CLI
description: Rollout-file transcripts under ~/.codex; subagent threads detected via thread_source markers; session index is unreliable.
resource: /backend/main.py
tags: [harness, coding-agent, delegation, openai]
timestamp: 2026-07-02
---

# OpenAI Codex CLI

- **Data:** `~/.codex` (`CODEX_DIR`), one rollout file per thread.
- **Signals:** tokens, model, tool counts; also a summarizer backend
  (`backend/summarizers/codex.py`).
- **Delegation:** subagent threads are separate rollout files whose
  `session_meta.payload` carries `thread_source: "subagent"`,
  `forked_from_id`, and `source.subagent.thread_spawn`
  (`parent_thread_id`, `depth`, `agent_nickname`, `agent_role`). Plain
  `forked_from_id` also fires on user `codex fork`, so require the subagent
  markers before linking.
- **Quirks:** Codex stopped maintaining `session_index.jsonl` (observed frozen
  2026-04-23; 10 indexed vs 36 actual sessions), so the scanner globs rollout
  files directly and uses the index only for legacy thread names. Verified
  against codex 0.136.0 (`DESIGN.md`).
