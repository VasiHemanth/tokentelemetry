"use client";

import { api } from "./api";

/** How a user pays for an agent — drives the cost label/disclaimer, not the math. */
export type BillingMode = "subscription" | "api" | "local" | "unknown";

/** How an agent's mode was arrived at. */
export type BillingSource = "user" | "detected" | "default";

export interface AgentBilling {
  mode: BillingMode;
  source: BillingSource;
  /** Raw auto-detected value, or null when no signal was found. */
  detected: BillingMode | null;
  /** Static fallback for this agent. */
  default: BillingMode;
  /** Human note on where detection looked (e.g. "~/.codex/auth.json"). */
  detect_source: string | null;
}

export interface BillingConfig {
  /** Keyed by agent id (only detected agents are present). */
  agents: Record<string, AgentBilling>;
  modes: BillingMode[];
}

export const getBillingConfig = () => api<BillingConfig>("/config/billing");

/** Set an agent's mode, or pass `null` to clear the override (revert to auto). */
export const setBillingMode = (agent: string, mode: BillingMode | null) =>
  api<BillingConfig>("/config/billing", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agent, mode }),
  });

// ---------------------------------------------------------------------------
// Drain-priority routes (/config/billing-route): which credit *bucket* pays,
// in what order, split by task type. Structure only (Stage 1) — pool fill
// meters need per-session task-type data and come later.
// ---------------------------------------------------------------------------

export type TaskType = "interactive" | "programmatic";

/** What the user pays at the margin while a bucket is active. */
export type BucketCharges = "included" | "api_rate" | "electricity";

export interface RouteBucket {
  id: string;
  label: string;
  charges: BucketCharges;
  task_types: TaskType[];
  /** Prepaid pool size in USD/month at API rates, or null = no dollar cap. */
  pool_usd: number | null;
  /** Request-count cap (e.g. Gemini's 1,000/day free tier), or null. */
  pool_requests: number | null;
  pool_period: "day" | "month" | null;
  /** Pool exhaustion STOPS requests — no automatic fall-through. */
  no_spillover: boolean;
  note: string;
}

export interface BillingRoute {
  agent: string;
  task_type: TaskType;
  plan: string;
  buckets: RouteBucket[];
  active: RouteBucket | null;
  charges: BucketCharges | null;
  marginal_cost_zero: boolean;
  capped: boolean;
}

export interface AgentRouteOverview {
  agent: string;
  plan: string;
  /** Plan tiers this agent's provider offers ([] = no plan knob). */
  plans: string[];
  buckets: RouteBucket[];
  routes: Record<TaskType, BillingRoute>;
}

export interface BillingRouteConfig {
  agents: Record<string, AgentRouteOverview>;
  task_types: TaskType[];
  charges: BucketCharges[];
  /** When the provider billing snapshot was last verified (staleness note). */
  as_of: string;
}

export const getBillingRouteConfig = () =>
  api<BillingRouteConfig>("/config/billing-route");

/** Set an agent's plan tier, or `null` to revert to the provider default. */
export const setBillingPlan = (agent: string, plan: string | null) =>
  api<BillingRouteConfig>("/config/billing-route", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agent, plan }),
  });

export const PLAN_LABEL: Record<string, string> = {
  default: "Default",
  pro: "Pro",
  max5x: "Max 5x",
  max20x: "Max 20x",
  pro_plus: "Pro+",
  business: "Business",
  enterprise: "Enterprise",
  ultra: "Ultra",
};

export const TASK_TYPE_LABEL: Record<TaskType, string> = {
  interactive: "Interactive — you, in the terminal/editor",
  programmatic: "Programmatic — headless: scripts, SDK, CI",
};

export const CHARGES_LABEL: Record<BucketCharges, string> = {
  included: "$0 marginal",
  api_rate: "API rate",
  electricity: "power estimate",
};

export const MODE_LABEL: Record<BillingMode, string> = {
  subscription: "Subscription (flat fee)",
  api: "API (pay-per-token)",
  local: "Local (self-hosted)",
  unknown: "Not set",
};

/**
 * Derive the dashboard's cost-tile framing from the mix of agent modes.
 * The dollar number is always the API-list-price equivalent; only the words
 * change so it's never wrong for a given user's situation.
 */
export function costFraming(
  agents: Record<string, AgentBilling> | undefined,
): { hint: string; callout: string } {
  const modes = new Set(Object.values(agents ?? {}).map((a) => a.mode));
  const hasSub = modes.has("subscription") || modes.has("unknown");
  const hasApi = modes.has("api");
  const hasLocal = modes.has("local");

  // Pure pay-per-token: the figure approximates a real bill.
  if (hasApi && !hasSub && !hasLocal) {
    return {
      hint: "Estimated API spend at list prices.",
      callout:
        "You're on pay-per-token (API) plans, so this approximates your actual bill — though it's still an estimate: tiers, batch/cache discounts and overage rates can shift the real figure.",
    };
  }

  // Pure subscription: the figure is an equivalent, not a bill.
  if (hasSub && !hasApi && !hasLocal) {
    return {
      hint: "At API list prices — for comparing sessions, not an invoice.",
      callout:
        "On a subscription plan? The API equiv. figure above re-prices your usage at API list rates so you can compare sessions — it is not a bill. Claude Pro/Max, Copilot and other flat-fee plans charge a fixed monthly price, so your actual spend is much lower.",
    };
  }

  // Mixed (and/or local): be explicit that meaning varies per agent.
  return {
    hint: "API list-price equivalent — meaning varies by plan.",
    callout:
      "You run a mix of plans. For pay-per-token (API) agents this figure approximates your bill; for flat-rate subscriptions (Claude Pro/Max, Copilot) it's only an API-list-price equivalent and your real spend is lower" +
      (hasLocal ? "; local models are estimated by electricity instead" : "") +
      ". Set each agent's plan in Settings → Billing & cost.",
  };
}
