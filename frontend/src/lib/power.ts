"use client";

import { api } from "./api";

export interface PowerConfig {
  loadWatts: number;
  costPerKwh: number;
  gridCarbonIntensity: number;
  subscriptionEndpoints: string[];
  localEndpoints: string[];
  /** Cloud model id used for local-vs-API savings (backend default: claude-sonnet-4-6). */
  referenceCloudModel?: string;
  /** True once the user has saved a power.json (else values are shipped defaults). */
  configured: boolean;
  /** Chip-aware default wattage for this machine, the baseline loadWatts falls back to. */
  deviceDefault?: {
    watts: number;
    source: string;
    detail?: string;
    /** True only when the hardware was auto-detected (e.g. Apple Silicon); false = generic fallback. */
    detected?: boolean;
  };
}

export interface LocalRuntimeModel {
  name?: string;
  size?: number;
  parameter_size?: string;
  quantization_level?: string;
  family?: string;
  modified_at?: string;
  size_vram?: number;
  details?: Record<string, unknown>;
  expires_at?: string;
}

export interface LocalRuntime {
  ollama: {
    ollama: "online" | "offline" | string;
    base_url?: string | null;
    models: LocalRuntimeModel[];
    running: LocalRuntimeModel[];
    error?: string | null;
  };
  gpu: {
    available: boolean;
    gpus: {
      index: number;
      name: string;
      memory_used_mb?: number | null;
      memory_total_mb?: number | null;
      utilization_pct?: number | null;
      power_w?: number | null;
    }[];
    reason?: string | null;
  };
  hf_usage?: string | null;
  platform?: string;
}

export interface PowerEstimate {
  watts: number;
  source: string;
  confidence: string;
  /** Human label for what the estimate is based on, e.g. "Apple M5 (10-core GPU)". */
  detail?: string;
}

export interface PowerMeter {
  capability: {
    available: boolean;
    method: string | null;
    system: string;
    reason: string;
    /** Chip-aware fallback default when no real measurement is possible. */
    estimated?: PowerEstimate;
  };
  /** Live real reading, or null when no root-free source is available. */
  reading: { watts: number; source: string; confidence: string } | null;
}

export interface CalibrateResult {
  /** Measured watts, or null when no real source was available (config unchanged). */
  measured: number | null;
  /** Chip-aware estimated watts when measurement wasn't possible, else null. */
  estimated?: number | null;
  source?: string | null;
  /** What the estimate is based on, e.g. "Apple M5 (10-core GPU)". */
  detail?: string | null;
  samples?: number;
  reason?: string;
  config?: PowerConfig;
}

export const getPowerConfig = () => api<PowerConfig>("/config/power");

export const putPowerConfig = (patch: Partial<PowerConfig>) =>
  api<PowerConfig>("/config/power", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });

export const getPowerMeter = () => api<PowerMeter>("/config/power/meter");

export const calibratePower = () =>
  api<CalibrateResult>("/config/power/calibrate", { method: "POST" });

export const getLocalRuntime = () => api<LocalRuntime>("/local-runtime");
