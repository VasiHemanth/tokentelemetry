---
type: Analysis
status: proposed
title: How to prove the brain saves tokens, ranked approaches
description: Depth-and-breadth assessment of eight measurement approaches, grounded in a real 2-arm pilot on education_video and a 51-session trace audit; adherence, not wiki quality, is the current bottleneck.
tags: [plugin, benchmarks, token-savings, adherence, methodology]
timestamp: 2026-07-06
resource: docs/wiki/ideas/prove-brain-token-savings.md
---

# How to prove the brain saves tokens, ranked approaches

Analysis saved from the 2026-07-06 research session that assessed
[Prove the brain saves tokens](../ideas/prove-brain-token-savings.md).
Eight candidate approaches were enumerated, a real pilot experiment and a
historical trace audit were run, and two adversarial reviews (experimental
methodology; product honesty) attacked the draft ranking. Body is a snapshot;
only `status` may change.

## Evidence gathered

**Pilot A/B (education_video, 2026-07-06).** Two identical copies of the
repo (~4.8MB source), one with its compiled 18-page wiki plus the
CLAUDE.md/AGENTS.md pointer block, one stripped. Six questions (four
wiki-covered, one partial, one uncovered), headless sonnet sessions,
`--max-turns 25`; replicate 2 partially killed by plan session limits
(16 valid sessions, ~$5).

| q | plain $ / turns | wiki $ / turns | wiki reads | delta |
|---|---|---|---|---|
| q1 playbook | .405 / 6 | .416 / 9 | 0 | wiki worse (both reps) |
| q2 decision | .364 / 10 | .452 / 14 | 0 | wiki worse (both reps) |
| q3 subsystem | .283 / 7 | .237 / 8 | 2 | wiki better |
| q4 convention | .404 / 15 | .223 / 9 | 3 | wiki halves cost, cache reads -62% |
| q5 partial | .218 / 7 | .201 / 5 | 0 | noise |
| q6 uncovered | .351 / 6 | .303 / 6 | 0 | noise |

Both arms answered all six questions correctly (scored against
independently read ground truth), so correctness could not discriminate.

Findings that survive small n (existence proofs, not effect sizes):

- **Adherence is the bottleneck.** 4 of 6 questions never consulted the wiki
  despite the pointer block and direct page coverage. Where ignored, the
  wiki arm was consistently equal-or-worse (pointer overhead without
  benefit); where consulted, it won both times, once halving cost
  (turns 15 to 9).
- **The saving mechanism is avoided turns, not avoided file bytes.** The
  whole wiki is ~13.5k tokens (median page ~560); q4's win came from six
  fewer turns, each avoided turn skipping a re-read of the growing context
  (446k fewer cache-read tokens). Savings therefore scale with context and
  repo size; a small repo is the wrong regime to benchmark in.
- **Dollar cost is not a usable primary metric.** Same-condition replicates
  varied 3x on prompt-cache state alone. Turns, tool calls, and cache-read
  volume are steadier (a credible effect needs ~15-20 paired replicates per
  question on turns; 100+ on dollars).
- **Verification tax.** One wiki session re-verified pages against code per
  the map-not-testimony rule, nearly erasing its win. Correct behavior, but
  it caps savings on small repos and must be priced into expectations.

**Trace audit (51 historical sessions, this repo + education_video).**
Zero sessions ever consulted a wiki (the TT wiki lives on an unmerged
branch), so observational metrics have no data yet. Exploration is 40-57%
of tool calls once Bash-carried searching is counted; the corpus contains
zero Grep/Glob tool calls, so wiki-read detection must parse Bash command
strings. `backend/main.py` was read 119 times across 16 sessions, the
single clearest re-read-waste signal. Raw JSONLs get pruned (education_video
kept one file), so tool-level classification must persist at scan time;
durable history already keeps the aggregates.

## The ranked approaches

No single approach answers everything, but one thing beats all in
sequence: fix and measure routing before measuring savings. Measuring
savings of a wiki agents do not open measures a discovery bug and will
"prove" zero.

1. **Adherence experiment (run first).** Manipulate the routing mechanism —
   pointer-block wording/placement, index-in-pointer, and the skillsmith
   skill's wiki-first section as its own arm — with a binary outcome:
   did the session consult the wiki on a covered question. Binary outcomes
   are cheap (~20-25 runs per arm detects 30% to 70%); this also answers
   the idea's skillsmith doubt. Gate: no savings benchmark until a variant
   reaches roughly 4-of-6 adherence.
2. **Scanner-side session classification, then the honest in-product
   panel.** Persist per-session wiki-touch flag, exploration share, and top
   re-read files into the durable history at scan time (parsing Bash
   commands, not just Read paths). On top of it ship only §9-legal copy:
   build cost (already shipped), "N of M sessions read the wiki since
   build", within-period wiki-touch vs non-touch comparison with the
   selection-bias disclosure, and past-spend re-read facts ("you spent X
   tokens re-reading these files"). Never a payback number:
   `build_cost / saving` is a causal claim in arithmetic clothing and §11
   bans it; zero and negative deltas render identically.
3. **One controlled benchmark campaign (after routing works).** Large repo
   (this one, where the 119x re-read lives), 2x2 pointer-x-wiki factorial
   plus a wiki+skill arm; questions sampled from historical session prompts
   (not curated against the wiki); intention-to-treat pre-registered;
   primary metrics turns/tool calls/cache-read volume with cold-cache
   control; 3+ replicates; checkpoint-and-resume harness (plan limits kill
   long runs). One published campaign with method, rerun only when routing
   mechanics change, never per release. The causal payback number may exist
   exactly once, here, clearly labeled benchmark-measured.
4. **Re-read waste card (pre-build, observational).** The §8 S1 Knowledge
   card powered by the same scanner data: past spend only, named files,
   no counterfactual ("could save you") phrasing. Doubles as compile-queue
   prioritization input.
5. **Maintainer-only query suite (compiler-regression cadence).** Fixed
   question sets with ground truth on 1-2 reference repos, run when the
   compiler or profiles change, never per compile and never on user
   machines. Its uncoverable-question output is the evidence for the
   domain-profile doubt; the profile ablation experiment is deferred until
   a real census visibly straddles profiles.

Deferred: stale-wiki harm arm (meaningless while adherence is low; the
staleness badge and untrusted-page rule ship without it), profile ablation
(see 5), any live per-session wiki-hiding on user machines (hostile, never).

## Consequences for existing plans

- Build-order step 6 (skillsmith last) inverts: skillsmith is the routing
  hypothesis under test in approach 1.
- The idea page's "compare against comparable pre-brain sessions" is
  unimplementable as written (before-population tool detail is pruned;
  zero historical wiki reads); the shipped comparison is within-period
  wiki-touch vs non-touch with disclosure.
- Add to the never list: no benchmark LLM sessions launched on user
  machines; no auto-tuning of pointer/skill text from measured adherence;
  no marketing savings claim until the published campaign exists.

## Related

- [Prove the brain saves tokens](../ideas/prove-brain-token-savings.md):
  the idea this analysis assesses.
- [Delegation and ecosystem telemetry](../subsystems/delegation-telemetry.md):
  the scanner capabilities approach 2 extends.
- Design doc §9/§11 (`resource:` on the idea page) supply the honesty
  constraints the ranking enforces.
