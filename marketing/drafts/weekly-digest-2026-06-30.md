# Weekly Digest — 2026-06-30

_Compared against weekly-digest-2026-06-22.md._

## Metrics

| Metric | Value | Δ vs last digest |
|---|---|---|
| Stars | n/a (GitHub API not reachable this session; was 148 on 2026-06-22) | unknown |
| Forks | n/a | unknown |
| Open issues | 3 | 0 |
| Open PRs | 3 | +2 |
| New contributors (this week) | none — all commits self-authored | — |

Note: star/fork count not available from this session (same limitation as 2026-06-22 digest). Manually verify on the repo page before reading this Monday morning.

## This week's activity (Jun 23–30)

Four PRs merged, all self-authored:

- **#113 — Per-project budgets + notification center** (feat, Jun 23): observational spend/token budgets per project/agent with 80%/100% threshold alerts, a new notification bell in the sidebar, and the Config tab budget editor. Major user-facing feature.
- **#114 — Budget telemetry** (Jun 23): tracks `budgets` (editor open) and `budget-set` (save) events in the existing anonymous telemetry pipeline, privacy-preserving, no Worker redeploy required.
- **#115 — Git-worktree grouping** (feat, Jun 24–25): sessions inside a git worktree now roll up under the parent repo card. Worktrees stay as individual cards; deleted worktrees surface via git registry. Fixes split-metrics for parallelized agent workflows.
- **#116 — llms.txt + sitemap + docs copy** (docs, Jun 25): `/docs` tree now fully indexed in `llms.txt` and `sitemap.xml` (26 URLs); stale "no telemetry" copy corrected in two docs pages.

Commits not yet in a merged PR this week:
- `feat(workflows): grid/list/compact view toggle` (persisted per user)
- `feat(workflows): rich session rows, projects-style cards, search + filters`

## Action items (need a reply)

**Urgent:**
- **#117 — pricing refresh PR** (bot, created Jun 29, 0 comments): automated weekly models.dev refresh. Needs a quick eyeball on the diff for price swings before merge. → https://github.com/VasiHemanth/tokentelemetry/pull/117
- **#112 — multi-agent metrics PR** (VasiHemanth, open since Jun 23, 0 comments): process monitor, concurrency timeline, attribution tree, workflow grouping — your own large feat PR sitting unmerged for a week. Make the merge call. → https://github.com/VasiHemanth/tokentelemetry/pull/112

**Stale community (escalating):**
- **#85 — PR "efficiency scoring, AI smell detection, burn rate forecasting"** (Yagnasena1999): last activity Jun 11 — now **19 days stale**. Your review feedback is on record. Either nudge the contributor directly or close with a "reopen when ready" note to keep the queue clean. → https://github.com/VasiHemanth/tokentelemetry/pull/85
- **#65 — "Tests exist but no CI runs them"** (Yagnasena1999, 0 comments, open since Jun 7): three weeks unanswered. A one-line "on the roadmap" comment costs 30 seconds. → https://github.com/VasiHemanth/tokentelemetry/issues/65
- **#61 — hermes-telemetry complementary listing** (nujovich, 0 comments, open since Jun 6): still unanswered, still easy goodwill. → https://github.com/VasiHemanth/tokentelemetry/issues/61

**Not urgent:**
- **#45 — mmmodels/pricing discussion** (ddiall, 4 comments, last Jun 9): you're engaged, no action needed.

## Next week's content angle: Community week

Rotation: Money (Jun 15) → Visibility (Jun 22) → **Multi-agent (Jun 23–29)** → **Community (Jun 30–Jul 6)**

Post ideas grounded in this week's activity:

1. **Contributor spotlight / ecosystem post** — Answer #61 publicly (hermes-telemetry complementary tool) and turn it into a post: "two tools for Hermes Agent — what each does." The nujovich comparison table in #61 is ready-made content. Easy community goodwill and signals a healthy ecosystem.
2. **"Show your dashboard" engagement post** — A screenshot of your own TokenTelemetry dashboard with worktree grouping or the new budget pill + an ask for others to share theirs. Community weeks perform best when you prompt participation rather than ship news.
3. **Build-in-public thread** — Yagnasena1999 has had two open PRs for weeks (85, 65). A Friday post like "contributors ship features, maintainers review — here's what's in the queue and why review takes time" normalizes the process and doubles as project transparency content.
