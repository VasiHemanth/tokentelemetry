export type QuotaResource = {
  kind: "consumption" | "balance" | "spend" | "usage" | string;
  unit: "percent" | "credits" | "resets" | "usd" | "count" | string;
  used?: number;
  available?: number;
  limit?: number;
  remaining?: number;
  utilization?: number;
  resetsAt?: string;
  windowSeconds?: number;
  expiresAt?: string[];
  estimated?: boolean;
};

export type QuotaSnapshot = {
  displayName: string;
  plan?: string | null;
  fetchedAt: string;
  expiresAt: string;
  stale: boolean;
  resources: Record<string, QuotaResource>;
};

export type QuotaResponse = {
  schema: "tokentelemetry.quotas.v1";
  generatedAt: string;
  providers: Record<string, QuotaSnapshot>;
  errors: { providerId: string; message: string }[];
  capabilities: Record<string, QuotaCapability>;
};

export type QuotaCapabilityState =
  | "available"
  | "notSignedIn"
  | "sessionExpired"
  | "notEntitled"
  | "refreshFailed"
  | "notSupported";

export type QuotaCapability = {
  displayName: string;
  state: QuotaCapabilityState | string;
  detail?: string;
};

const RESOURCE_NAMES: Record<string, string> = {
  session: "Session",
  weekly: "Weekly",
  monthly: "Monthly",
  sonnetWeekly: "Sonnet weekly",
  spark: "Spark",
  sparkWeekly: "Spark weekly",
  credits: "Credits",
  extraUsage: "Extra usage",
  rateLimitResets: "Rate-limit resets",
  chat: "Chat",
  completions: "Completions",
  cursorModels: "Cursor models",
  otherModels: "Other models",
  onDemand: "On-demand",
};

export function quotaResourceLabel(key: string): string {
  return RESOURCE_NAMES[key] ?? key.replace(/([a-z])([A-Z])/g, "$1 $2");
}

export function quotaAmount(value: number, unit: string): string {
  if (unit === "usd") return `$${value.toFixed(value < 10 ? 2 : 0)}`;
  if (unit === "percent") return `${Math.round(value)}%`;
  return `${Number.isInteger(value) ? value : value.toFixed(1)} ${unit}`;
}

/** Colour marks shared by every quota surface. */
export const QUOTA_WARN_AT = 75;
export const QUOTA_CRITICAL_AT = 90;

export function quotaColor(pct: number): string {
  if (pct >= QUOTA_CRITICAL_AT) return "var(--tt-danger-fg)";
  if (pct >= QUOTA_WARN_AT) return "var(--tt-warn-fg)";
  return "var(--tt-brand)";
}

export type QuotaWindow = {
  providerId: string;
  displayName: string;
  resourceKey: string;
  label: string;
  pct: number;
};

/** Percentage consumed, or null when the provider gave no ceiling to fill. */
export function quotaPercent(resource: QuotaResource): number | null {
  if (resource.used == null || resource.limit == null || resource.limit <= 0) return null;
  return Math.min(100, Math.max(0, (resource.used / resource.limit) * 100));
}

/** The most-consumed window for one provider — what its tile should show. */
export function worstWindowFor(
  providerId: string,
  snapshot: QuotaSnapshot | undefined,
): QuotaWindow | undefined {
  if (!snapshot) return undefined;
  let worst: QuotaWindow | undefined;
  for (const [resourceKey, resource] of Object.entries(snapshot.resources)) {
    const pct = quotaPercent(resource);
    if (pct == null) continue;
    if (!worst || pct > worst.pct) {
      worst = {
        providerId,
        displayName: snapshot.displayName,
        resourceKey,
        label: quotaResourceLabel(resourceKey),
        pct,
      };
    }
  }
  return worst;
}

/**
 * The single window closest to its limit across every signed-in provider.
 *
 * This is what the sidebar reports, so "am I about to be cut off?" is answerable
 * without opening anything: the nearest ceiling anywhere is the one that matters.
 */
export function worstWindow(data: QuotaResponse | undefined): QuotaWindow | undefined {
  if (!data) return undefined;
  let worst: QuotaWindow | undefined;
  for (const [providerId, snapshot] of Object.entries(data.providers)) {
    const candidate = worstWindowFor(providerId, snapshot);
    if (candidate && (!worst || candidate.pct > worst.pct)) worst = candidate;
  }
  return worst;
}
