---
type: Harness
title: Claude Code
description: Richest-signal harness; JSONL transcripts under ~/.claude/projects with full cache fields, subagent rollup, skill and MCP usage.
resource: /backend/main.py
tags: [harness, coding-agent, delegation, anthropic]
timestamp: 2026-07-02
---

# Claude Code

- **Data:** `~/.claude/projects/<encoded-project>/<sessionId>.jsonl`
  (`CLAUDE_DIR` in `backend/main.py`). Subagents live at
  `<sessionId>/subagents/agent-<agentId>.jsonl` + `.meta.json`; the sibling
  `tool-results/` dir is ignored.
- **Signals:** input/output tokens, cache fields
  (`cache_read_input_tokens`, `cache_creation_input_tokens`, 1h ephemeral),
  model per line, tool calls, reasoning steps, skills
  (`Skill` tool_use + `<command-name>` tags, built-in CLI commands filtered),
  MCP usage from `mcp__<server>__<tool>` names.
- **Delegation:** full token rollup, the only harness with one. Subagent files
  are not sessions; their usage goes into a separate `delegated` bucket that IS
  included in aggregates. Cost each subagent file by its own `message.model`
  (subagent models routinely differ from the parent's; parent-model costing
  would be wrong). Parent link: dir name, with the `sessionId` field inside
  subagent lines as authoritative fallback. Spawning tool_use is `Agent`
  (older versions: `Task`). See [delegation telemetry](../subsystems/delegation-telemetry.md).
- **Quirks:** skip `<synthetic>` model lines; `cached` = high-water-mark of
  `cache_read_input_tokens` per transcript ([count-once](../conventions/count-once-invariant.md));
  transcripts pruned after `cleanupPeriodDays` (default 30), which is why the
  [history store](../subsystems/history-store.md) exists.
