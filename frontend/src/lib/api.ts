"use client";

import { useEffect, useState } from "react";

// Resolve the backend base URL. An explicit NEXT_PUBLIC_API_BASE wins (pin a
// fixed host if you want one). Otherwise derive it from the address the
// dashboard was actually loaded on (window.location) plus the API port — so a
// single build works on localhost, a LAN IP, or a tailnet host without rebaking
// the URL. Falls back to loopback during SSR, where window is unavailable.
export const API_BASE = (() => {
  const explicit = process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "");
  if (explicit) return explicit;
  const port = process.env.NEXT_PUBLIC_API_PORT || "8000";
  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:${port}`;
  }
  return `http://127.0.0.1:${port}`;
})();

// --- Remote-access token --------------------------------------------------
// When the dashboard is opened from another device, the backend requires an
// access token (see bin/cli.js / backend RemoteAuthMiddleware). We hold it in
// localStorage keyed by hostname — a laptop may talk to several boxes, each
// with its own token, and "localhost" never needs one. The token is NEVER
// baked into the build; the user pastes it (printed once on the server) into
// the TokenGate prompt. Loopback requests are exempt server-side, so local use
// never sees any of this.

function tokenKey(): string {
  const host = typeof window !== "undefined" ? window.location.hostname : "localhost";
  return `tt-token-${host}`;
}

export function getToken(): string {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(tokenKey()) || "";
  } catch {
    return "";
  }
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  try {
    const t = token.trim();
    if (t) window.localStorage.setItem(tokenKey(), t);
    else window.localStorage.removeItem(tokenKey());
  } catch {
    /* storage unavailable (private mode / disabled) — non-fatal */
  }
}

// Bootstrap: if the dashboard was opened with a `?token=` in the URL (e.g. from
// a scanned QR / "connect a device" link), persist it for this host. Runs at
// module load — before any component fetch — so the first request already
// carries the token. The URL itself is cleaned up separately, post-hydration,
// by stripBootstrapTokenFromUrl() (Next's router re-applies the query if we
// strip it this early). Browser-only; no-op during SSR.
function consumeBootstrapToken(): void {
  if (typeof window === "undefined") return;
  try {
    const t = new URLSearchParams(window.location.search).get("token");
    if (t) setToken(t);
  } catch {
    /* malformed URL / storage unavailable — non-fatal */
  }
}
consumeBootstrapToken();

/** Remove a consumed `?token=` from the address bar so it doesn't linger in
 *  history/bookmarks/screenshots. Must run AFTER hydration (see TokenGate) —
 *  a module-load replaceState gets overwritten when Next syncs the URL. */
export function stripBootstrapTokenFromUrl(): void {
  if (typeof window === "undefined") return;
  try {
    const url = new URL(window.location.href);
    if (!url.searchParams.has("token")) return;
    url.searchParams.delete("token");
    window.history.replaceState(null, "", url.pathname + url.search + url.hash);
  } catch {
    /* non-fatal */
  }
}

/** Raised when the backend rejects a request for lack of a valid token. The
 *  TokenGate listens for the `tt-auth-required` window event this also emits. */
export class AuthRequiredError extends Error {
  constructor(path: string) {
    super(`Authentication required for ${path}`);
    this.name = "AuthRequiredError";
  }
}

function signalAuthRequired(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("tt-auth-required"));
  }
}

/** Build a URL for a browser-native resource load (artifact <img>/<a>/<video>),
 *  carrying the token as a query param since those requests can't set headers. */
export function artifactUrl(path: string): string {
  const base = `${API_BASE}${path}`;
  const token = getToken();
  if (!token) return base;
  const sep = base.includes("?") ? "&" : "?";
  return `${base}${sep}token=${encodeURIComponent(token)}`;
}

/** Like fetch(API_BASE + path) but attaches the access token and turns a 401
 *  into the auth-required signal. Returns the raw Response so callers that read
 *  .json()/.text() themselves keep working; it throws AuthRequiredError on 401
 *  so existing .catch handlers stop the chain. */
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  const token = getToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (res.status === 401) {
    signalAuthRequired();
    throw new AuthRequiredError(path);
  }
  return res;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await apiFetch(path, init);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${path}`);
  return res.json() as Promise<T>;
}

/** Remote-access connection info for the "Connect a device" panel. The backend
 *  serves this loopback-only, so on a remote device the request 403s and the
 *  panel simply renders nothing. */
export interface RemoteAccess {
  enabled: boolean;
  url?: string;
  token?: string;
}

export function getRemoteAccess(): Promise<RemoteAccess> {
  return api<RemoteAccess>("/remote-access");
}

export interface ResourceState<T> {
  data: T | undefined;
  loading: boolean;
  error: Error | undefined;
  refetch: () => void;
}

/**
 * Lightweight fetch hook. Polls every `pollMs` if provided.
 * Replaces the useEffect+fetch ceremony repeated on every page.
 */
export function useResource<T>(
  path: string | null,
  opts: { pollMs?: number; initial?: T } = {},
): ResourceState<T> {
  const [data, setData] = useState<T | undefined>(opts.initial);
  const [loading, setLoading] = useState<boolean>(path !== null);
  const [error, setError] = useState<Error | undefined>(undefined);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (path === null) return;
    let cancelled = false;
    const run = () => {
      api<T>(path)
        .then((d) => { if (!cancelled) { setData(d); setError(undefined); } })
        .catch((e) => { if (!cancelled) setError(e instanceof Error ? e : new Error(String(e))); })
        .finally(() => { if (!cancelled) setLoading(false); });
    };
    run();
    let id: ReturnType<typeof setInterval> | undefined;
    if (opts.pollMs) id = setInterval(run, opts.pollMs);
    return () => { cancelled = true; if (id) clearInterval(id); };
  }, [path, opts.pollMs, tick]);

  return { data, loading, error, refetch: () => setTick((t) => t + 1) };
}
