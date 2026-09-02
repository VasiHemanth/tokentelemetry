# Weekly Digest — 2026-06-14

_First digest — no prior week to diff against. Future digests will show deltas._

## Metrics

| Metric | Value | Δ vs last week |
|---|---|---|
| Stars | 107 | — (baseline) |
| Forks | 17 | — |
| Open issues | 3 | — |
| Open PRs | 1 | — |
| New contributors (this week) | fanyi-zhao (issue #98 → merged fix PR #99) | — |

## Action items (need a reply)

- **#65 — "Tests exist but no CI runs them — add GitHub Actions test workflow"** (Yagnasena1999, 0 comments, open since Jun 7). Solid, well-specified ask given the recent path-traversal/XSS history (#54-56). Worth a quick ack even if not actioned immediately. → https://github.com/VasiHemanth/tokentelemetry/issues/65
- **#61 — "hermes-telemetry — native Hermes plugin with budget enforcement"** (nujovich, 0 comments, open since Jun 6). Offers a complementary-tool README listing. Easy goodwill reply. → https://github.com/VasiHemanth/tokentelemetry/issues/61
- **#85 — PR "feat(intelligence): efficiency scoring, AI smell detection, burn rate forecasting"** (Yagnasena1999). You posted a thorough review 3 days ago (UPDATE.json policy blocker, missing session-field enrichment, hardcoded localhost URL, suggest splitting the PR). No contributor response yet — may need a nudge if it goes quiet much longer. → https://github.com/VasiHemanth/tokentelemetry/pull/85
- **#45 — mmmodels/models.dev pricing discussion** (ddiall): active back-and-forth, you're engaged — no action needed, just flagging it's still open with a live thread.

## This week's activity (highlights)

Very active week — 9 merged PRs, mostly same-day fixes to bug reports:

- **feat: durable analytics history + date/range filters (#103)** — SQLite-backed history store so analytics survive agent log pruning; day/week/month bucketing + agent/model filters. Closes the long-standing #83/#27 "this month/this year" ask.
- **feat: chip-aware local power default + drain-priority billing routes (#100)** — auto-detects Apple Silicon for local-model cost estimates; models Anthropic's June 15 Agent SDK credit split, Codex/Gemini/Copilot/Cursor bucket priorities.
- Same-day bug fixes for: SSH-tunnel data not loading (#96), Settings crash (#92), npm audit vulnerabilities (#91), Codex multi-day session date attribution (#88), Hermes sessions dropped via `sqlite3.Row.get()` (#87), cache-pricing math (#86, #68→#71), summarizer CLI launch via stdin (fanyi-zhao, #99).
- CI: bumped Node-20 → Node-24 actions ahead of the June 16 GitHub Actions cutoff (#102).
- Website: fixed Microsoft Clarity analytics not loading on tokentelemetry.com (#104).

## Next week's content angle: Money week

This week's shipped work (drain-priority billing routes, chip-aware power detection, durable analytics) is squarely a "what does this actually cost" story — good fit for the Money angle.

Post ideas:
1. **X/LinkedIn:** "Anthropic's June 15 Agent SDK credit split — here's how it changes what your Claude Code sessions actually draw from." Walk through the new drain-priority bucket model from #100 with a real dashboard screenshot.
2. **Demo GIF:** New Analytics page — date-range presets + day/week/month granularity (#103). Show "this month vs last month" cost comparison, which was the most-requested feature (#83/#27).
3. **Community/Friday:** Thank fanyi-zhao for their first merged PR (#99) and the 4 community bug reporters (andresako, andrewkangkr, h121b, MumuTW) whose issues were fixed same-day — good "this project ships fast" proof point for the milestone post.
