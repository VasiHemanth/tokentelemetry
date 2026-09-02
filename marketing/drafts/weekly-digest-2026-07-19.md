# Weekly Digest — 2026-07-19

_Compared against weekly-digest-2026-07-12.md._

## Metrics

| Metric | Value | Δ vs last digest |
|---|---|---|
| Stars | **254** | +26 (228 → 254) |
| Open issues | 5 (#176, #145, #65, #61, #45) | +2 |
| Open PRs | **20** | +13 |
| Merged this week | 22 (12 human + 10 bot) | +13 |
| New issue reporters | 4 — **vipentti** (#181), **bwilli123** (#176), **cobrabr** (#162), **mvinca-bandwidth** (#142) | +2 |
| New contributor PRs | 1 — **slmingol** (#172, Docker/Podman) | — |

Biggest star week on record (+26 vs +18 last week). Open-PR count ballooned mostly
from 6 dependabot PRs (Jul 14) plus 5 of your own drafts — not real review backlog.

## This week's activity (Jul 12 – Jul 19)

Fast-response week: three externally-reported bugs went from report to merged fix
in under a day each.

- **#182 merged (fix)** — Codex Desktop session crash on structured reasoning
  summaries. Reported by **vipentti** at 04:58, merged 06:03 the same morning.
- **#163 merged (fix)** — Windows install broken by non-universal `requirements.lock`
  (uvloop). **cobrabr** reported #162 at 17:44, fixed and merged by 18:04 — 20 minutes.
- **#140 + #143 merged (feat)** — Hermes profiles: attribution, scope UI, burn budgets,
  kanban costs, plus a two-profile diff view. Implements **mvinca-bandwidth**'s #142,
  which was filed and closed same-day.
- **#167 + #169 merged (feat)** — `/loop` telemetry: detect, track and show recurring
  loops per session (re-landed on main), then **#177** added project loop tabs plus
  Grok & Cline detection.
- **#175 merged (feat)** — Settings now shows each agent's experimental / feature flags.
- **#166 / #168 merged (fix)** — subagent token attribution in Claude traces;
  clearer total-tokens/cost scope labels (dashboard all-time vs analytics window).
- **#144 merged** — security & docs fixes from Shiv's review.
- **#172 opened** — Docker/Podman compose support + GHCR CI, from new external
  contributor **slmingol**. Not yet triaged.
- **#178 / #179 open** — fixes for **bwilli123**'s #176 (Hermes proxy sessions priced
  at $0.00) and #170 (OpenCode data-dir resolution).

## Action items (need a reply)

- **#172 — slmingol's Docker/Podman PR** (new contributor, opened Jul 18): a substantial
  infra contribution sitting untriaged. Highest-value reply this week — review or at
  minimum acknowledge. → https://github.com/VasiHemanth/tokentelemetry/pull/172
- **#176 — bwilli123** offered a tested patch and you have #178 open covering it. Close
  the loop: tell them the fix is in flight and credit them in UPDATE.json per convention.
  → https://github.com/VasiHemanth/tokentelemetry/issues/176
- **#122 — kriptoburak PR** (still 0 comments, open since Jul 2 — **third week flagged**):
  accept or decline. → https://github.com/VasiHemanth/tokentelemetry/pull/122
- **#85 — Yagnasena1999 efficiency-scoring PR** (~40 days stale): nudge or close.
  → https://github.com/VasiHemanth/tokentelemetry/pull/85
- **#112 — multi-agent metrics (own PR)**: ~26 days, 0 comments, behind main. Merge,
  rebase, or close. → https://github.com/VasiHemanth/tokentelemetry/pull/112
- **#61 — nujovich hermes-telemetry listing** (~6 weeks unanswered): easy goodwill reply.
  → https://github.com/VasiHemanth/tokentelemetry/issues/61
- **#65 — no CI runs tests** (Yagnasena1999): note `security-audit.yml` partially covers it.
  → https://github.com/VasiHemanth/tokentelemetry/issues/65
- **Dependabot sweep**: 6 open (#161, #160, #157, #153, #151, #150). #160/#157 are
  TypeScript 5.9 → 7.0 majors — batch-review in one sitting so the queue reads clean.
- **Own drafts**: #184, #183, #180, #179, #171, #146, #138, #124, #121 — nine open,
  several 1–2 weeks. Merge or mark clearly WIP.

## Next week's content angle: Community week

Rotation: Multi-agent (Jun 23–29) → Community (Jun 30–Jul 6) → Money (Jul 6–12) →
Visibility (Jul 13–19) → **Community (Jul 20–26)**

This week's story is response time and users shaping the roadmap — perfect for community:

1. **"Reported 04:58, fixed 06:03"** — the vipentti Codex crash (#181 → #182), and the
   cobrabr Windows install bug fixed in 20 minutes (#162 → #163). Screenshot the two
   issue timelines side by side. Angle: what it looks like when a maintainer actually
   reads the issue tracker. No hype — just the two timestamps and what changed.
2. **"A user asked for Hermes profile comparison. It shipped that week."**
   mvinca-bandwidth filed #142 on Jul 13; #140/#143 landed the profile views and
   two-profile diff. Screenshot the diff view. Angle: the feature request → shipped loop.
3. **Contributor spotlight: slmingol's Docker/Podman PR (#172)** — only post this *after*
   you've reviewed it. Frames TT as a project where infra contributions land, and gives
   you a reason to prioritize the review.

Feature-Friday note: 12 human PRs merged — loop telemetry, Hermes profiles, agent
feature flags, three same-week bug fixes. Plenty for the announcement thread.
