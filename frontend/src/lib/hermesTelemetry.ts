"use client";

import { api } from "./api";

// Mirrors the backend payload returned by GET /hermes/telemetry.
// Field names are wire-format: a typo here type-checks fine and breaks at
// runtime, so keep them byte-identical to the endpoint.

/** How a session's dollar figure was arrived at.
 *  `zero-marginal` is a priced answer that happens to be $0 (local model, or a
 *  model/endpoint listed in power.json subscriptionModels). It is a positive
 *  claim about marginal cost, not a missing value like `unpriced`, and it must
 *  never be rendered as an API-equivalent dollar figure. */
export type CostStatus =
  | "provider-reported"
  | "provider-estimated"
  | "tt-computed"
  | "zero-marginal"
  | "unpriced";

/** Canonical session-outcome buckets. Anything Hermes reports that isn't in
 *  the backend mapping table lands in "unknown" and keeps its raw string. */
export type OutcomeBucket =
  | "completed"
  | "interrupted"
  | "timed_out"
  | "continued"
  | "reset"
  | "errored"
  | "unknown";

export interface OutcomeCount {
  outcome: string;
  count: number;
  /** Already a percentage (36.4 means 36.4%), not a 0..1 fraction. */
  pct: number;
}

export interface UnknownOutcome {
  raw: string;
  count: number;
}

export interface OutcomeBySource {
  source: string;
  total: number;
  /** bucket name -> count; sparse, only non-zero buckets appear. */
  buckets: Record<string, number>;
}

export interface OutcomeByModel {
  model: string;
  total: number;
  buckets: Record<string, number>;
}

export interface HermesOutcomes {
  buckets: OutcomeCount[];
  unknown_raw: UnknownOutcome[];
  /** 0..1 fraction; multiply by 100 to display. */
  completion_rate: number;
  by_source: OutcomeBySource[];
  /** Capped at the 10 largest models, so this can sum to less than
   *  `session_count`. Compare against `models_total` before trusting it as a
   *  full breakdown. `by_source` is never capped. */
  by_model: OutcomeByModel[];
  /** How many distinct models exist before the `by_model` cap. Older backends
   *  don't send it; fall back to `by_model.length`. */
  models_total?: number;
}

export interface HermesCost {
  total_usd: number;
  /** Portion of `total_usd` from sessions Hermes marked cost_status='included',
   *  i.e. covered by a flat subscription. A subset of the total, not an extra
   *  amount: never add it to `total_usd` or render it as its own bucket. */
  subscription_included_usd: number;
  /** Session counts per provenance. */
  confidence: Record<CostStatus, number>;
  /** Dollars per provenance. `unpriced` is always 0 and means "not captured",
   *  not "free". Never render it as a dollar figure. */
  usd_by_confidence: Record<CostStatus, number>;
}

export interface LatencyByModel {
  model: string;
  calls: number;
  /** null when the model has no timed API calls. Never 0-as-missing. */
  avg_s: number | null;
  p95_s: number | null;
}

export interface HermesLatency {
  captured_sessions: number;
  uncaptured_sessions: number;
  api_calls: number;
  /** null (not 0) when api_calls === 0. */
  avg_s: number | null;
  p50_s: number | null;
  p95_s: number | null;
  by_model: LatencyByModel[];
}

export interface ToolStat {
  tool: string;
  calls: number;
  failures: number;
  /** 0..1 fraction; multiply by 100 to display. */
  failure_rate: number;
  /** null when no duration was captured for the tool. Never 0-as-missing. */
  avg_duration_s: number | null;
}

export interface HermesTools {
  /** false when no tool lines were parsed out of the logs; both lists are []. */
  captured: boolean;
  top_by_calls: ToolStat[];
  /** Only tools with calls >= 3; a single failed call isn't a signal. */
  top_by_failure_rate: ToolStat[];
}

export interface HermesLogCoverage {
  /** Log file names actually read, e.g. ["agent.log.1", "agent.log"]. */
  files_read: string[];
  sessions_with_log: number;
  sessions_total: number;
}

export interface HermesTelemetryData {
  available: true;
  session_count: number;
  outcomes: HermesOutcomes;
  cost: HermesCost;
  latency: HermesLatency;
  tools: HermesTools;
  log_coverage: HermesLogCoverage;
}

/** Union, not an optional-field interface: the endpoint returns nothing but
 *  `{available: false}` when no Hermes DB exists, so the guard is mandatory. */
export type HermesTelemetry = { available: false } | HermesTelemetryData;

export const getHermesTelemetry = () => api<HermesTelemetry>("/hermes/telemetry");

// --- Display helpers -------------------------------------------------------

/** Order the cost split is always rendered in (most trustworthy first). */
export const COST_STATUS_ORDER: CostStatus[] = [
  "provider-reported",
  "provider-estimated",
  "tt-computed",
  "zero-marginal",
  "unpriced",
];

/** Visible text for a status. These are the labels users read; the raw wire
 *  keys are never rendered. Both maps are total Records on purpose: adding a
 *  status to the union fails the build until it has a label and a hint. */
export const COST_STATUS_LABELS: Record<CostStatus, string> = {
  "provider-reported": "reported by Hermes",
  "provider-estimated": "estimated by Hermes",
  "tt-computed": "priced by TokenTelemetry",
  "zero-marginal": "no marginal cost",
  unpriced: "not captured",
};

export const COST_STATUS_HINTS: Record<CostStatus, string> = {
  "provider-reported": "Hermes recorded the actual charge for this session.",
  "provider-estimated": "Hermes recorded its own estimate, not a billed amount.",
  "tt-computed": "TokenTelemetry priced the token counts locally.",
  "zero-marginal":
    "TokenTelemetry priced it and the answer is $0: the model runs locally or is covered by a subscription you already pay for.",
  unpriced: "No cost and no token counts to price. Not captured, not zero.",
};

const OUTCOME_LABELS: Record<OutcomeBucket, string> = {
  completed: "completed",
  interrupted: "interrupted",
  timed_out: "timed out",
  continued: "continued",
  reset: "reset",
  errored: "errored",
  unknown: "unknown",
};

/** Human label for a bucket. An unrecognised bucket is treated as unknown so a
 *  future backend value can never masquerade as a known outcome. */
export function outcomeBucketLabel(outcome: string): string {
  return OUTCOME_LABELS[outcome as OutcomeBucket] ?? "unknown";
}

/**
 * One-line split of a sparse bucket map, e.g. "13 continued, 8 completed".
 * Ordered by count desc then bucket name, so the same data always renders the
 * same way. Zero-count buckets never appear (the backend omits them).
 */
export function outcomeBucketSplit(buckets: Record<string, number>): string {
  return Object.entries(buckets)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([bucket, n]) => `${n} ${outcomeBucketLabel(bucket)}`)
    .join(", ");
}

/**
 * Label for one session's outcome. Unmapped values render as
 * `unknown: <raw>` so an outcome nobody has classified yet is visible rather
 * than silently folded into a bucket it doesn't belong to.
 */
export function outcomeLabel(outcome?: string | null, raw?: string | null): string | null {
  if (!outcome) return null;
  const known = outcome in OUTCOME_LABELS && outcome !== "unknown";
  if (known) return OUTCOME_LABELS[outcome as OutcomeBucket];
  return raw ? `unknown: ${raw}` : "unknown";
}
