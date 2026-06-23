"use client";

import { api } from "./api";

// ---- Budget contract (see backend harness_config + /budgets endpoints) ----
//
// A budget is OBSERVATIONAL: TokenTelemetry reads logs after the fact and
// cannot cap a running agent. A budget only powers threshold alerts (and,
// later, burn-rate forecasts).
//
// Scope is a *filter object*, not a single enum — a budget applies to the
// sessions matching ALL present filter keys:
//   {}                                  -> global
//   { project }                         -> whole project, every agent
//   { project, agent }                  -> one agent on one project
//   { agent } / { model }               -> that agent / model everywhere

export type BudgetPeriod = "monthly" | "weekly" | "rolling_30d";
export type BudgetLimitType = "usd" | "tokens";

export interface BudgetFilters {
  project?: string;
  agent?: string;
  model?: string;
}

/** A stored budget definition (what the editor reads/writes). */
export interface Budget {
  id: string;
  filters: BudgetFilters;
  period: BudgetPeriod;
  limit_type: BudgetLimitType;
  limit_value: number;
  /** Fractions of the limit that raise an alert, e.g. [0.8, 1.0]. Sorted asc. */
  thresholds: number[];
  enabled: boolean;
}

/** A budget enriched with current usage — what GET /budgets returns. */
export interface BudgetStatus extends Budget {
  /** Spend so far this period (USD or token count, per limit_type). */
  used: number;
  /** used / limit_value (0..n). */
  fraction: number;
  /** Highest crossed threshold, or null if under the lowest. */
  alert_level: number | null;
  sessions_in_window: number;
  /** ISO datetime the current period started (local time). */
  window_start: string;
  /** ISO datetime the period resets, or null for rolling windows. */
  reset_at: string | null;
  /** Per-agent split of spend within the window, richest first. */
  breakdown_by_agent: Record<string, { cost: number; tokens: number }>;
}

export const getBudgets = () =>
  api<{ budgets: BudgetStatus[] }>("/budgets").then((r) => r.budgets);

export const putBudgets = (budgets: Budget[]) =>
  api<{ ok: boolean; budgets: BudgetStatus[] }>("/budgets", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ budgets }),
  }).then((r) => r.budgets);

// ---- Helpers shared by the card / pill / banner ----

export const DEFAULT_THRESHOLDS = [0.8, 1.0];

/** A budget is "for this project" if its only scoping is project (+ optional agent). */
export function isProjectBudget(b: BudgetFilters, projectPath: string): boolean {
  return b.project === projectPath && !b.model;
}

/** Tone bucket for progress UI, mirroring the cloud-budget green/amber/red model. */
export function budgetTone(fraction: number): "ok" | "warn" | "over" {
  if (fraction >= 1) return "over";
  if (fraction >= 0.8) return "warn";
  return "ok";
}

/** localStorage key for per-budget, per-period alert dismissal. */
export function budgetDismissKey(b: BudgetStatus): string {
  return `tt-budget-dismissed:${b.id}:${b.window_start}`;
}

export const BUDGET_ALERT_DISMISS_PREFIX = "tt-budget-dismissed:";
