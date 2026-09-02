# Weekly Digest — 2026-08-02

_Compared against weekly-digest-2026-07-26.md._

## Metrics

| Metric | Value | Δ vs last digest |
|---|---|---|
| Stars | **293** | +10 (283 → 293) |
| Open issues | **10** (#225, #224, #223, #222, #221, #198, #145, #65, #61, #45) | +5 (5 → 10) |
| Open PRs | **29** | +7 (22 → 29) |
| Merged this week | ~8 PRs (#202, #217, #216, #215, #213, #200, #199, #192 + #227 pricing bot) | — |
| Issues closed this week | **0** | — |
| New PR contributors | 3 — **hwantage** (#229), **octo-patch** (#218), **Jiaocz** (#203) | +2 |

Two flags this week. **Star growth decelerated hard: +10 vs last week's +29** —
first slowdown after three accelerating weeks. And **issues went 5 → 10 with zero
closed**: Yagnasena1999 filed a five-issue bug audit (#221–#225) on Aug 1, none
yet acknowledged. Open-PR count crept to 29, driven by a 7-PR dependabot batch
(Jul 28, #205–#211) and three new external PRs — not real review throughput.

## This week's activity (Jul 26 – Aug 2)

Mostly a docs / fix / hardening week, not a feature push. Only one real feature landed:

- **#202 merged (feat)** — `/goal` telemetry for all four agents that ship it:
  captures agent *intent*, not just tokens. This is the week's headline feature.
- **#217 merged (docs)** — product demo video now on the landing page + docs.
- **#215 merged (fix)** — OpenCode channel-suffixed DBs (`opencode-<channel>.db`) now read.
- **#213 merged (docs+fix)** — ban session URLs + machine identifiers from telemetry;
  fix Windows project names. A privacy/hygiene fix.
- **#199 / #216 merged (docs)** — issue-brief skill; loops documentation.
- **#200 / #192 merged** — container follow-ups from the Docker work landed
  (forward `TT_AUTH_TOKEN`, container run guide) — last week's open items, now closed.
- **Bug audit opened** — Yagnasena1999's #221–#225: cost undercounting on cache-read
  tokens (#224) and three data-loss bare-except bugs (Codex #221, Cline #222, Hermes
  #223). These are substantive, not noise — treat as a triage priority.

## Action items (need a reply)

- **#229 — hwantage PR** (Antigravity trace-parser fix, **0 comments**, first-time
  contributor, opened Aug 2): review promptly — new contributors churn if ignored.
  → https://github.com/VasiHemanth/tokentelemetry/pull/229
- **#221–#225 — Yagnasena1999 bug audit** (**0 comments each**): acknowledge and
  triage. #224 (cost undercount) and #221/#222/#223 (data-loss) are real.
  → https://github.com/VasiHemanth/tokentelemetry/issues/224
- **#203 — Jiaocz "Single Port Mode" PR** (0 comments, opened Jul 27): this is the
  implementation of their own #198 request — review or give direction.
  → https://github.com/VasiHemanth/tokentelemetry/pull/203
- **#218 — octo-patch MiniMax summarizer PR** (2 comments, external): has engagement;
  push to accept/decline. → https://github.com/VasiHemanth/tokentelemetry/pull/218
- **#61 — nujovich hermes-telemetry listing** (**0 comments, ~8 weeks — flagged
  repeatedly**): a one-line reply clears months of silence.
  → https://github.com/VasiHemanth/tokentelemetry/issues/61
- **#85 — Yagnasena1999 efficiency PR** (~55 days stale): nudge or close.
  → https://github.com/VasiHemanth/tokentelemetry/pull/85
- **#45 — ddiall mmmodels FYI** (4 comments, resolved-ish): can likely close.
- **Dependabot sweep**: ~13 open (#205–#211 new Jul 28 batch + #188, #161, #160,
  #157, #153, #151). #160/#157 are the parked TS 5.9→7.0 majors — batch in one sitting.
- **Own draft backlog**: 9 drafts (#230, #228, #187, #180, #171, #146, #138, #124,
  #121) + 2 non-draft (#184, #112). Merge or mark clearly WIP.

## Next week's content angle: Visibility week

Rotation: Money (Jul 6–12) → Visibility (Jul 13–19) → Community (Jul 20–26) →
Money (Jul 27–Aug 2) → **Visibility (Aug 3–9)**. This week's merges hand you a
clean visibility story about *intent and traces*, not just cost:

1. **"What was your agent actually trying to do?"** — #202 `/goal` telemetry.
   Screenshot the goal view across the four agents that emit it. Angle: tokens tell
   you *how much*; goals tell you *what for*. Visibility into intent is the new layer.
2. **"Watch the whole run."** — reshare the #217 product demo now on the landing
   page as a 20–30s trace-walkthrough GIF: session → tool calls → reasoning → cost.
3. **"Visibility that never leaks."** — #213 (session URLs + machine identifiers
   banned from telemetry) tied to the 100%-local frame. Plain point: full trace
   detail, none of it phones home or carries identifiers.

Feature-Friday note: lighter week — 1 feature (#202), plus docs, an OpenCode fix,
a privacy fix, and the container follow-ups. If the thread feels thin, lead with
`/goal` telemetry and frame the rest as "hardening week: 8 PRs, here's what's next."

---
_Methodology: stars 293 from the live repo page counter (aria-label "293 users
starred") vs prior digest 283; open issue/PR counts enumerated from the full
open-items list (10 issues, 29 PRs); merged-this-week and "0 issues closed" from
GitHub search (`is:merged merged:>=2026-07-26` = 10 incl. two Jul-26 straddlers;
`is:issue is:closed closed:>=2026-07-26` = 0). Point-in-time, Sun 2026-08-02._
