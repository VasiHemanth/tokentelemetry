"use client";

import { api } from "./api";

// ---- Backend API contract types (see backend on :8010) ----

export interface SummarizerBackend {
  name: string;
  display_name: string;
}

/**
 * Tuning for the openai_compat backend — POSTed to any server speaking the
 * OpenAI /v1/chat/completions API. Mirrors the backend default_config().
 */
export interface OpenAICompatConfig {
  endpoint: string;
  /** Optional bearer token; most local servers ignore it. */
  api_key: string;
  max_tokens: number;
  temperature: number;
  top_p: number;
  top_k: number;
  min_p: number;
  presence_penalty: number;
  repetition_penalty: number;
  enable_thinking: boolean;
}

export const DEFAULT_OPENAI_COMPAT: OpenAICompatConfig = {
  endpoint: "http://localhost:8080/v1",
  api_key: "",
  max_tokens: 512,
  temperature: 0.7,
  top_p: 0.95,
  top_k: 20,
  min_p: 0.0,
  presence_penalty: 1.5,
  repetition_penalty: 1.0,
  enable_thinking: false,
};

export interface SummarizerConfig {
  enabled: boolean;
  backend: string | null;
  model: string | null;
  /** Present only when the openai_compat backend has been configured. */
  openai_compat?: OpenAICompatConfig;
}

export interface SummaryBrief {
  intent: string;
  final_text: string;
  user_turns: number;
  tools: Record<string, number>;
  files: string[];
  commands: string[];
  errors: string[];
  tokens: { input: number; output: number; total: number };
  cost: number;
  model: string | null;
  agent: string;
  project: string;
}

export interface SummaryNarrative {
  intent_outcome?: string;
  actions?: string[];
  efficiency?: string;
  notable?: string[];
}

export interface Summary {
  session_id: string;
  agent: string;
  content_hash: string;
  backend: string;
  model: string | null;
  brief: SummaryBrief;
  narrative: SummaryNarrative | null;
  summary_cost: number;
  generated_at: string;
  stale: boolean;
}

export interface SummaryErrorInfo {
  category: "auth" | "quota" | "too_large" | "model" | "timeout" | "network" | "no_output" | "unknown";
  title: string;
  message: string;
  hint: string | null;
  raw: string;
}

export interface RecentTally {
  requested: number;
  summarized: number;
  skipped: number;
  failed: number;
}

// ---- API helpers (all go through api<T>/API_BASE, never hardcoded URLs) ----

export const getSummarizerConfig = () => api<SummarizerConfig>("/config/summarizer");

export const getAvailableBackends = () =>
  api<{ backends: SummarizerBackend[] }>("/summarizer/available").then((r) => r.backends);

export interface OllamaModel {
  name: string;
  size: string;
  modified: string;
}
export const listOllamaModels = () =>
  api<{ models: OllamaModel[] }>("/summarizer/ollama/models").then((r) => r.models);

export interface CodexModel {
  name: string;
  label: string;
  hint: string;
}
export const listCodexModels = () =>
  api<{ models: CodexModel[] }>("/summarizer/codex/models").then((r) => r.models);

export const putSummarizerConfig = (cfg: SummarizerConfig) =>
  api<SummarizerConfig>("/config/summarizer", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cfg),
  });

export interface OpenAICompatTestResult {
  ok: boolean;
  sample?: string;
  endpoint?: string;
  error?: string;
  error_info?: SummaryErrorInfo | null;
}

/** Ping the configured OpenAI-compatible endpoint to confirm it's reachable. */
export const testOpenAICompat = (model: string | null, openai_compat: OpenAICompatConfig) =>
  api<OpenAICompatTestResult>("/summarizer/openai-compat/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model, openai_compat }),
  });

export const getCachedSummary = (sessionId: string) =>
  api<{ summary: Summary | null }>(`/sessions/${sessionId}/summary`).then((r) => r.summary);

export const generateSummary = (sessionId: string, agent: string, force = false) =>
  api<{ summary: Summary; error: string | null; error_info?: SummaryErrorInfo | null }>(
    `/sessions/${sessionId}/summary?agent=${encodeURIComponent(agent)}&force=${force}`,
    { method: "POST" },
  );

export const summarizeRecent = (limit: number) =>
  api<RecentTally>(`/summaries/recent?limit=${limit}`, { method: "POST" });

/**
 * Config is "unset" (never configured by the user) when AI summaries are off
 * AND no backend has been chosen — that's the signal to show first-run onboarding.
 */
export const isConfigUnset = (cfg: SummarizerConfig) => !cfg.enabled && cfg.backend == null;

export const ONBOARDING_FLAG = "tt-summarizer-onboarded";
