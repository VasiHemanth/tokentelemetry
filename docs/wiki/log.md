# Log

## 2026-07-05

**Creation** New page type `Analysis` (`analyses/`, snapshot pages saved from
agent chats via the new `/brain save` workflow; body immutable after save,
only `status` may change). First page:
`analyses/graphify-vs-tt-plugin.md`, comparing the graphify knowledge-graph
skill with the tokentelemetry second-brain plugin, saved from the 2026-07-05
chat session, status proposed.

## 2026-07-02

**Creation** Initial compile of the bundle: overview, 13 harness pages, 9
subsystem pages, 7 feature pages, 3 decision pages, 6 playbooks, 5
conventions. Sources: repo at 8215d60 (`DESIGN.md`, `docs/adr/`,
`docs/design/`, `.claude/CLAUDE.md`, `llms.txt`, `backend/`, `bin/cli.js`,
`website/content/docs/`).

**Finding** `llms.txt` and `README.md` still list 10 coding agents; Cline and
SmallCode landed in PR #120 (commit 90f7ad0), so the real count is 12. The
source files need the update, not the wiki.

**Finding** ADR-0004 (resource-history sampling) and the
`docs/design/resource-history.md` design doc exist only on an unmerged branch;
the bundle documents main only and will pick them up on merge.
