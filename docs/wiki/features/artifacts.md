---
type: Feature
title: Artifacts
description: Deliverable artifacts per project and per session; Claude Code published pages and Antigravity task/plan/walkthrough docs, with local previews and a Cards/List toggle.
resource: /website/content/docs/features/artifacts.mdx
tags: [feature, artifacts, projects, sessions]
timestamp: 2026-07-22
---

# Artifacts

Shipped in PR #193 (2026-07-22). Surfaces the deliverables agents produce
beyond code, in two places: an Artifacts tab per project workspace and the
artifacts panel inside a [session trace](traces.md).

Two kinds, one `published_artifacts` list per session:

- **kind `page`:** a hosted claude.ai page published by Claude Code's
  `Artifact` tool. Extraction pairs the tool_use (file_path, title,
  description, favicon) with its tool_result, which carries the URL.
  Deduped by URL across redeploys: later publish wins, metadata a redeploy
  omitted is kept. The local source `path` is retained for previews. See
  [Claude Code](../harnesses/claude-code.md).
- **kind `document`:** Antigravity's per-session `task.md` /
  `implementation_plan.md` / `walkthrough.md`, with title from the doc's
  first heading and description from its `.metadata.json` sidecar summary.
  Sidecar `userFacing: false` docs are excluded. See
  [Antigravity](../harnesses/antigravity.md).

Behavior:

- `/projects` aggregates entries per card (`artifacts`); worktree publishes
  merge onto the repo-root card, identity url-or-path.
- Cards view previews artifacts locally: a sandboxed no-script iframe of the
  page's local HTML source (only while the file exists and sits under a
  served agent root; the hosted page is never fetched, per
  [local-first](../conventions/local-first.md)) and an expandable markdown
  preview for documents. List view is a compact row table; the toggle
  persists in localStorage. `/artifacts` answers HEAD for the existence
  check.
- Claude entries persist in the [history store](../subsystems/history-store.md)
  ecosystem blob, so links outlive transcript pruning.
- Tests: `backend/test_published_artifacts.py`.
