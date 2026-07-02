# Log

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
