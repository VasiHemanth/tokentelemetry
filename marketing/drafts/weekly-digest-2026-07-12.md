# Weekly Digest — 2026-07-12

_Compared against weekly-digest-2026-07-06.md._

## Metrics

| Metric | Value | Δ vs last digest |
|---|---|---|
| Stars | **228** | +18 (210 → 228) |
| Open issues | 3 (#65, #61, #45) | 0 |
| Open PRs | 7 | +1 |
| Merged this week | 9 (#125, #127, #130, #131, #132, #133, #134, #136, #137) | +6 |
| New contributors | 2 — **tom-swift-tech** (#127), **mariadb-KyleHutchinson** (#131) | +2 |

## This week's activity (Jul 6 – Jul 12)

Strong ship week — 9 PRs merged, two from new external contributors, both fixing real accuracy bugs:

- **#131 merged (feat)** — removed the 100-session parse cap; every session past the 100 most recent was silently frozen at zero tokens. Also fixed timestamp misdating + a stub-vs-real data race. From new contributor **mariadb-KyleHutchinson**.
- **#127 merged (fix)** — cache-hit % was computed from the per-session high-water mark, showing ~70% where the true rate was ~99.9%. Fixed by new contributor **tom-swift-tech** (fixes #126).
- **#136 + #137 merged (feat/docs)** — Pi Coding Agent (Earendil Works) support: scanning, per-turn pricing, marketing/docs. TT now covers 15 agents.
- **#130 merged (feat)** — per-step token usage in traces + better IDE session intent previews. Implements @ipatalas's discussions #128/#129.
- **#133 merged (fix)** — Copilot CLI was double-counting cache tokens (62.9k of 63.2k "input" was cache traffic counted twice).
- **#132 / #134 merged (chore/docs)** — `/bug-audit` weekly sweep skill; contributor-credit convention in UPDATE.json.
- **#139 opened (draft)** — anonymous per-agent model-family telemetry.
- **#138 opened (draft)** — Second Brain plugin docs section on the website.

## Action items (need a reply)

- **#122 — kriptoburak PR** (first-time contributor, open since Jul 2, still 0 comments): flagged promotional last week; a fork was created minutes before the PR. Decide accept/decline — don't leave it hanging two weeks. → https://github.com/VasiHemanth/tokentelemetry/pull/122
- **#85 — efficiency scoring PR** (Yagnasena1999, ~33 days stale): nudge or close with "reopen when ready." → https://github.com/VasiHemanth/tokentelemetry/pull/85
- **#112 — multi-agent metrics (own PR)**: ~19 days unmerged, 0 comments, behind main. Merge, rebase, or close. → https://github.com/VasiHemanth/tokentelemetry/pull/112
- **#61 — hermes-telemetry listing** (nujovich, ~5 weeks unanswered): easy goodwill reply. → https://github.com/VasiHemanth/tokentelemetry/issues/61
- **#65 — no CI runs tests** (Yagnasena1999, updated Jul 8): note that `security-audit.yml` partially addresses it. → https://github.com/VasiHemanth/tokentelemetry/issues/65
- **Own drafts to close out**: #124 (Second Brain graph tab), #121 (wiki bundle), #138, #139 — several open 1–2 weeks. Merge or mark clearly WIP.

## Next week's content angle: Visibility week

Rotation: Multi-agent (Jun 23–29) → Community (Jun 30–Jul 6) → Money (Jul 6–12) → **Visibility (Jul 13–19)**

This week's merges are a gift for a visibility theme — three shipped fixes are all "your dashboard was hiding/misreporting something, now it isn't":

1. **"Your cache hit rate was lying to you"** — #127 fixed a metric that showed ~70% when the real number was 99.9%. Before/after screenshot of the analytics card. Honest-numbers post, credit tom-swift-tech.
2. **"See which step in an agent run actually burned the tokens"** — #130 added per-step token chips to the trace. Screenshot of a trace with the output-token counts on the step rail; the one offending step stands out.
3. **"TT was freezing every session past your 100 most recent"** — #131 removed the cap. "If you have >100 sessions, your old dashboard was showing zeros — here's the full history now." Full-history visibility, credit mariadb-KyleHutchinson.

Feature-Friday note: plenty shipped (9 PRs, Pi support, two contributor fixes) — the announcement thread writes itself.
