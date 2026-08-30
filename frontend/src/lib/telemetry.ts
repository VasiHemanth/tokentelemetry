"use client";

import { api, apiFetch } from "./api";

/** State of the telemetry preference (`GET/POST /config/telemetry`). Mirrors the
 *  update-check shape: `enabled` is the saved preference, `env_forced_off` is set
 *  by DO_NOT_TRACK / TT_NO_TELEMETRY (toggle read-only), `effective` is what
 *  actually happens (env + CI win). */
export interface TelemetryState {
  enabled: boolean;
  env_forced_off: boolean;
  is_ci: boolean;
  effective: boolean;
  notice_ack: boolean;
}

/** One prop an event may carry. `values` is the closed set it is validated
 *  against, or null when the prop is free-form (safe-scalar filter only). */
export interface TelemetryProp {
  name: string;
  values: string[] | null;
}

/** One event and every prop it can carry. Derived server-side from the
 *  allowlists, so this list can never drift from what is actually sent. */
export interface TelemetryEventSpec {
  event: string;
  props: TelemetryProp[];
}

/** A context/system prop attached to every event, with this machine's real
 *  current value — so the panel shows what would be sent, not a description. */
export interface TelemetryAlwaysSent {
  name: string;
  scope: "context" | "system";
  value: string | number | boolean;
  note: string;
}

/** Exactly-what-we-send transparency payload (`GET /config/telemetry/preview`). */
export interface TelemetryPreview extends TelemetryState {
  session_id: string;
  never_collected: string[];
  events: string[];
  event_catalog: TelemetryEventSpec[];
  always_sent: TelemetryAlwaysSent[];
  sample: unknown[];
  recent_sent: unknown[];
}

export const getTelemetry = () => api<TelemetryState>("/config/telemetry");

export const setTelemetry = (enabled: boolean) =>
  api<TelemetryState>("/config/telemetry", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });

export const getTelemetryPreview = () =>
  api<TelemetryPreview>("/config/telemetry/preview");

/** Persist server-side that the first-run notice has been acknowledged.
 *  After this, `GET /config/telemetry` returns `notice_ack: true` so the
 *  banner never reappears even after clearing browser storage. */
export async function ackTelemetryNotice(): Promise<void> {
  await api<{ notice_ack: boolean }>("/config/telemetry/ack", {
    method: "POST",
  });
}

/** Client-origin events the backend bridge accepts. */
export type ClientEvent = "page.viewed" | "analytics.filtered" | "feature.used";

/**
 * Fire-and-forget event. The backend re-sanitizes everything (allowlist + enum),
 * so this can never leak content even if called carelessly — but keep props to
 * the documented enum values anyway. Never throws, never blocks the UI.
 */
export function trackEvent(event: ClientEvent, props?: Record<string, string>): void {
  try {
    apiFetch("/telemetry/event", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event, props }),
    }).catch(() => {});
  } catch {
    /* never surface telemetry failures */
  }
}

/** Map a Next.js pathname to one of the backend's allowlisted route enums. */
export function routeOf(pathname: string): string {
  const p = pathname.replace(/\/+$/, "") || "/";
  if (p === "/") return "dashboard";
  if (p.startsWith("/analytics")) return "analytics";
  if (p.startsWith("/local-models")) return "local-models";
  if (p.startsWith("/sessions")) return "traces";
  if (p.startsWith("/projects")) return p === "/projects" ? "projects" : "project-detail";
  if (p.startsWith("/agents/")) return "agent-panel";
  if (p.startsWith("/hermes")) return "hermes";
  if (p.startsWith("/settings")) return "settings";
  return "other";
}

/** The harness key from an `/agents/<key>` path, else undefined.
 *
 *  Paired with `routeOf`, this is what makes "is anyone actually opening the
 *  Qoder panel?" answerable. The backend re-validates the key against its own
 *  closed agent list, so an unrecognised one is reported as "other" rather than
 *  riding through. */
export function agentOf(pathname: string): string | undefined {
  const m = pathname.replace(/\/+$/, "").match(/^\/agents\/([A-Za-z0-9_-]+)/);
  return m ? m[1].toLowerCase() : undefined;
}
