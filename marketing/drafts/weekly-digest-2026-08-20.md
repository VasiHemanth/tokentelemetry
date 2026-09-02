# Weekly Digest — 2026-08-20

_Compared against weekly-digest-2026-08-09.md._

## Metrics

| Metric | Value | Δ vs last digest |
|---|---|---|
| Stars | **317** | +12 (305 → 317) |
| Open issues | **11** (#277, #251, #225, #223, #222, #221, #198, #145, #65, #61, #45) | +1 (10 → 11) |
| Open PRs | **27** | −5 (32 → 27) |
| Merged this week | **6** PRs (#275, #274, #272, #271, #269, #266) | −4 vs last week's 10 |
| Issues closed this week | **5** (#273, #270, #268, #267, #265) | 0 (5 → 5) |
| New contributors | **cachemoney** (#277 multi-machine aggregation), **yannschepens** (#267 Ubuntu pip fix) | — |

Steady growth week. Star velocity held flat at +12, open PRs dropped meaningfully
(32 → 27) as 6 merged and old dependabot PRs cleared. The headline is
**DeepSeek Harness support landed (#275) — 17 agents now.** hwantage continued
their streak with 4 merged PRs this week (layout fixes + step filtering + auto-scroll),
cementing them as the most active outside contributor. Community engagement is
healthy: two new external users filed issues, both got replies within 24h.

## This week's activity (Aug 10 – Aug 20)

- **#275 merged (feat)** — DeepSeek Harness (dsh) as 17th supported agent:
  zstd-compressed JSONL scanning, per-step dedup, multi-provider cost recompute,
  and subagent delegation folding. Week's headline.
- **#272 merged (fix)** — pip-less venv bootstrap fix (closes #267 from
  yannschepens) + opportunistic uv acceleration (0.39s vs 2.78s install).
- **#269 merged (feat)** — step index category filter (hwantage, closes #268):
  filter long session traces by event type with zero API overhead.
- **#271 merged (fix)** — aside layer shift and sticky header overlap fix
  (hwantage, closes #270).
- **#274 merged (feat)** — auto-scroll step index + execution timeline during
  session replay (hwantage, closes #273).
- **#266 merged (fix)** — aside height mismatch on wider viewports (hwantage,
  closes #265).
- **#277 opened** — cachemoney requests cross-machine statistics aggregation
  (sqlite in git repo). Replied and assigned.

## Action items (need a reply)

- **#251 (hwantage) + #252 (mariadb-KyleHutchinson)** — persistent Hermes filter
  state. Both still open. Coordinate and pick the PR.
  → https://github.com/VasiHemanth/tokentelemetry/issues/251
- **#218 — octo-patch MiniMax summarizer PR**: external, still unreviewed (~4 weeks).
  Accept or decline. → https://github.com/VasiHemanth/tokentelemetry/pull/218
- **#203 — Jiaocz "Single Port Mode" PR** (impl of #198): still unreviewed (~6 weeks).
  → https://github.com/VasiHemanth/tokentelemetry/pull/203
- **#220 — Yagnasena1999 docs(audit) PR**: review or close.
  → https://github.com/VasiHemanth/tokentelemetry/pull/220
- **Yagnasena1999 issues #225/#223/#222/#221** (Aug-1 bug audit, still open,
  all 0 comments): #224 was fixed weeks ago — triage the remaining four so the
  audit isn't half-answered.
- **#61 — nujovich hermes-telemetry listing** (~11 weeks, 0 comments): one-line reply.
  → https://github.com/VasiHemanth/tokentelemetry/issues/61
- **Dependabot backlog (~12 open)**: #281, #280, #279, #278, #276, #254, #255,
  #249, #238, #237, #209, #160. Batch merge the safe minor/patch bumps.
- **Own draft PRs**: #250, #231, #187, #184, #180, #171. Merge or mark WIP.

## Next week's content angle: Money week

Rotation: Multi-agent (Aug 10–16) → Community (Aug 17–23) →
**Money (Aug 24–30)**.

1. **"What DeepSeek Harness actually costs."** — #275 landed with per-step
   dedup and multi-provider cost recompute. Show a real DSH session with
   mixed Ollama (free) + API segments and the correct cost split. Angle:
   local vs cloud costs for the same agent, one dashboard.
2. **"uv cuts install time 7×."** — #272's 0.39s vs 2.78s is a concrete
   number. Frame it as money-adjacent: "faster install = faster onboarding =
   you start seeing costs sooner." Demo GIF for Wednesday.
3. **"The hidden cost of bad venvs."** — tie #267 (Ubuntu pip failure) to
   the money angle: if you can't install, you can't track. Frame as a
   community-reported fix that unblocked real users from seeing their spend.

Feature-Friday note: lead with **17-agent support (#275, DSH)** and the
session replay UX improvements (#269 step filter, #274 auto-scroll, #271/#266
layout fixes). hwantage deserves a Thursday community shoutout — 4 merged PRs
in one week across bugs + features.

---
_Methodology: stars 317 from the live repo page counter (aria-label "317 users
starred") vs prior digest 305; open issue/PR counts from GitHub search totals
(`is:issue is:open` = 11, `is:pr is:open` = 27); merged-this-week = 6 from
search (`is:pr is:merged merged:>=2026-08-13`); issues-closed = 5 from search
(`is:issue is:closed closed:>=2026-08-13`). Point-in-time, Thu 2026-08-20._
