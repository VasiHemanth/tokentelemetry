---
type: Idea
status: captured
title: Prove the brain saves tokens
description: Benchmark the brain-init/compile/skillsmith pipeline and surface a payback metric; loosen domain profiles from boxes to starting kits.
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

## Related

- [How to prove the brain saves tokens, ranked approaches](../analyses/brain-savings-approaches.md):
  the 2026-07-06 assessment of this idea's measurement sketch.
- [Graphify vs the TokenTelemetry plugin](../analyses/graphify-vs-tt-plugin.md):
  earlier analysis of prior-knowledge overlap.
- The plugin design doc (`resource:` above) sketches a before/after metrics
  panel in §9; this idea asks for the rigor behind that panel.
