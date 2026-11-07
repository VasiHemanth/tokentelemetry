# ADR-0005: Report OMP session cost verbatim, not recomputed

- **Status:** Proposed
- **Date:** 2026-10-16
- **Deciders:** maintainer
- **Related:** [OMP integration design](../design/omp-integration.md), [ADR-0004](0004-qoder-credits-as-native-unit.md)

## Context

TokenTelemetry derives each session's cost from local agent logs. For most
agents it recomputes cost from the recorded token counts through
`backend/pricing.py` (`calculate_cost`) rather than trusting any number the
agent writes.

OMP (Oh My Pi) session files carry both halves of that input. Every assistant
turn records per-turn token counts (`message.usage.input`, `output`,
`cacheRead`, `cacheWrite`, `totalTokens`) and a per-turn cost object
(`message.usage.cost.total`). The cost is already metered.

The model identifier on those turns is the problem. OMP records a
gateway/router alias — a "combo" name — not an upstream vendor model id, and
the true upstream model is not written anywhere in the session file. Those
alias names appear in no pricing table, so `calculate_cost` would miss every
lookup and fall through to the generic `_default` rate, producing a dollar
figure the user was never billed — a fabricated cost.

In practice most OMP traffic is routed through a free or subscription gateway,
so OMP itself records a `cost.total` of `0` for those turns.

The precedent that matters is ADR-0004: a zero with no reason attached is
indistinguishable from a bug, and a guessed number is worse than either.

## Decision

We will report the recorded `message.usage.cost.total` — summed across the
session's assistant turns — **verbatim**, and never recompute OMP cost with
`calculate_cost`. The session carries `cost_source: "reported"` so downstream
surfaces can tell a recorded cost apart from an estimated one. A recorded `0`
is a legitimate, honest value, handled by the same principle as ADR-0004: a
zero with its reason attached, never a fabricated figure.

## Alternatives considered

- **Recompute with `calculate_cost` on the recorded model alias** — rejected:
  the alias names are absent from the pricing tables, so every turn would land
  on the generic `_default` rate and invent a cost.
- **Resolve the alias to an upstream model via the router's own local
  database** — rejected: it depends on a third-party tool's private store, the
  join back to individual OMP turns is not exact, and reading another product's
  database is outside the "read the agent's own logs" model.
- **Estimate from token counts at a generic blended rate** — rejected: it
  fabricates a number.

## Consequences

- ✅ Nothing is fabricated. The cost shown for OMP is one OMP wrote.
- ✅ `cost_source: "reported"` lets every surface distinguish measured cost
  from an estimate without new machinery.
- ⚠️ The OMP tile and panel may legitimately show `$0` for free-gateway or
  subscription-routed traffic. That is correct, not a defect.
- ⚠️ Cost accuracy for OMP is bounded by how completely OMP itself meters
  cost; TokenTelemetry adds and infers nothing.
- 🔁 If a future OMP version records upstream model identity in its session
  files, recomputation against the pricing tables could be revisited.
