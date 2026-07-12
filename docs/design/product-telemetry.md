# Design: Privacy-respecting product telemetry

**Status:** BUILT & DEPLOYED · **Author:** analysis · **Date:** 2026-06-15
**Related:** [[local-first-no-user-network]] principle · website CRO analysis (`tokentelemetry-cro-analysis.md`) · `harness_config.py` preference pattern · update-check (the only prior outbound call)

---

## 1. The problem, stated honestly

We want to know **which features people actually use** — integrated trace summaries,
local-model filtering on Analytics, the Hermes surface, Projects/Plans, Artifacts,
etc. — so product effort goes where it matters instead of where we guess. Today we
have **zero signal**: the app is 100% local and emits nothing, so every roadmap call
is blind.

This collides head-on with the product's defining promise, repeated on the site and
in the privacy policy:

> "100% local and read-only … never sends your usage data anywhere … TokenTelemetry
> has no usage-telemetry endpoint."

**Any telemetry weakens that sentence.** The whole design is about how to learn what
we need while keeping that promise *substantially* intact and, above all, **honest**.
A vague claim of "anonymous" is not enough — the CRO data shows our best-converting,
most-skeptical audience is developers (GitHub 66.7%, Reddit 53.7%, Google 53.0%
engagement). That audience verifies claims and punishes betrayal.

### The cautionary tale we must not repeat
In **April 2026 the GitHub CLI switched on _opt-out_ (default-on) telemetry** and took
sustained public criticism (The Register, developer blogs, "DO_NOT_TRACK" threads).
For a tool literally named *TokenTelemetry* whose pitch is "nothing leaves your
machine," shipping default-on telemetry would be brand suicide. This is the single
most important constraint below.

---

## 2. Non-negotiable principles

These are derived from our brand, the local-first memory, and 2025–2026 CLI-telemetry
best practice (GitHub CLI backlash, Next.js anonymous telemetry, VS Code, the
`DO_NOT_TRACK` convention).

1. **On by default, but informed and one-click reversible (opt-out).** *(Decision
   2026-06-14 — overrides the earlier opt-in stance.)* Telemetry is enabled by
   default; a **loud first-run notice** tells the user it's on, exactly what it
   collects, and that it helps improve the product, with an obvious one-click "Turn
   off." This is only defensible because of principles 2–8 below — **and only if the
   brand/privacy copy is rewritten to match (see 1a).** Silent-on or buried-opt-out is
   not acceptable; the user must be *told*, not have to discover it.
   - **1a. The "we collect nothing" promise MUST be rewritten before release.** The
     site + privacy policy today say "never sends your usage data anywhere… no
     usage-telemetry endpoint." On-by-default makes that false. Releasing without
     fixing the copy is the actual failure mode (cf. the GitHub-CLI backlash: the
     objection was the *default*, not the disclosure). Non-negotiable.
   - **1b. Strictly anonymous, no personal data — this is what makes default-on
     lawful.** Under GDPR/ePrivacy, only genuinely non-personal anonymous analytics
     may run **without prior opt-in consent**. No stored IP, no stable identifier,
     content-free, allowlist-enforced (§3.3). The Cloudflare Analytics Engine
     architecture is built for exactly this: no key ships in the app, no cookies,
     no cross-session IDs. Add anything personal and default-on becomes a legal
     problem, not just a trust one.
