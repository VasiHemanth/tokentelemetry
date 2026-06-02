/**
 * Resolve where a session-detail "Back" button should navigate.
 * Prefers an explicit `from` origin (the route the session was opened from),
 * falling back to a sensible per-agent landing page. Only internal absolute
 * paths are honored (must start with a single "/") to avoid open-redirect via
 * a crafted ?from= value; protocol-relative ("//evil.com") and external URLs
 * are rejected in favor of the fallback.
 */
export function resolveSessionBackTarget(from: string | null | undefined, agent: string | null | undefined): string {
  if (typeof from === "string" && from.startsWith("/") && !from.startsWith("//")) {
    return from;
  }
  return agent === "hermes" ? "/hermes" : "/";
}
