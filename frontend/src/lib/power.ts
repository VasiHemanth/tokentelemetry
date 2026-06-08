"use client";

import { api } from "./api";

export interface PowerConfig {
  loadWatts: number;
  costPerKwh: number;
  subscriptionEndpoints: string[];
  localEndpoints: string[];
  /** True once the user has saved a power.json (else values are shipped defaults). */
  configured: boolean;
}

export interface PowerMeter {
  capability: {
    available: boolean;
    method: string | null;
    system: string;
    reason: string;
  };
  /** Live real reading, or null when no root-free source is available. */
  reading: { watts: number; source: string; confidence: string } | null;
}

export interface CalibrateResult {
  /** Measured watts, or null when no real source was available (config unchanged). */
  measured: number | null;
  source?: string;
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
