// Runtime ids the backend records on a session when it ran on a local engine.
const LOCAL_PROVIDERS = new Set([
  "ollama", "lmstudio", "lm-studio", "llama.cpp", "llamacpp", "vllm",
  "localai", "local-ai", "jan", "gpt4all", "koboldcpp", "local",
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
 * Prefer the backend's authoritative `provider` signal (set when a session ran on
 * a local engine); fall back to the model-name heuristic when it's absent.
 */
export function isLocalSession(model: string | undefined, provider: string | undefined): boolean {
  if (provider && LOCAL_PROVIDERS.has(provider.toLowerCase())) return true;
  return isLocalModel(model || "");
}

export function estimateEnergyWh(outputTokens: number): number {
  return outputTokens * 0.05; // 0.05 Wh per output token assumption
}
