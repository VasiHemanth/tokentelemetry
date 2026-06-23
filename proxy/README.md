# Telemetry sink

The app sends anonymous, content-free usage events to a **Cloudflare Worker**,
which writes them into **Workers Analytics Engine** (Cloudflare's time-series
store). The app ships only the Worker's public URL — and because Analytics
Engine is written through an **account-bound binding**, there is **no API key
anywhere in the request path** and **no credential in the open-source app to
extract**. The Worker also never reads or stores the client IP; it records only
the coarse 2-letter country from Cloudflare's edge.

```
App backend (telemetry.py)  ──POST event──▶  WORKER  ──writeDataPoint()──▶  Analytics Engine
   ships only the Worker URL                 no key in path,                 (3-month retention)
                                             strips IP, adds country
```

> **Note:** if you ran an earlier build that used a third-party analytics key as
> a Worker secret, you can delete it — Analytics Engine needs no key:
> `wrangler secret delete APTABASE_KEY` (only if it still exists).

---

## Deploy (Cloudflare Worker)

From `proxy/cloudflare/`:

```bash
npm install
npx wrangler login          # one-time, opens browser
npx wrangler deploy         # provisions the dataset + deploys the Worker
```

That's it — no secret to set. `wrangler.jsonc` already declares the binding:

```jsonc
"analytics_engine_datasets": [
  { "binding": "TELEMETRY", "dataset": "tt_telemetry" }
]
```

The dataset `tt_telemetry` is auto-created on first deploy. The app already
points at `https://tt-telemetry-proxy.tokentelemetry.workers.dev`
(`DEFAULT_PROXY_URL` in `backend/telemetry.py`); override at runtime with
`TT_TELEMETRY_URL=https://…`.

**Verify the Worker is up:**
```bash
curl -X POST https://tt-telemetry-proxy.tokentelemetry.workers.dev \
  -H 'content-type: application/json' \
  -d '{"eventName":"app.launched","sessionId":"test","systemProps":{},"props":{}}'
# -> 204 (empty). A GET returns a plain-text health string.
```

---

## Reading the data (no built-in dashboard)

Analytics Engine has **no UI** — you query it. Two ways:

### 1. SQL API (quick checks)
```bash
curl "https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/analytics_engine/sql" \
  -H "Authorization: Bearer <API_TOKEN_with_Account_Analytics_Read>" \
  -d "SELECT blob1 AS event, count() AS n
      FROM tt_telemetry
      WHERE timestamp > now() - INTERVAL '7' DAY
      GROUP BY event ORDER BY n DESC"
```

#### Budgets & alerts adoption

The budget feature emits `feature.used` with `blob8` set to one of two labels:
`budgets` (opened the editor) and `budget-set` (saved a budget). No limit value
or amount is ever sent — only the label. To see how many people use it and how
often they configure one, over the last 30 days:

```sql
SELECT blob8 AS action,
       count() AS events,
       count(DISTINCT blob2) AS sessions   -- blob2 = per-launch session id
FROM tt_telemetry
WHERE blob1 = 'feature.used'
  AND blob8 IN ('budgets', 'budget-set')
  AND timestamp > now() - INTERVAL '30' DAY
GROUP BY action
```

`sessions` for `budgets` is the adoption number (how many launches opened the
editor); `events` for `budget-set` is the configure count (the "clicks").
sessionId resets every launch and isn't linkable, so this is a usage floor, not
a unique-user count.

### 2. Grafana (the "holistic picture")
Install the official **Cloudflare Analytics Engine** Grafana data-source plugin,
point it at the SQL API with the same token, and build panels (DAU, top routes,
agent mix, summary outcomes). This is the recommended long-term dashboard.

### Schema (positional columns)
`writeDataPoint` stores fields by position; remember these when writing SQL:

| Column | Meaning | Column | Meaning |
|---|---|---|---|
| `index1` / `blob1` | eventName | `blob9` | dimension (`analytics.filtered`) |
| `blob2` | sessionId (per-launch) | `blob10` | summary backend |
| `blob3` | osName | `blob11` | summary outcome |
| `blob4` | osVersion | `blob12` | retention tier |
| `blob5` | deviceModel (arch) | `blob13` | agents (csv) |
| `blob6` | appVersion | `blob14` | summarizer_backend (context) |
| `blob7` | route (`page.viewed`) | `blob15` | country (edge, no IP) |
| `blob8` | feature name (`feature.used`) | `blob16` | sdkVersion |
| `double1` | agent_count | `double2` | isDebug (0/1) |

Plus the automatic `timestamp` and `_sample_interval` columns.

---

## Free tier, retention, cost

- **Free (Workers Free plan):** 100,000 data points/day written + 10,000 read
  queries/day (~3M events/month).
- **Retention: 3 months.** Raw points older than 90 days are dropped. For longer
  trends, run a Cron-triggered Worker that periodically `SELECT`s aggregates and
  writes them to **D1** or **R2** (both free) — AE = recent firehose, D1/R2 =
  permanent rollups.
- **Overage (Paid plan only):** $0.25 / million data points, $1 / million read
  queries. On Free you simply stop writing past the daily cap; you are not billed.

---

## Abuse & DDoS — threat model

This endpoint is **public and write-only**. Worst case is polluted analytics or a
day of burned free-tier quota — **no data breach, no user harm, no bill**.

**Already mitigated**
- **DDoS (L3/L4):** automatic and free on Cloudflare — volumetric floods are
  absorbed at the edge before reaching the Worker.
- **Junk events:** the Worker validates method, `Content-Type`, body size
  (≤8 KB), event name (`ALLOWED_EVENTS`), and `sessionId`; anything else is
  silently dropped (`204`, so a probe gets no signal). Junk never reaches the
  dataset.
- **No key to leak:** there is no credential in the request path at all.

**Add if abuse appears**
- **Rate limiting (L7):** Cloudflare dashboard → Security → WAF → Rate limiting,
  e.g. *“>30 requests / 1 min / client IP → Block”*. The free plan includes one
  rule.

**Deliberately NOT done**
- **Request signing:** the app is open-source, so any shipped secret is
  extractable — a signature would be security theater. We rely on rate-limiting
  to cap abuse and on the cheap write path (Analytics Engine) to absorb noise.
