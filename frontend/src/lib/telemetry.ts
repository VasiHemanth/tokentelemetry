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

/** Exactly-what-we-send transparency payload (`GET /config/telemetry/preview`). */
export interface TelemetryPreview extends TelemetryState {
  session_id: string;
  never_collected: string[];
  events: string[];
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

/** Hermes sub-pages that get their own route enum. Anything under /hermes that
 *  is not listed here reports as plain "hermes" rather than inventing a value
 *  the backend would collapse to "other" — an unknown sub-page is still a
 *  Hermes visit, and losing it entirely would understate the section. Keep in
 *  sync with the `route` enum in backend/telemetry.py. */
const HERMES_SUBROUTES = [
  "skills", "tools", "profiles", "soul",
  "memory", "gateway", "kanban", "schedules",
] as const;

function hermesRoute(p: string): string {
  const rest = p.slice("/hermes".length).replace(/^\/+/, "");
  if (!rest) return "hermes";
  const head = rest.split("/")[0];
  return (HERMES_SUBROUTES as readonly string[]).includes(head)
    ? `hermes-${head}`
    : "hermes";
}

/** Map a Next.js pathname to one of the backend's allowlisted route enums. */
export function routeOf(pathname: string): string {
  const p = pathname.replace(/\/+$/, "") || "/";
  if (p === "/") return "dashboard";
  if (p.startsWith("/analytics")) return "analytics";
  if (p.startsWith("/local-models")) return "local-models";
  if (p.startsWith("/sessions")) return "traces";
  if (p.startsWith("/projects")) return p === "/projects" ? "projects" : "project-detail";
  if (p.startsWith("/hermes")) return hermesRoute(p);
  if (p.startsWith("/settings")) return "settings";
  return "other";
}
