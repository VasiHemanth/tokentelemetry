---
type: Harness
title: Antigravity (Google)
description: Gemini CLI's successor; brain transcripts under ~/.gemini/antigravity, CLI data under ~/.gemini/antigravity-cli, subagents linked via INVOKE_SUBAGENT.
resource: /backend/main.py
tags: [harness, coding-agent, delegation, google]
timestamp: 2026-07-02
---

# Antigravity

Google's live agent after the [Gemini CLI](gemini-cli.md) sunset
(2026-06-18). Two surfaces share `~/.gemini`:

- **IDE/brain:** `~/.gemini/antigravity/brain` (`ANTIGRAVITY_BRAIN_DIR`),
  transcripts at `brain/<id>/.system_generated/logs/transcript.jsonl`.
  Extensions inventory at `~/.antigravity/extensions`.
- **CLI (`agy`):** `~/.gemini/antigravity-cli` (`ANTIGRAVITY_CLI_DIR`);
  tests in `backend/test_antigravity_cli.py`. Also a summarizer backend
  (`backend/summarizers/antigravity.py`).

**Delegation:** spawns create full sibling conversations. The parent brain
transcript records an `INVOKE_SUBAGENT` step whose content embeds the child
`conversationId` (JSON-escaped); children link back via `send_message` to the
parent id. Children are sessions in their own right, so linkage is
annotation-only. Verified with agy 1.0.7; retroactive local linkage found 7
parents / 10 children (`DESIGN.md`).
