# Landing page vs docs as the front door of tokentelemetry.com

**Status:** ANALYSIS, decision recommended · **Date:** 2026-07-15 ·
**Method:** GA4 + Microsoft Clarity read via browser (windows below), then a
4-lens multi-agent analysis (conversion funnel, audience segments, docs-page
readiness against the repo, SEO/distribution risk) synthesized into options.

## Question

Should tokentelemetry.com keep its marketing landing page at `/`, or route
visitors straight to the docs Introduction so they "get more idea in a first
glance"?

## Answer

Keep the landing page at root; upgrade the docs Introduction into a proper
second front door (hybrid, option 3 below). The hunch has a direct test in
the data and fails it: the docs intro holds visitors 11 seconds versus the
homepage's 29, and it lacks the install command, social proof, and mobile
treatment that convert. What the hunch correctly detects is that the landing
page buries answers: FAQ is the single most-clicked element on the site while
sitting below where two thirds of visitors ever scroll.

## Evidence

Windows: GA4 Jun 17 to Jul 14 2026 (28d); Clarity last 30d as of Jul 15.
Traffic is launch-spike-driven (Reddit/Threads posts), not steady state.
Heatmap data is desktop-only. Revisit at steady state.

### Where users are

| Metric | Value |
|---|---|
| Sessions / active users (GA4, 28d) | 953 / 618 |
| Users touching `/` | 499 (81%), 29s avg engagement |
| Users touching `/docs/` intro | 52 (8.4%), 11s avg engagement |
| Entry pages (Clarity, 30d) | `/` 809; all docs pages combined ~210 (traces 67, intro 54, analytics 35, installation 26, supported-agents 26) |
| Homepage-to-docs continuation | ~7% (34 Docs-nav clicks / 499 homepage users) |
| Mobile share | ~45% (ChromeMobile 23.8% + MobileSafari 20.6%) |
| New users | 87.6% |

### What users do on the homepage (desktop heatmap, 429 views, 804 clicks)

| Rank | Element | Clicks |
|---|---|---|
| 1 | FAQ "Common questions" | 80 (9.95%) |
| 2 | Copy install command | 34 (4.23%) |
| 3 | Docs nav link | 34 (4.23%) |
| 4 | Dashboard | 33 (4.10%) |
| 5 | Windows install tab | 23 |

Scroll: 27% leave within the hero (15% depth), half gone by 30%, 36% reach
60% where the FAQ sits. Dead clicks in 16.06% of sessions (181). Rage clicks
0.98%. Performance 84/100, LCP 2.1s.

### Where traffic comes from (GA4, 28d)

| Source | Sessions | Engagement rate | Avg time |
|---|---|---|---|
| direct | 435 (45.7%) | 36.3% | 18s |
| reddit.com | 205 (21.5%) | 44.4% | 26s |
| l.threads.com | 114 (12%) | 41.2% | 17s |
| google organic | 93 (9.8%) | 55.9% | 28s |
| github.com | 21 | 52.4% | 48s |
| chatgpt.com | 13 | 76.9% | 44s |

Search is 97% branded ("tokentelemetry" variants, avg position 1.2);
non-brand queries are negligible. Microsoft Copilot cites the site 20 times
in 7 days, all 20 to the homepage URL (42.55% share of authority).

## Lens conclusions

1. **Funnel.** The landing page is earning its keep, not acting as a toll
   gate. Installs happen in the hero (~8% desktop copy rate vs 31 users on
   `/docs/installation` in 28 days), and docs are already a parallel
   entrance, not gated behind the homepage (67 of 69 traces visits are
   direct entries). The weakness is mid-page attrition and a buried FAQ.
2. **Audience.** No segment is better served by a root swap. Cold
   social/mobile skimmers (~36% of sessions, ~45% mobile) need the hero's
   instant orientation; intent-driven devs already deep-link into docs;
   branded-search returners hunt FAQ answers; LLM-referred visitors ground
   on the homepage URL.
3. **Docs readiness.** The intro page has the screenshot but no install
   command (link only), no live stars/proof, doc chrome as the mobile first
   screen, and no conversion tracking. Routing root there today would
   rebuild a landing page inside docs chrome and blind the install funnel.
4. **SEO/distribution.** A swap gambles the only AI-referral asset (20/20
   Copilot citations to `/`), the OG cards on the Reddit/Threads posts that
   drive a third of sessions, and branded navigational search, for no
   demonstrated upside on a statically exported site with no quick rollback.

## Options

| Option | Effort | Call |
|---|---|---|
| 1. Keep landing at root, reorder it (lift FAQ answers above the 30% scroll line, fix dead clicks) | S | do first |
| 2. Full swap: docs Introduction at root | L | rejected on the evidence above |
| 3. Hybrid: option 1 plus rebuild `/docs/` intro as a real second door (install one-liner with copy, framed screenshot, quick-start path) | M | **recommended** |

## Quick wins regardless of option

- Fix the install-command mismatch: `Hero.tsx` uses
  `raw.githubusercontent.com/.../install.sh`, `installation.mdx` uses
  `tokentelemetry.com/install.sh|ps1`. Two canonical commands in public copy.
- Move FAQ/objection answers (privacy, what does it collect) above the 30%
  scroll line; 80 clicks say that is what visitors hunt for.
- Audit the dead-click targets (16% of sessions click non-interactive
  elements).
- Add the install one-liner + copy button to `/docs/` intro; it is the #3
  entry page and currently the weakest page on the site.
- Single source of truth for the agent count ("13 agents" Hero chip vs 14
  names in the docs intro) and the install URL, consumed by both surfaces.
- Wire `track()`/`PageViewTracker` into the docs layout so docs-side
  conversion is measurable before any future routing decision.
- Optimize the 3200x3000 dashboard screenshot before reusing it above the
  fold anywhere else.

## Caveats

- Copy-install clicks are a proxy, not confirmed installs.
- Launch-spike traffic; segment mix will shift at steady state, when branded
  search and LLM referrals weigh more. Re-check these numbers then.
- Clarity undercounts browsers that block the tracker.
- GA4 and Clarity count sessions differently (953 vs 1127); cross-tool
  comparisons are directional.
