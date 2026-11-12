# ADR-0006: Compute waste signals from a cached transcript extraction pass

- **Status:** Proposed
- **Date:** 2026-11-12
- **Deciders:** maintainer
- **Related:** [Waste detection design](../design/waste-detection.md)

## Context

The evaluation plan has four tiers: efficiency signals, friction signals,
outcome signals per use case, and a local model-graded judge. Tier 1 is meant
to ship on data the app already reads, with the same code for every agent.

The session list scan cannot support it. It keeps per-session rollups, records
tool errors for Claude Code only, and records tool arguments for no agent.
Retry loops (identical consecutive calls) and repeated reads of the same file
both need arguments. Extending every scanner to carry them would touch the
most conflict-prone code in the repo and grow the scan every page depends on.

The on-demand transcript parse behind the session detail page already
normalizes most agents into two event shapes that include tool names,
arguments and results.

An earlier unmerged branch (`pr-85-intelligence`) scored sessions with a single
0 to 100 efficiency number built from output ratio, error count and turn count.
The number could not be explained to a user or checked against a transcript,
and its smell rules read session fields that no scanner populated.

## Decision

We will compute Tier 1 signals in a separate extraction pass over the existing
transcript parse, one session at a time, in a background worker, and cache the
result per session keyed by last activity time, total tokens and an extraction
version.

The cache stores counts and flag labels only. Prompt text, tool output,
command strings and file contents are never written. File paths are used in
memory to detect re-reads and are discarded.

Signals an agent's logs cannot support are reported as null with a per-agent
capability map, never as zero.

We will report named flags with published thresholds and the cost of flagged
sessions. We will not publish a composite score or a "wasted dollars" figure.

## Consequences

- The scanners and the scan cache version are untouched, so nothing existing
  is invalidated or slowed.
- Coverage is incremental. The first visit shows partial results and a
  coverage count while the worker catches up. The endpoint never blocks on
  parsing.
- Signal quality depends on each agent's detail parser. Agents whose parser
  yields text only get cost and turn metrics and "not recorded" for the rest.
- Tier 2 friction heuristics need user message text, which this same pass
  reads. They can be added as more counted labels without a new pipeline or a
  change to the privacy rule.
- "Per task" metrics use the session and the user turn as units, because the
  logs carry no task boundary. Tier 3 intent classification is the place to
  improve that.
- Thresholds are heuristics. They are returned by the endpoint and shown in
  the UI so a user can judge a flag against the rule that raised it.
