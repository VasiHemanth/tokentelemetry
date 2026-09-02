// Runtime ids the backend records on a session when it ran on a local engine.
const LOCAL_PROVIDERS = new Set([
  "ollama", "lmstudio", "lm-studio", "llama.cpp", "llamacpp", "llama-cpp",
  "vllm", "localai", "local-ai", "jan", "gpt4all", "koboldcpp", "local",
]);

export function isLocalModel(modelName: string): boolean {
  const lower = modelName.toLowerCase();
  return (
    lower.includes("llama") ||
    lower.includes("mistral") ||
    lower.includes("qwen") ||
    lower.includes("phi") ||
    lower.includes("gemma") ||
    lower.includes("mixtral") ||
    lower.includes("nemotron") ||
    lower.includes("deepseek-coder") ||
    lower.includes("starcoder") ||
    lower.includes("local") ||
    lower.includes("mlx") ||
    lower.includes("gguf") ||
    lower.includes("ollama")
  );
}

/**
 * Prefer the backend's authoritative `provider` / `billing_mode` / `local` blob;
 * fall back to the model-name heuristic only when those are absent.
 */
export function isLocalSession(
  model: string | undefined,
  provider: string | undefined,
  billingMode?: string | undefined,
  localBlob?: { is_local?: boolean } | null,
): boolean {
  if (localBlob?.is_local) return true;
  if (billingMode === "local") return true;
  if (provider && LOCAL_PROVIDERS.has(provider.toLowerCase())) return true;
  return isLocalModel(model || "");
}

/** @deprecated Prefer backend energy_wh; kept for offline display only. */
export function estimateEnergyWh(outputTokens: number, loadWatts = 80, tokPerSec = 30): number {
  if (outputTokens <= 0 || loadWatts <= 0 || tokPerSec <= 0) return 0;
  return (outputTokens / tokPerSec) * loadWatts / 3600;
}

export interface LocalSessionMetrics {
  is_local: boolean;
  tok_per_sec: number;
  tok_per_sec_source: "measured" | "estimated" | string;
  gen_seconds: number;
  energy_wh: number;
  co2_g: number;
  electricity_cost: number;
  cloud_equiv_cost: number;
  savings_usd: number;
  wh_per_1m_output: number | null;
  cost_per_1m_output: number | null;
  load_watts: number;
  reference_cloud_model: string;
}

export function formatEnergy(wh: number | undefined | null): string {
  if (wh == null || Number.isNaN(wh)) return "—";
  if (wh >= 1000) return `${(wh / 1000).toFixed(2)} kWh`;
  if (wh >= 1) return `${wh.toFixed(2)} Wh`;
  return `${wh.toFixed(3)} Wh`;
}

export function formatCo2(g: number | undefined | null): string {
  if (g == null || Number.isNaN(g)) return "—";
  if (g >= 1000) return `${(g / 1000).toFixed(2)} kg`;
  return `${g.toFixed(2)} g`;
}

export function formatTokPerSec(tps: number | undefined | null, source?: string): string {
  if (tps == null || Number.isNaN(tps) || tps <= 0) return "—";
  const base = tps >= 100 ? tps.toFixed(0) : tps.toFixed(1);
  return source === "estimated" ? `~${base} t/s` : `${base} t/s`;
}

export function formatWhPer1M(v: number | undefined | null): string {
  if (v == null || Number.isNaN(v)) return "—";
  if (v >= 1000) return `${(v / 1000).toFixed(1)}k Wh`;
  return `${v.toFixed(1)} Wh`;
}
