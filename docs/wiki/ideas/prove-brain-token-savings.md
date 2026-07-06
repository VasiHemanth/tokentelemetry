---
type: Idea
status: captured
title: Prove the brain saves tokens
description: Benchmark the brain-init/compile/skillsmith pipeline and surface a payback metric; replace the domain-profile menu with a census-driven dynamic schema.
tags: [plugin, benchmarks, token-savings, domain-profiles, skillsmith]
timestamp: 2026-07-06
resource: docs/design/tokentelemetry-plugin.md
---

# Prove the brain saves tokens

Captured from a maintainer prompt, 2026-07-06.

## The pipeline being questioned

`/brain-init` picks one domain profile (fullstack-app, research-data,
generic), `/brain-compile` builds the OKF wiki, a pointer block lands in
CLAUDE.md/AGENTS.md, and `/skillsmith` generates the per-project skill. The
whole chain rests on an unproven claim: that agents reading the wiki spend
fewer tokens than agents re-exploring the codebase.

## Doubt 1: domain profiles are too restrictive

One profile chosen up front fixes the entire page-type table. Real projects
straddle domains; a fullstack app with a research pipeline gets squeezed into
whichever profile was picked.

Sketch: treat profiles as starting kits, not boxes. `/brain-init` composes the
page-type table from the project census, mixing rows across profiles or
proposing new ones, instead of forcing one choice.

## Doubt 2: savings are asserted, never shown

Sketch of the fix, in three parts:

1. **A/B benchmark.** A fixed task suite per repo, run with the brain vs
   without, and separately brain + skillsmith skill vs neither. Compare total
   tokens, wall time, correctness. Publish method and results so the claim is
   verifiable.
2. **In-product payback metric.** The Second Brain tab already shows the build
   cost ("built with N tok"). Add the other side: compare wiki-consulting
   sessions against comparable pre-brain sessions in the same project.
   TokenTelemetry already has per-session tokens and skill attribution
   (see [Delegation and ecosystem telemetry](../subsystems/delegation-telemetry.md))
   to tell the two populations apart.
3. **Skillsmith in the matrix.** Measure whether the generated skill, the
   wiki, or the combination carries the savings.

## Open questions

- What task suite is fair? Repo-specific tasks favor the wiki; generic tasks
  may never touch it.
- How to attribute savings in sessions that mix wiki reads with raw
  exploration.
- Staleness risk: a wrong wiki can cost more than no wiki. The benchmark
  should include a stale-wiki arm.

## Refinement 2026-07-06

A research pass ran a real pilot (education_video, 2 arms, 16 sessions) and
a 51-session trace audit, then ranked the measurement approaches:
[How to prove the brain saves tokens, ranked approaches](../analyses/brain-savings-approaches.md).
Headline: adherence, not wiki quality, is the current bottleneck (agents
ignored the wiki on 4 of 6 covered questions; when they read it, one answer
halved in cost). Sequencing changes: routing experiment first, savings
benchmark after; the payback number as sketched here is §11-banned in
product and survives only as a published benchmark result.

## Refinement 2026-07-06 (later): adherence experiment ran

The routing experiment the analysis ranked first was executed the same day
(3 arms x 4 covered questions x 2 replicates, 24 sessions, education_video
copies): current pointer block 5/8 runs consulted the wiki (median 11 turns,
mean $0.30); pointer with the wiki index embedded 8/8 (median 4 turns, mean
$0.14, answers still correct and still verifying against source); pointer
plus a skillsmith-generated skill 2/8, with the skill invoked in 0 of 8 runs
despite being loaded (verified available). Turn distributions for the index
arm vs baseline do not overlap (3-8 vs 9-12). Direction for the plugin:
embed the index (or a distilled page map) in the pointer block, and rethink
skillsmith's role; a skill described as optimization advice never fires on
ordinary questions, so routing cannot live there.

## Refinement 2026-07-06 (later still): drop the profile menu entirely

Doubt 1 sharpened from "starting kits, not boxes" to removing the
three-profile menu altogether. The maintainer's call: the supplied context
(raw sources, census) stays as is, but wiki generation should derive the
page-type table and folder structure dynamically instead of picking from
fullstack-app / research-data / generic.

Evidence since the original capture supports it: TT itself, the reference
project for `fullstack-app`, needed a `harness` type the profile did not
ship (BRAIN.md was the escape hatch, so the schema is already per-project
in practice); and the proven routing win (index-in-pointer, 8/8 adherence)
is schema-agnostic, so a dynamic taxonomy does not threaten it.

Agreed shape (option B of three discussed):

- A universal skeleton every project gets with no LLM discretion:
  `Overview`, `Decision`, `Playbook`, `Convention`, index/log/manifest,
  OKF rules, and a non-negotiable redaction core copied verbatim into
  every generated BRAIN.md. Redaction is never LLM-derived.
- `profile_census.py` changes job: its facts (extension histogram,
  framework markers, tree, doc inventory) feed an LLM proposal of 3-8
  domain-specific page types, each with a directory, `one_page_per`
  granularity, and evidence of at least 2-3 expected pages.
- The AskUserQuestion gate stays, showing the proposed table instead of a
  three-item menu. BRAIN.md remains the durable contract: only
  `/brain-init` derives; compiles and ingests never re-derive.
- The three profile YAMLs demote to few-shot exemplars in the brain-init
  prompt; explicit custom profiles stay supported as overrides.

Testable with the existing harness: compile education_video under a forced
`generic` profile vs a census-driven schema, run the same question set,
compare adherence, turns, correctness.

## Refinement 2026-07-06 (round 2): A/B on the census-schema wiki ran

The A/B benchmark sketched in Doubt 2 was executed against the regenerated
education_video wiki (28 pages, census-derived schema, page-map pointer
block): 2 arms (wiki + pointer vs no wiki, pointer stripped) x 7 questions
(round-1 set plus one targeting the new Domain pages) x 2 replicates, 28
sessions, all valid, all correct on source-verified key facts in both arms.

Results by coverage class: where the wiki actually answers the question
(3 of 7), brain halved both turns (4.0 vs 8.2 mean) and cost ($0.14 vs
$0.28); where the details live in CLAUDE.md that both arms read anyway, no
advantage; on the one uncovered code-path question the wiki cost ~2 extra
turns (the wiki tax is real but small); overall cost -18% ($3.03 vs $3.70).
Adherence of the shipped pointer block: 12/14, and 12/12 on questions that
do not name a source file (both misses were the question naming
`scripts/research.js`, where going straight to the file is rational). The
new schema's pages earned their place: the tracker-database data-store page
flipped last round's partially-covered DB question to a 3-turn half-cost
answer. Correctness never degraded; brain answers still verified against
source and were deeper on one question (found the posting CLI mismatch).

## Related

- [How to prove the brain saves tokens, ranked approaches](../analyses/brain-savings-approaches.md):
  the 2026-07-06 assessment of this idea's measurement sketch.
- [Graphify vs the TokenTelemetry plugin](../analyses/graphify-vs-tt-plugin.md):
  earlier analysis of prior-knowledge overlap.
- The plugin design doc (`resource:` above) sketches a before/after metrics
  panel in §9; this idea asks for the rigor behind that panel.
