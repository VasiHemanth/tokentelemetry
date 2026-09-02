# Weekly Digest — 2026-07-26

_Compared against weekly-digest-2026-07-19.md._

## Metrics

| Metric | Value | Δ vs last digest |
|---|---|---|
| Stars | **283** | +29 (254 → 283) |
| Open issues | 5 (#198, #145, #65, #61, #45) | 0 (composition changed) |
| Open PRs | **22** | +2 (20 → 22) |
| Merged this week | ~10 PRs (#172, #178, #179, #183, #185, #186, #192, #193, #194, #200) + direct commits | — |
| New issue reporters | 1 — **Jiaocz** (#198) | −3 |
| New contributor merged | **slmingol** (#172 Docker/Podman) — landed this week | +1 |

New star record: **+29**, edging out last week's +26 — third straight
accelerating week. Open-issue count is flat at 5, but the set turned over:
**#176 closed** (Hermes $0.00 fix shipped), **#198 opened**. Open-PR count crept
to 22, driven by 9 open dependabot PRs (4 new Jul 21 batch: #188–#191) plus a
growing pile of your own drafts — not real external review backlog.

## This week's activity (Jul 19 – Jul 26)

The Docker story dominated: **slmingol's #172 (Docker/Podman compose + GHCR CI)
merged** — last week's top action item, now closed — and immediately spawned
follow-ups: **#192** (container run guide), **#200** (forward `TT_AUTH_TOKEN`
into the backend container), and new issue **#198** (Jiaocz, combine API + Web
port) which is container-ergonomics feedback. First external infra contribution
to land.

- **#178 / #179 merged (fix)** — closes bwilli123's #176 (Hermes proxy/custom
  sessions priced at $0.00, now re-priced) and #170 (OpenCode data-dir
  resolution across platforms).
- **#193 merged (feat)** — surface Claude Code published artifacts per project,
  with an artifact-count badge on the Artifacts tab.
- **#194 merged (feat)** — truthful loop cancellation + next-run time on active loops.
- **#186 merged (perf)** — faster trace loading (mtime cache + O(n²)→O(n) pairing).
- **#183 merged (feat)** — show model reasoning effort for every agent that records one.
- **#185 merged (chore)** — pricing_data.json auto-refreshed from models.dev.
- **Pi coding agent** added to the supported-agents list (direct commit).
- **#198 opened** — Jiaocz's [FEAT] to combine API + Web port. You already replied
  (1 comment), so it's acknowledged; keep as a live request to design.

## Action items (need a reply)

- **#122 — kriptoburak PR** (docs, still **0 comments**, open since Jul 2 —
  **fourth week flagged**): accept or decline; it's aging into a bad look.
  → https://github.com/VasiHemanth/tokentelemetry/pull/122
- **#61 — nujovich hermes-telemetry listing** (**0 comments, ~7 weeks**): easy
  goodwill reply. → https://github.com/VasiHemanth/tokentelemetry/issues/61
- **#85 — Yagnasena1999 efficiency-scoring PR** (~47 days stale): nudge or close.
  → https://github.com/VasiHemanth/tokentelemetry/pull/85
- **#112 — multi-agent metrics (own PR)**: ~33 days, 0 comments, behind main.
  Merge, rebase, or close. → https://github.com/VasiHemanth/tokentelemetry/pull/112
- **#65 — no CI runs tests** (Yagnasena1999): note `security-audit.yml` partially
  covers it. → https://github.com/VasiHemanth/tokentelemetry/issues/65
- **slmingol follow-through**: #172 merged — credit them in UPDATE.json per
  convention and thank them on the PR; they're a live contributor worth keeping.
- **Dependabot sweep**: 9 open (#188, #189, #190, #191, #161, #160, #157, #153,
  #151). #160/#157 are the TS 5.9→7.0 majors still parked — batch-review in one sitting.
- **Own drafts**: #199, #197, #187, #180, #171, #146, #138, #124, #121 — nine open,
  several 1–3 weeks. Merge or mark clearly WIP.

## Next week's content angle: Money week

Rotation: Community (Jun 30–Jul 6) → Money (Jul 6–12) → Visibility (Jul 13–19) →
Community (Jul 20–26) → **Money (Jul 27–Aug 2)**.

This week handed you a clean money story — cost *accuracy*, not just cost display:

1. **"Your agent said $0.00. It wasn't free."** — the Hermes proxy/custom-endpoint
   repricing fix (#176 → #178). Screenshot a session that read $0.00 now showing
   its real cost. Angle: proxy and custom endpoints silently hide spend; TT now
   catches it. No hype — just the before/after number.
2. **"Why your cost numbers don't go stale."** — the weekly `pricing_data.json`
   refresh from models.dev (#185). Explain plainly: model prices change, TT pulls
   fresh ones automatically, so your dashboard math stays right.
3. **"Track spend across every agent from one container."** — tie slmingol's Docker
   merge (#172) to the money frame: one `docker compose up`, one dashboard, total
   cost across all your agents. Doubles as the contributor spotlight.

Feature-Friday note: ~10 PRs merged — Docker/Podman support (first infra
contribution), published artifacts, loop cancellation, Hermes repricing, trace
perf, reasoning-effort display. Plenty for the announcement thread.

---
_Methodology: stars from repo page (283) vs prior digest (254); open issue/PR
counts derived from the full open-items list (5 issues, 22 PRs); merged-this-week
from commit history since Jul 19. Counts are point-in-time (Sun 2026-07-26)._
