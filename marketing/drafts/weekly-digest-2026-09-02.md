# Weekly Digest — 2026-09-02

_Compared against weekly-digest-2026-08-24.md._

## Metrics

| Metric | Value | Δ vs last digest |
|---|---|---|
| Stars | **341** | +16 (325 → 341) |
| Open issues | **14** | +2 (12 → 14) |
| Open PRs | **27** | −4 (31 → 27) |
| Merged this week | **19** PRs (#319, #320, and 17 others) | +16 vs last digest's 3 |
| Issues closed this week | **2** (#303, #304) | same as last digest |
| New contributors | **Pauliehedron** (#303 DeepSeek pricing, #304 Codex/Cline cost bug) | — |

Biggest shipping week since launch. Two flagship features landed: live plan
limits for every supported coding agent (#319) and the macOS menu bar + Electron
desktop shell (#320). Star growth doubled vs last week (+16 vs +8), likely driven
by the plan-limits feature gaining visibility on social. Pauliehedron filed two
thorough, well-researched bug reports (#303, #304) — both closed within days.
The 19 merged PRs include the plan-limits and desktop-shell stacks plus
dependabot catch-up.

## This week's activity (Aug 25 – Sep 1)

- **#319 merged (feat)** — VasiHemanth: live plan limits for every supported
  coding agent. Sidebar gauge, per-provider quota bars with reset countdowns,
  subscription-aware pricing. The headline feature of the week.
- **#320 merged (feat)** — VasiHemanth: macOS menu bar (rumps status item with
  worst-window display, LaunchAgent lifecycle) + local Electron desktop shell.
  Merged same day as opened.
- **#304 closed (bug)** — Pauliehedron: Codex and Cline scanners never passed
  provider/endpoint to `calculate_cost`, causing subscription sessions to be
  mispriced. Fixed within 2 days.
- **#303 closed (bug)** — Pauliehedron: DeepSeek V4 pricing tables were stale
  (40–60% undercount). Fixed within 1 day.
- **#322 opened (chore)** — dependabot: website minor/patch bumps (8 packages
  including Next.js 16.3.3 security fixes).
- **#298 open (enhancement)** — VasiHemanth: subagent sessions inflate the
  session list (205 cards for 8 actual conversations on Grok Build). Detailed
  design proposal, 1 comment, still open.

## Action items (need a reply)

- **#290 (Rub3nCT)** — Windows path dedup, first-time contributor, still 0
  comments (~2 weeks). Review or decline.
  → https://github.com/VasiHemanth/tokentelemetry/pull/290
- **#289 (hwantage)** — scrubber sync fix, 0 comments (~2 weeks).
  → https://github.com/VasiHemanth/tokentelemetry/pull/289
- **#298 (VasiHemanth)** — subagent session dedup, open. Decide scope and
  assign.
  → https://github.com/VasiHemanth/tokentelemetry/issues/298
- **#218 — octo-patch MiniMax summarizer PR**: ~6 weeks unreviewed.
  → https://github.com/VasiHemanth/tokentelemetry/pull/218
- **#203 — Jiaocz "Single Port Mode" PR** (impl of #198): ~8 weeks unreviewed.
  → https://github.com/VasiHemanth/tokentelemetry/pull/203
- **#322 (dependabot)** — Next.js 16.3.3 includes two critical RCE fixes.
  Merge promptly.
  → https://github.com/VasiHemanth/tokentelemetry/pull/322
- **Yagnasena1999 issues #225/#223/#222/#221**: still 0 comments (~5 weeks).
- **Own draft PRs**: #250, #231, #187, #184, #180, #171. Merge or close stale.

## Next week's content angle: Multi-agent week

Rotation: Money (Aug 24–30) → Visibility (Aug 31 – Sep 6) → **Multi-agent (Sep 7–13)**.

1. **"Your menu bar knows all your agents."** — The macOS menu bar (#320) pulls
   quota from every connected agent into one status item. Show the menu bar
   dropdown with Claude Code at 91%, Codex at 24%, and Grok's credit balance
   side by side. Angle: "one glance, every agent."
2. **"Plan limits across agents — why the bars look different."** — #319's
   per-provider gauge renders percentage bars for capped quotas and plain
   balances for credit-based ones (Codex). Explain *why* agents report limits
   differently and how TT normalizes them. Good Wednesday demo GIF.
3. **"Subagent sessions were hiding in your list."** — #298 describes 205
   phantom cards from 8 conversations. Even before the fix ships, the issue
   writeup itself is a compelling multi-agent story. Frame as "what happens
   when your agent spawns 25 sub-agents and each one gets a card."

Feature-Friday note: lead with **macOS menu bar (#320)** as the multi-agent
angle (all agents, one tray icon). Plan-limits (#319) is the deeper tech
story for the Wednesday demo.

---
_Methodology: stars 341 from the repo page aria-label; open issue/PR counts
from GitHub search totals (`is:issue is:open` = 14, `is:pr is:open` = 27);
merged-this-week = 19 from search (`is:pr is:merged merged:>=2026-08-26`);
issues-closed = 2 from search (`is:issue is:closed closed:>=2026-08-26`).
Point-in-time, Sun 2026-09-02._
