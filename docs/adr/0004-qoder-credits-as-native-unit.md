# ADR-0004: Report Qoder spend in credits, and its token counts as zero

- **Status:** Accepted
- **Date:** 2026-08-30
- **Deciders:** maintainer
- **Related:** [Qoder survey](../research/harness-survey/harness-qoder.md)

## Context

Qoder (Alibaba) is the first supported agent that records no token counts at
all. Every assistant turn writes a `usage` object in Anthropic's shape whose
`input_tokens`, `output_tokens`, `cache_read_input_tokens` and
`cache_creation_input_tokens` are all `0`, and puts the real figure in
`credits`. This held across all 22 assistant turns on the surveyed install, in
the CLI transcripts and in the IDE's own context snapshot alike.

The counts cannot be reconstructed. `context_usage_ratio` is a fraction of an
unknown denominator — `runtime-config.contextWindow` is `null` and the IDE's
`chat_session_context_usage` reports `maxTokens: 0`. Model ids are internal
(`qmodel_38max`, `qfmodel`) and the catalogue that would resolve them is
encrypted at rest, so there is no model to price against even if counts existed,
and no published credit-to-currency rate on disk.

Every number TokenTelemetry shows is denominated in tokens or dollars. A new
agent that has neither lands in surfaces that all assume they exist: the KPI
strip, agent and model distribution, the session list, the trace header,
analytics, and the billing and retention tables.

The precedent that matters is DeepSeek Harness. Its sessions once counted zero
because an optional codec was missing, and the zero looked exactly like a
correctly-scanned empty agent. The lesson was not "avoid zeros" — it was that a
zero with no explanation attached to it is indistinguishable from a bug.

## Decision

We will treat credits as Qoder's native billing unit and report its token counts
as an honest zero, with the reason attached wherever the zero appears.

Concretely: `tokens.total` is `0` and `cost` is `0.0`; `billing_mode` for qoder
is `subscription`, under which a `$0.00` API-equivalent cost is the correct
reading rather than a missing value (the same reading Hermes already ships);
credits ride in the per-session `qoder` blob and drive a meter on the agent's
panel; and the panel carries three `not_available` entries naming what is not
derivable and why — tokens, model identity, and encrypted session state.

Delegated spend is reported as `delegated_credits` with `tokens_recorded:
False`, because subagent spend is real but is not denominated in tokens.

## Alternatives considered

- **Derive pseudo-tokens from `context_usage_ratio`** — impossible, not merely
  inadvisable: the denominator is `null`/`0` in both stores. Anything produced
  this way would be invented.
- **Convert credits to dollars with a hardcoded rate** — Qoder publishes no rate
  locally, and a guessed one would flow into budgets, analytics and the cost
  KPI as though it were measured.
- **A user-configurable credit-to-dollar rate** — a real option and not
  rejected on merit, but it is a separate feature touching billing settings and
  every cost aggregate. Deferred rather than bundled into the integration.
- **Omit Qoder from cost surfaces entirely** — hiding an agent from analytics is
  worse than a zero that explains itself, and it would make Qoder's spend
  invisible rather than merely un-priced.

## Consequences

- ✅ Nothing is fabricated. Every figure shown for Qoder is one Qoder wrote.
- ✅ Credits, including the ~49% that goes to subagents, are visible — a
  parent-only view would halve the apparent cost of a session.
- ✅ The pattern generalises: a second credit-metered agent needs the same three
  pieces (native unit in the blob, `subscription` billing mode, an
  `not_available` entry), not new machinery.
- ⚠️ Qoder contributes `0` to fleet-wide token totals and dollar costs, so
  cross-agent comparisons understate it. This is accurate but easy to
  misread at a glance, which is why the reason travels with the number.
- ⚠️ Credits are not comparable to any other agent's unit, so Qoder cannot be
  ranked against Claude Code or Codex on cost.
- 🔁 Undoing this means either Qoder starts recording tokens, or we accept a
  user-supplied credit rate — at which point `billing_mode` moves off
  `subscription` and the `tokens` `not_available` entry is rewritten rather
  than removed.
