# Weekly Digest — 2026-08-24

_Compared against weekly-digest-2026-08-20.md._

## Metrics

| Metric | Value | Δ vs last digest |
|---|---|---|
| Stars | **325** | +8 (317 → 325) |
| Open issues | **12** (#288, #277, #251, #225, #223, #222, #221, #198, #145, #65, #61, #45) | +1 (11 → 12) |
| Open PRs | **31** | +4 (27 → 31) |
| Merged this week | **3** PRs (#285, #284, #274) | −3 vs last digest's 6 |
| Issues closed this week | **2** (#283, #273) | −3 vs last digest's 5 |
| New contributors | **Rub3nCT** (#290 Windows path dedup), **sirenexcelsior** (#285 Grok billed usage) | — |

Quieter shipping week but community engagement stayed strong. Two new external
contributors landed substantive code: sirenexcelsior fixed Grok's billed-usage
pipeline (#285, merged) and Rub3nCT submitted a thorough Windows path
canonicalization PR (#290, awaiting review). hwantage continued their streak —
filed #288 + its fix #289, plus merged #284 (copy feedback UX). Star growth
slowed slightly (+8 vs +12) but the contributor pipeline is healthy.

## This week's activity (Aug 21 – Aug 24)

- **#285 merged (fix)** — sirenexcelsior: Grok sessions now read billed usage
  from the unified inference log (`prompt_tokens` / `completion_tokens` /
  `cached_prompt_tokens`) instead of showing only context-window footprint.
  Adds `grok-4.6` pricing with the 200k-prompt 2× cliff. First contribution.
- **#284 merged (feat)** — hwantage: copy feedback UX for Session ID in the
  Context Panel — icon-based button with "Copied" label, check icon, and
  success border tint (closes #283).
- **#274 merged (feat)** — hwantage: auto-scroll Step Index + Execution Timeline
  during session replay (closes #273). Merged Aug 18, counted in this window.
- **#290 opened (fix)** — Rub3nCT (FIRST_TIME_CONTRIBUTOR): Windows path
  separator canonicalization (`C:\a\b` vs `C:/a/b` → one project card).
  Touches 7 identity boundaries + history_store v3 migration. Includes tests.
- **#289 opened (fix)** — hwantage: sync active step and scroll views on manual
  scrubber seek (closes #288).
- **#288 opened (bug)** — hwantage: playback scrubber doesn't update activeStep
  when paused and manually seeking. Assigned to VasiHemanth; PR #289 ready.

## Action items (need a reply)

- **#290 (Rub3nCT)** — Windows path dedup, first-time contributor, 0 comments.
  High-quality PR with tests. Review promptly.
  → https://github.com/VasiHemanth/tokentelemetry/pull/290
- **#289 (hwantage)** — scrubber sync fix, 0 comments. PR for #288.
  → https://github.com/VasiHemanth/tokentelemetry/pull/289
- **#218 — octo-patch MiniMax summarizer PR**: external, still unreviewed (~5 weeks).
  Accept or decline. → https://github.com/VasiHemanth/tokentelemetry/pull/218
- **#203 — Jiaocz "Single Port Mode" PR** (impl of #198): still unreviewed (~7 weeks).
  → https://github.com/VasiHemanth/tokentelemetry/pull/203
- **#220 — Yagnasena1999 docs(audit) PR**: review or close.
  → https://github.com/VasiHemanth/tokentelemetry/pull/220
- **Yagnasena1999 issues #225/#223/#222/#221** (Aug-1 bug audit, all 0 comments):
  triage the remaining four.
- **#277 (cachemoney)** — cross-machine stats aggregation, replied but still open.
- **#61 (nujovich)** — hermes-telemetry listing (~12 weeks, 0 comments).
- **Dependabot backlog (~12 open)**: batch merge safe minor/patch bumps.
- **Own draft PRs**: #250, #231, #187, #184, #180, #171. Merge or mark WIP.

## Next week's content angle: Money week

Rotation: Community (Aug 17–23) → **Money (Aug 24–30)** → Visibility (Aug 31 – Sep 6).

1. **"What Grok 4.6 actually costs per session."** — #285 just landed real
   billed-usage parsing from the unified inference log. Show a Grok session
   with the 200k-prompt 2× pricing cliff and compare the old
   context-footprint estimate vs the new accurate number. Angle: "your
   dashboard was under-counting Grok — here's the real number."
2. **"Windows users were double-counting projects."** — #290 (if merged)
   fixes path separator dedup. Frame as money-adjacent: duplicate project
   cards mean duplicate budget tracking and confused cost rollups. Before/after
   screenshot of one project vs two phantom ones.
3. **"Your copy-paste workflow just got faster."** — #284's copy-feedback UX
   is small but visible. Pair it with a tip about exporting session IDs for
   cost auditing. Light Tuesday tip post.

Feature-Friday note: lead with **Grok billed-usage accuracy (#285)** and
Windows path dedup (#290) if merged. hwantage deserves a community shoutout —
6th consecutive week with merged contributions.

---
_Methodology: stars 325 from the live repo page counter (aria-label "325 users
starred"); open issue/PR counts from GitHub search totals
(`is:issue is:open` = 12, `is:pr is:open` = 31); merged-this-week = 3 from
search (`is:pr is:merged merged:>=2026-08-17`); issues-closed = 2 from search
(`is:issue is:closed closed:>=2026-08-17`). Point-in-time, Sun 2026-08-24._
