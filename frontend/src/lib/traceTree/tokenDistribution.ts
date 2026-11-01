import type { SpanTokens } from "./types";

const KEYS = ["input", "cacheRead", "cacheWrite", "output"] as const;

export function tokenDistribution(tokens: SpanTokens): { total: number; shares: SpanTokens } | null {
  if (KEYS.some(key => !Number.isFinite(tokens[key]) || tokens[key] < 0)) return null;
  const total = KEYS.reduce((sum, key) => sum + tokens[key], 0);
  if (!Number.isFinite(total)) return null;
  const shares = { input: 0, cacheRead: 0, cacheWrite: 0, output: 0 };
  if (total > 0) for (const key of KEYS) shares[key] = tokens[key] / total * 100;
  return { total, shares };
}

export function formatTokenShare(percent: number): string {
  if (percent === 0) return "0%";
  if (percent < 0.01) return "<0.01%";
  return `${percent.toLocaleString(undefined, { maximumFractionDigits: 2 })}%`;
}
