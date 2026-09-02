# Weekly Digest — 2026-07-06

_Compared against weekly-digest-2026-06-30.md._

## Metrics

| Metric | Value | Δ vs last digest |
|---|---|---|
| Stars | **210** | +62 since Jun 22 (Jun 30 count was unavailable; ~2-week delta) |
| Open issues | 3 (#65, #61, #45) | 0 |
| Open PRs | 6 | +3 |
| Merged this week | 3 (#117 pricing, #119 docs screenshots, #120 Cline+SmallCode) | — |
| New contributors | 1 — **kriptoburak** (first-time, PR #122) | +1 |

## This week's activity (Jun 30 – Jul 6)

- **#120 merged (feat)** — Cline + SmallCode session scanning, subagent-safe accounting. TT now covers 14 agents.
- **#121 opened (draft)** — `docs/wiki` second brain: 44-page OKF bundle + `/brain` skill.
- **#123 opened (draft)** — unified cross-agent Usage page, incl. research table of every agent's native `/usage` equivalent.
- **#124 opened (draft)** — Second Brain tab: interactive Obsidian-style graph of the project wiki.
- **#122 opened (community)** — "Hermes Tweet telemetry" README addition from a first-time contributor. Reads promotional; fork created minutes before the PR. Review skeptically before merging.

## Action items (need a reply)

- **#122 — kriptoburak PR**: decide accept/decline; don't leave a first-time contributor hanging. → https://github.com/VasiHemanth/tokentelemetry/pull/122
- **#112 — multi-agent metrics (own PR)**: 2 weeks unmerged, 0 comments, now behind main. Merge, rebase, or close. → https://github.com/VasiHemanth/tokentelemetry/pull/112
- **#85 — efficiency scoring PR** (Yagnasena1999): 25 days stale. Nudge or close with "reopen when ready." → https://github.com/VasiHemanth/tokentelemetry/pull/85
- **#65 — no CI runs tests** (Yagnasena1999): ~1 month unanswered; note the new `security-audit.yml` partially addresses it. → https://github.com/VasiHemanth/tokentelemetry/issues/65
- **#61 — hermes-telemetry listing** (nujovich): ~1 month unanswered, easy goodwill. → https://github.com/VasiHemanth/tokentelemetry/issues/61

## Next week's content angle: Money week

Rotation: Visibility (Jun 22) → Multi-agent (Jun 23–29) → Community (Jun 30–Jul 6) → **Money (Jul 6–12)**

1. **"What your agent's /usage command won't tell you"** — the #123 research table (14 agents, who has a native usage command, who doesn't) is a ready-made comparison thread; Cursor and Grok Build have nothing.
2. **Local-model cost story** — #120 shipped Cline/SmallCode scanning against Ollama: "local models are $0 in API fees — here's what a week of sessions looks like anyway" (tokens, power/CO2 card screenshot).
3. **Pricing-freshness post** — the #117 bot keeps `pricing_data.json` synced with models.dev weekly; pull one surprising price swing from the latest diff as the hook.
