/**
 * TokenTelemetry telemetry sink — Cloudflare Worker → Workers Analytics Engine.
 *
 * Why a Worker (still): the app is open-source and runs from source on each
 * user's machine, so any API token shipped in it is extractable. Analytics
 * Engine is written via a Worker *binding* (env.TELEMETRY) that is bound to the
 * Cloudflare account at deploy time — there is NO key in the request path and
 * NO credential in the downloadable app. The app ships only this Worker's public
 * URL — there is no analytics key to hold or rotate anywhere.
 *
 * Privacy: we never read or store the client IP. We DO record the 2-letter
 * country from Cloudflare's edge (request.cf.country) — coarse geo, not an
 * address — so the dashboard has a country breakdown without touching PII.
 *
 * Deploy: see proxy/README.md.
 *   1. wrangler.jsonc already binds the dataset (binding "TELEMETRY",
 *      dataset "tt_telemetry"). No secret to set.
 *   2. wrangler deploy
 *   3. Query via the SQL API / Grafana (Analytics Engine has no built-in UI).
 *
 * Analytics Engine data-point schema — POSITIONAL, so remember these columns
 * when you write SQL (blob1..blobN, double1..doubleN, index1, plus the
 * automatic `timestamp` and `_sample_interval`):
 *
 *   index1  = eventName              (sampling/grouping key, <=96 bytes)
 *   blob1   = eventName
 *   blob2   = sessionId              (random per launch, not linkable)
 *   blob3   = osName                 (Darwin / Linux / Windows)
 *   blob4   = osVersion
 *   blob5   = deviceModel            (CPU arch: arm64 / x86_64)
 *   blob6   = appVersion             (git short sha)
 *   blob7   = route                  (page.viewed)
 *   blob8   = feature name           (feature.used)
 *   blob9   = dimension              (analytics.filtered)
 *   blob10  = summary backend        (trace.summarized "backend")
 *   blob11  = outcome                (trace.summarized "outcome")
 *   blob12  = retention tier         (retention.opted_in)
 *   blob13  = agents                 (csv of detected agents, context)
 *   blob14  = summarizer_backend     (context)
 *   blob15  = country                (CF edge 2-letter, no IP stored)
 *   blob16  = sdkVersion
 *   blob17  = agent                 (agent.model_used)
 *   blob18  = model family          (agent.model_used "family")
 *   double1 = agent_count
 *   double2 = isDebug                (0/1)
 */

const MAX_BODY = 8 * 1024; // events are tiny; reject anything bigger as abuse.

// The only event names we accept. Anything else is dropped here, so a stranger
// POSTing junk to the public URL can't pollute the dataset. Keep in sync with
// backend/telemetry.py::_EVENT_PROPS. NOTE: the "other" bucket is deliberately
// NOT accepted here — the backend only ever emits the known names above, so an
// inbound "other" can only be forged junk. (Audit AUDIT-grok.md, Med finding.)
const ALLOWED_EVENTS = new Set([
  "app.launched", "page.viewed", "trace.summarized",
  "analytics.filtered", "feature.used", "retention.opted_in",
  "agent.model_used",
]);

// Cheap, stateless validation. This is NOT anti-spoof (an open-source client
// can't hold a secret) — it just keeps obvious junk out of the dataset.
// Volumetric floods are handled by Cloudflare's automatic DDoS protection; add a
// Rate Limiting rule on this route to cap per-IP request rate (see README).
function parseValid(body) {
  if (!body || body.length > MAX_BODY) return null;
  let e;
  try { e = JSON.parse(body); } catch { return null; }
  if (!e || typeof e !== "object") return null;
  if (!ALLOWED_EVENTS.has(e.eventName)) return null;
  if (typeof e.sessionId !== "string" || e.sessionId.length > 64) return null;
  return e;
}

// Coerce any value to a short, safe blob string. The backend already sanitizes,
// but the sink is defensive: never let an unexpected/huge value through.
function blob(v, max = 64) {
  if (v === undefined || v === null) return "";
  const s = String(v);
  return s.length > max ? s.slice(0, max) : s;
}

function num(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

export default {
  async fetch(request, env) {
    // Health check / accidental GET.
    if (request.method !== "POST") {
      return new Response("tokentelemetry telemetry sink (analytics engine)", { status: 200 });
    }
    // Misconfiguration: binding missing. 500 so a deploy mistake is visible in
    // logs, but the app swallows it (fire-and-forget) so users never notice.
    if (!env.TELEMETRY) return new Response("sink not configured", { status: 500 });

    // Only accept JSON; reject other content types outright.
    const ctype = request.headers.get("content-type") || "";
    if (!ctype.includes("application/json")) return new Response(null, { status: 415 });

    const body = await request.text();
    const e = parseValid(body);
    // Drop invalid/junk events silently (204) — give a spoofer no signal to
    // probe against, and never write unrecognised payloads to the dataset.
    if (!e) return new Response(null, { status: 204 });

    const s = (e.systemProps && typeof e.systemProps === "object") ? e.systemProps : {};
    const p = (e.props && typeof e.props === "object") ? e.props : {};
    const country = (request.cf && request.cf.country) || "";

    // Write to Analytics Engine. writeDataPoint buffers at the platform and does
    // not block; wrap defensively so a runtime hiccup can never surface to the
    // caller. Whatever happens below, the app gets a clean 204.
    try {
      env.TELEMETRY.writeDataPoint({
        indexes: [blob(e.eventName, 96)],
        blobs: [
          blob(e.eventName),          // blob1
          blob(e.sessionId),          // blob2
          blob(s.osName),             // blob3
          blob(s.osVersion),          // blob4
          blob(s.deviceModel),        // blob5
          blob(s.appVersion),         // blob6
          blob(p.route),              // blob7
          blob(p.name),               // blob8
          blob(p.dimension),          // blob9
          blob(p.backend),            // blob10
          blob(p.outcome),            // blob11
          blob(p.tier),               // blob12
          blob(p.agents, 120),        // blob13
          blob(p.summarizer_backend), // blob14
          blob(country, 8),           // blob15
          blob(s.sdkVersion),         // blob16
          blob(p.agent),              // blob17
          blob(p.family),             // blob18
        ],
        doubles: [
          num(p.agent_count),         // double1
          s.isDebug ? 1 : 0,          // double2
        ],
      });
    } catch (_) {
      // Best-effort: a sink failure must never make the caller wait or retry.
    }
    // Always 204 — the app fire-and-forgets and must not retry-storm.
    return new Response(null, { status: 204 });
  },
};