2. **Inspectable.** The user can preview the *exact* payload any time ("Show me what
   you send") — on the first-run notice and in Settings. Anonymous only lands with
   developers if they can verify it in five seconds.
3. **Reversible instantly.** One toggle in Settings; opting out stops emission
   immediately and is honored on the very next event.
4. **No content, ever.** No prompts, code, file paths, project names, tokens, costs,
   model outputs, log text. Only *that a feature was used*, never *what it operated on*.
5. **No durable identity.** No account, no email, no stable hardware fingerprint. A
   random per-launch `session_id` only (see §6).
6. **Best-effort, never blocks.** Telemetry failures (offline, endpoint down) are
   swallowed silently and never slow or break the app. Mirror the update-check's
   fail-open posture.
7. **Honor the ecosystem kill-switches.** Respect `DO_NOT_TRACK=1` and a dedicated
   `TT_NO_TELEMETRY=1` env var (hard off, not user-overridable — for org/policy).
   CI / non-interactive launches never prompt and never emit.
8. **Document it precisely** in the privacy policy and README, including a sample
   payload. Update the "we collect nothing" copy to "we collect nothing unless you
   opt in, and here's exactly what."

> If we cannot hold all eight, we should ship **no telemetry** and use the
> voluntary-feedback fallback (local "Share my stats" panel) instead.

---

## 3. What to collect (event taxonomy)

Grounded in the real routes (`frontend/src/app/*`) and features. The model follows the
CLI best-practice shape: a small number of **event names** + a tiny **anonymous context**,
sent at most once per meaningful action.

### 3.1 Anonymous context (attached to every event)
| Field | Example | Why | Risk |
|---|---|---|---|
| `app_version` | `1.4.2` | Correlate usage with releases; spot stuck-on-old-version | none |
| `os` | `darwin` / `win32` / `linux` | Platform prioritization | none |
| `session_id` | random per app launch | Group events in one run, no cross-session linking | low |
| `agents_detected` | `["claude-code","codex"]` (names only, count) | **Highest-value signal**: which agents people actually run | low — names are public product list, not user data |
| `summarizer_backend` | `ollama` / `claude` / `none` | Local vs cloud summarizer mix → where to invest | low |
| `country` | `US` / `DE` (coarse, CF-edge-derived) | Regional usage breakdown | low — never IP; derived by CF edge, not stored |

### 3.2 Events (feature usage)
| Event | Fires when | Properties | Question it answers |
|---|---|---|---|
| `app.launched` | backend starts | — | DAU/retention, version spread |
| `page.viewed` | a route is opened | `route` (enum: dashboard, analytics, traces, projects, hermes, artifacts, local-models, settings…) | **Which surfaces matter.** Is anyone using Hermes? Artifacts? |
| `trace.summarized` | a trace summary is generated | `backend` (ollama/claude/…), `outcome` (ok/error-category) | Is the headline feature used? Which backend? Failure rate |
| `analytics.filtered` | a filter is applied on Analytics | `dimension` (agent/model/local-only/day), no values | **Is local-model filtering used?** (your explicit question) |
| `feature.used` | generic, for discrete features | `name` (plan-library, project-insights, delegation-view, power-cost, billing-mode, search…) | Long-tail feature adoption |
| `retention.opted_in` | user enables durable history | `tier` | Which power features convert |
| `agent.model_used` | once per launch, after the first full sessions scan | `agent` (enum: claude, codex, …), `family` (enum: claude-opus, gpt, gemini, …) | **Which model families each agent runs** (last 30 days) → seeds per-agent token-efficiency suggestions. Family is a hardcoded enum via `normalize_model_family()` — custom model ids collapse to `other`, never sent raw |

**Duration/outcome buckets, never raw values.** e.g. summary latency as
`fast/medium/slow`, not milliseconds tied to a specific trace.

### 3.3 Explicitly NEVER collected
Prompts · code · file/dir paths · project or repo names · tokens · costs in $ ·
model output · log content · IP address or IP-derived precise location · any free-text
the user typed · stable machine identifiers. These get an explicit **guardrail test**
(`test_telemetry_redaction.py`) asserting the serializer drops anything outside the
allowlist — so a future careless `feature.used("opened /Users/me/secret-repo")` can't
leak. Unknown or junk event names are also dropped server-side by the Worker.

---

## 4. Architecture — Cloudflare Workers Analytics Engine

### Why Cloudflare Analytics Engine (AE)

The telemetry sink is a **Cloudflare Worker** that writes data points into
**Analytics Engine** (AE), Cloudflare's purpose-built append-only time-series store.

Key reasons this was chosen over alternatives:

- **No key ships in the app.** The Worker writes to AE via an account-bound
  `env.TELEMETRY` binding — there is nothing to configure in the app, no secret to
  rotate, and no credentials in the repo.
- **Free tier is large.** AE free tier: **100 k data points/day written** +
  **10 k read queries/day**; **90-day (3-month) raw retention**. Compare to
  alternatives considered: managed analytics SaaS free tiers cap at ~20 k
  events/month (roughly 150× smaller). AE's per-day budget scales comfortably
  with early-stage usage.
- **Full data ownership.** Events never touch a third-party analytics processor;
  they live in your Cloudflare account, queryable via the AE SQL API or Grafana.
- **No built-in dashboard (accepted trade-off).** AE has no point-and-click UI;
  query via SQL API or connect Grafana. For long-term trends beyond 90-day raw
  retention, a **Cron-triggered Worker → D1/R2 rollup** is the planned future path.

### Data flow

```
frontend (page event, feature.used, …)
    │
    │  POST /telemetry/event   (loopback, backend bridge)
    ▼
backend/telemetry.py  telemetry.emit()
    │  allowlist-serializes + redacts on the backend before dispatch
    │
    │  POST https://tt-telemetry-proxy.tokentelemetry.workers.dev/event
    ▼
Cloudflare Worker  (tt-telemetry-proxy)
    │  re-validates event name against allowlist
    │  derives coarse country from CF-edge header (never raw IP)
    │  drops unknown / junk event names
    │
    ▼
env.TELEMETRY.writeDataPoint(…)  →  AE dataset: tt_telemetry
```

`DEFAULT_PROXY_URL` in `backend/telemetry.py` is set to
`https://tt-telemetry-proxy.tokentelemetry.workers.dev`. No key, no credentials,
no DNS record to manage — the Worker is already deployed.

### Schema (AE data point)

Each `writeDataPoint` call records:

| AE field type | Fields |
|---|---|
| `blobs` | `event`, `os`, `app_version`, `session_id`, `agents`, `summarizer_backend`, `country`, `props_json` |
| `doubles` | (reserved for future numeric metrics, e.g. summary latency bucket) |
| `indexes` | `event` (for efficient per-event cardinality filtering) |

### Querying

```sql
-- DAU (distinct sessions per day)
SELECT toDate(timestamp) AS day, count(DISTINCT session_id) AS dau
FROM tt_telemetry
WHERE event = 'app.launched'
GROUP BY day ORDER BY day DESC;

-- Feature adoption
SELECT blob2 AS feature, count() AS uses
FROM tt_telemetry
WHERE event = 'feature.used'
GROUP BY feature ORDER BY uses DESC;
```

Read via: `https://api.cloudflare.com/client/v4/accounts/{id}/analytics_engine/sql`
or Cloudflare's Grafana datasource plugin.

### Alternatives considered

Managed analytics SaaS (e.g. Aptabase): rejected — free tier capped at ~20 k
events/month vs AE's 100 k/day, and a third-party key would need to ship in or
near the app. Self-hosted ClickHouse-based stacks: rejected — significant ops burden
for early-stage signal.

---

## 5. Consent & control UX

Mirror the existing cookie-consent (website) + `update_check` toggle (app) patterns,
but **default-on (opt-out)** — the user is *informed*, not asked permission.

1. **First-run notice** (one time, like the website cookie banner, dismissible) —
   informs that telemetry is **already on**:
   > "Anonymous usage stats are **on** to help improve TokenTelemetry — which pages
   > and features you use, never your code, prompts, paths, or costs.
   > **[See exactly what]** · **[Keep it on]** · [Turn off]"
   Both "Keep it on" and "Turn off" are equally weighted, visible choices (not a
   buried link). Non-interactive/CI launches don't show it — and, because there's no
   one to inform, **CI/non-interactive defaults to NOT emitting** (informed-consent
   can't be satisfied unattended; avoids silent server collection). The user's choice
   is persisted in the local prefs DB as `telemetry_notice_ack`.
2. **Settings → "Usage & privacy"**: a toggle (default **on**), a live **payload
   preview**, a link to the privacy policy, and the env-override status (read-only when
   `TT_NO_TELEMETRY` / `DO_NOT_TRACK` is set — exactly like update-check's
   `env_forced_off`).
3. **Opt-out is immediate.** `DO_NOT_TRACK=1` is honored as a pre-emptive opt-out
   (never emits, never shows the notice). `TT_NO_TELEMETRY=1` is a hard policy
   override (for org/CI environments).

---

## 6. Anonymous identity

- A **random `session_id`** (UUID) is generated fresh at each app launch. It groups
  events within one session but never persists across launches, so it cannot become
  a long-term tracker.
- No stable ID is stored or derived from hostname, MAC, disk serial, or any hardware
  value. Opt-out does not need to "delete" an id because none is persisted.
- The Worker never records or logs IP addresses; the only location signal is a coarse
  country code derived from Cloudflare's edge routing header.

---

## 7. Implementation surface (mirrors `update_check` almost exactly)

**Backend**
- `backend/harness_config.py`: `DEFAULT_PREFERENCES` includes:
  ```python
  "telemetry": True,           # opt-OUT: ON by default (cf. update_check). CI/
                               # non-interactive + DO_NOT_TRACK/TT_NO_TELEMETRY force off.
  ```
- `backend/telemetry.py`: `enabled()` (pref AND not `TT_NO_TELEMETRY` AND not
  `DO_NOT_TRACK`), `emit(event, props)`, allowlist serializer + redaction guard,
  best-effort async POST to `DEFAULT_PROXY_URL`. Fail-open, never raises — same
  posture as `_update_check_enabled()` / the update fetch.
- `backend/main.py`: `POST /telemetry/event` bridge endpoint; `GET/POST
  /config/telemetry` (copies the `/config/update-check` handler including
  `env_forced_off` / `effective`); `GET /config/telemetry/preview` returning the
  exact next payload.
- `backend/test_telemetry_redaction.py`: asserts no non-allowlisted key, path, or
  free-text can be serialized. This is the guardrail that makes "anonymous"
  *verifiable*, per §3.3.

**Cloudflare Worker** (`proxy/`)
- Deployed to `tt-telemetry-proxy.tokentelemetry.workers.dev`.
- Receives events from the backend bridge, re-validates event names, derives coarse
  country from CF edge, writes to AE via `env.TELEMETRY.writeDataPoint()`.
- No secret is needed in the app; the Worker binding is account-bound on Cloudflare's
  side.

**Frontend** (`frontend/src/app/settings`)
- "Usage & privacy" card with the toggle + payload preview, wired to the backend
  endpoints (cloned from the update-check toggle component).
- First-run consent banner component; choice stored in prefs DB (`telemetry_notice_ack`),
  not just localStorage.

**Website** (`website/src/app/privacy/page.tsx`)
- Updated: "What we never collect" now states collects nothing by default; if
  telemetry is on, here is the exact, content-free list (no third-party analytics
  processor to disclose — AE is Cloudflare account-bound). Copy kept plain and
  verifiable.

**Env / docs**
- `TT_NO_TELEMETRY=1` and `DO_NOT_TRACK=1` documented next to `TT_NO_UPDATE_CHECK`.
- README + CHANGELOG note; `UPDATE.json` entry added per the project hook.

---

## 8. Example payloads

**In-app transparency preview ("See exactly what we send"):**
```json
{
  "schema": "tt-usage/1",
  "generated": "2026-06-15",
  "app_version": "1.4.2",
  "os": "darwin",
  "session_id": "a3f8…",
  "agents_detected": ["claude-code", "codex", "gemini-cli"],
  "summarizer_backend": "ollama",
  "usage_30d": {
    "pages": { "dashboard": 41, "analytics": 22, "traces": 18, "hermes": 0, "artifacts": 3 },
    "features": { "trace_summarized": 14, "analytics_local_filter": 9, "plan_library": 2 }
  }
}
```
*(Note the directly actionable signal: Hermes unused, local-model filter used 9×,
Artifacts barely touched.)*

**Per-event payload sent to the Worker (auto-send, opt-out model):**
```json
{ "event": "analytics.filtered",
  "props": { "dimension": "local-only" },
  "ctx": { "app_version": "1.4.2", "os": "darwin", "session_id": "a3f8…" } }
```

The Worker adds `country` at the edge before calling `writeDataPoint`; the raw IP
is never recorded.

---

## 9. Rollout phases (completed)

- **Phase 0 — instrument internally (no network):** `telemetry.emit()` call sites
  behind the (off) flag; redaction test. Nothing sent. Pure plumbing.
- **Phase 1 — transparency UI:** Settings "Share my stats" / preview panel + first-run
  notice. Honest, infra-free, doubles as the transparency UI.
- **Phase 2 — AE auto-send behind opt-out:** continuous signal via
  `tt-telemetry-proxy.tokentelemetry.workers.dev` → `writeDataPoint` → `tt_telemetry`.
  Privacy policy updated; no third-party processor to disclose.

All three phases are shipped.

---

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Brand betrayal / "even *they* track now" backlash | Default-on with loud first-run notice; payload preview; `DO_NOT_TRACK` / `TT_NO_TELEMETRY` honored; privacy copy rewritten |
| Accidental content leak in an event | Allowlist serializer + `test_telemetry_redaction.py` guardrail; re-validated server-side in the Worker |
| Telemetry slows/breaks app | Best-effort, async, fail-open — same as update-check |
| Re-identification via rare field combos | Coarse buckets, no paths/names, per-launch session_id only, low cardinality enums |
| Data beyond 90-day AE raw retention | Cron→D1/R2 rollup Worker (future); raw retention sufficient for initial signal |
| AE read query budget (10k/day) | Batch queries; cache Grafana results; budget is generous for dashboard use |

---

## 11. Decisions (locked 2026-06-15)

| Question | Decision |
|---|---|
| **Consent model** | **Opt-out — ON by default**, with a loud first-run notice + one-click off (§2.1, §5). Strictly anonymous, no personal data (§1b). Choice persisted as `telemetry_notice_ack`. |
| **Transport / sink** | **Cloudflare Workers Analytics Engine** via `tt-telemetry-proxy.tokentelemetry.workers.dev`. Frontend events bridge through `POST /telemetry/event` on the backend; backend calls `telemetry.emit()` which POSTs to the Worker; Worker writes via `env.TELEMETRY.writeDataPoint()` into dataset `tt_telemetry`. No analytics key ships in the app. |
| **First-run discovery** | **One-time first-run notice** stating telemetry is already on, with equal-weight *Keep on* / *Turn off* + *See exactly what*. CI/non-interactive: not shown **and** not emitting. |
| **Release gate** | **Homepage + `privacy/page.tsx` "we collect nothing / no telemetry endpoint" copy** rewritten to match on-by-default reality (§1a). Shipped with the feature. |
| **Build status** | **BUILT & DEPLOYED 2026-06-15.** Backend `telemetry.py` + bridge endpoint + redaction test (11/11 pass); frontend lib + first-run notice + Settings "Usage & privacy" card + page/filter emits; Cloudflare Worker deployed to `tt-telemetry-proxy.tokentelemetry.workers.dev`; privacy/FAQ/TrustStrip/llms.txt copy rewritten; `UPDATE.json` entry added. No maintainer steps remaining — the Worker is live and `DEFAULT_PROXY_URL` in `backend/telemetry.py` already points to it. |
