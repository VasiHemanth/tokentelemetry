export function isLocalModel(modelName: string): boolean {
  const lower = modelName.toLowerCase();
  return (
    lower.includes("llama") ||
    lower.includes("mistral") ||
    lower.includes("qwen") ||
    lower.includes("phi") ||
    lower.includes("gemma") ||
    lower.includes("mixtral") ||
    lower.includes("deepseek-coder") ||
    lower.includes("starcoder") ||
    lower.includes("local") ||
    lower.includes("mlx") ||
    lower.includes("gguf") ||
    lower.includes("ollama")
  );
}

export function estimateEnergyWh(outputTokens: number): number {
  return outputTokens * 0.05; // 0.05 Wh per output token assumption
}
