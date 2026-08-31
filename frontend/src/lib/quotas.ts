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
