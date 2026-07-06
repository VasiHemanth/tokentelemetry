# Log

## 2026-07-06

**Finding** The adherence experiment proposed by
`analyses/brain-savings-approaches.md` ran the same day (24 sessions, 3
routing arms on education_video copies). Index-in-pointer routing reached
8/8 wiki consultation at a third of the turns and half the cost of the
current pointer block (5/8); a skillsmith-generated skill never fired (0/8
invocations while loaded). Recorded as a dated refinement on
`ideas/prove-brain-token-savings.md`; plugin-side changes (pointer block
gains an embedded page map, skillsmith routing role rethought) are direction,
not yet implemented.

**Creation** Analysis page `analyses/brain-savings-approaches.md`, saved from
the research session that assessed `ideas/prove-brain-token-savings.md`.
Evidence: a 2-arm pilot on education_video (16 headless sessions) and a
51-session trace audit, plus two adversarial reviews. Ranked five approaches;
headline finding is that agent adherence to the wiki, not wiki quality, is
the current bottleneck. The idea page gained a dated refinement pointing at
the analysis. Status: proposed.

**Creation** First `Idea` page via the new `/brain idea` workflow:
`ideas/prove-brain-token-savings.md`. Captured from a maintainer prompt:
domain profiles may be too restrictive (starting kits, not boxes), and the
token-savings claim behind the plugin pipeline needs benchmarks plus an
in-product payback metric next to the build-cost badge. Status: captured.

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
