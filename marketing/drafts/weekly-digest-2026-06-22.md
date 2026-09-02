# Weekly Digest — 2026-06-22

_Compared against weekly-digest-2026-06-14.md (most recent prior digest; no digest was written for 06-21)._

## Metrics

| Metric | Value | Δ vs last digest |
|---|---|---|
| Stars | 148 | +41 |
| Forks | 21 | +4 |
| Open issues | 3 | 0 |
| Open PRs | 1 | 0 |
| New contributors (this week) | none — all commits self-authored (VasiHemanth) | — |

Note: star/fork counts came from the GitHub repo page (API metrics endpoint wasn't reachable from this session); issue/PR counts and commit history came directly from the GitHub MCP tools.

## Action items (need a reply)

- **#65 — "Tests exist but no CI runs them"** (Yagnasena1999, 0 comments, open since Jun 7). Still unanswered, two weeks running. → https://github.com/VasiHemanth/tokentelemetry/issues/65
- **#61 — "hermes-telemetry" complementary-tool listing** (nujovich, 0 comments, open since Jun 6). Easy goodwill reply, still unanswered. → https://github.com/VasiHemanth/tokentelemetry/issues/61
- **#85 — PR "efficiency scoring, AI smell detection, burn rate forecasting"** (Yagnasena1999). Your review (UPDATE.json policy blocker, missing field enrichment, hardcoded localhost, split-the-PR suggestion) is now **11 days old with no contributor response** (last activity Jun 11). Worth a direct nudge or closing/re-opening later if it stays stale. → https://github.com/VasiHemanth/tokentelemetry/pull/85
- **#45 — mmmodels/pricing discussion** (ddiall): still open, last comment Jun 9 — you're engaged, no urgent action.

## This week's activity (Jun 15–18; commits Jun 19–22 = none)

All self-authored, no external PRs merged:

- **feat: docs site + resources, route analytics, Antigravity session artifacts (#109)** — Fumadocs-powered documentation site, Community Resources page, GA4 route instrumentation, and Antigravity session artifacts now surface in the trace Artifacts tab.
- **fix(website): mobile nav menu (#110)** — Docs/Resources/Install now reachable on phones.
- **docs: README telemetry disclosure (#106)** + chore: weekly models.dev pricing refresh (#107) + worktree CRO analysis report (#105).

## Next week's content angle: Visibility week

Last digest called Jun 15–21 "Money week" (drain-priority billing, chip-aware power) — confirmed, that's what got drafted. Per the 4-week rotation (Money → **Visibility** → Multi-agent → Community), this week is Visibility, and it lines up well with what just shipped.

Post ideas:
1. **Demo GIF:** Antigravity trace Artifacts tab — show a real autonomous run's artifacts surfacing alongside tool calls. Direct "see what your agent actually did" hook.
2. **X/LinkedIn:** Announce the new Fumadocs documentation site — "here's exactly how TokenTelemetry reads your logs, no black box." Good trust-building post given the docs gap was long-standing.
3. **Community/Friday:** A draft already exists at `drafts/feature-friday-2026-06-22.md` covering this week's ship — reuse it, and consider asking users to share their own trace/Artifacts view as a follow-up engagement post.

Reminder: PR #85 has now gone quiet long enough that it may need attention before next week's digest either way.
