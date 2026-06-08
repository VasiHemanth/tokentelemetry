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
