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

#### Is a newly added harness actually working?

`harness.scanned` fires once per launch for each agent detected on the machine,
carrying that agent (`blob17`) and how many sessions its reader returned as an
order-of-magnitude bucket (`blob18`) — never a raw count. A row with
`blob18 = '0'` is the interesting one: the harness is installed and we found
nothing, which is the shape of a broken reader.

```sql
SELECT blob17 AS agent,
       blob18 AS sessions,
       count(DISTINCT blob2) AS launches   -- blob2 = per-launch session id
FROM tt_telemetry
WHERE blob1 = 'harness.scanned'
  AND timestamp > now() - INTERVAL '30' DAY
GROUP BY agent, sessions
ORDER BY agent, sessions
```

An agent whose launches sit overwhelmingly in the `0` bucket is failing in the
field even though it detects fine. That is the exact state DeepSeek Harness
shipped in, and it took a bug report to find.

To ask the narrower question — do people ever *open* a given harness panel —
use `page.viewed`, which is gated behind a real browser interaction and so is
far less bot-contaminated than anything hanging off launch:

```sql
SELECT blob17 AS agent, count() AS views, count(DISTINCT blob2) AS launches
FROM tt_telemetry
WHERE blob1 = 'page.viewed' AND blob7 = 'agent-panel'
  AND timestamp > now() - INTERVAL '30' DAY
GROUP BY agent ORDER BY views DESC
```

#### Recurring users (`app.active`)

`app.active` is sent at most once per local day per install, and only after a
real UI interaction, so headless launches and bots that only hit
`app.launched` never produce one. It carries no install id. Instead the app
keeps a local file of dates (never sent) and reports coarse bands, which the
Worker stores as doubles holding each band's **lower bound in days**:

| Column | Prop | Values |
|---|---|---|
| `double3` | first_in_week | 1 on the install's first active day of the local ISO week |
| `double4` | first_in_month | 1 on the first active day of the local calendar month |
| `double5` | install_age | `0` (0d), `1` (1-6d), `7` (7-29d), `30` (30-89d), `90` (90d+) |
| `double6` | gap since last active day | `1` (1d), `2` (2-7d), `8` (8-30d), `30` (30d+), `-1` new install, `-2` first event after upgrading an existing install |
| `double7` | freq_28d, active days in last 28 | `1`, `2` (2-4), `5` (5-12), `13` (13+) |

Every other event also writes these slots (`0` for the flags, `-99` for the
bands), and so does an `app.active` with a missing or unknown label. **Always
filter `blob1 = 'app.active'`**, and exclude `-99` when aggregating a band.

Analytics Engine may sample, so weight by `_sample_interval` instead of
`count()`. The flags are 0/1, so `SUM(double3 * _sample_interval)` counts
installs.

```sql
-- DAU: one app.active per install per local day
SELECT toStartOfDay(timestamp) AS day,
       SUM(_sample_interval) AS dau
FROM tt_telemetry
WHERE blob1 = 'app.active' AND timestamp > now() - INTERVAL '30' DAY
GROUP BY day ORDER BY day

-- WAU: installs whose first active day of the week fell in this week
SELECT toStartOfWeek(timestamp) AS week,
       SUM(double3 * _sample_interval) AS wau
FROM tt_telemetry
WHERE blob1 = 'app.active' AND timestamp > now() - INTERVAL '90' DAY
GROUP BY week ORDER BY week

-- MAU: same idea per calendar month
SELECT toStartOfMonth(timestamp) AS month,
       SUM(double4 * _sample_interval) AS mau
FROM tt_telemetry
WHERE blob1 = 'app.active' AND timestamp > now() - INTERVAL '90' DAY
GROUP BY month ORDER BY month

-- New vs returning per day. "upgraded" (-2) is an existing install seen for
-- the first time since the upgrade: neither new nor a measurable return.
SELECT toStartOfDay(timestamp) AS day,
       SUM(if(double6 = -1, _sample_interval, 0)) AS new_installs,
       SUM(if(double6 > 0, _sample_interval, 0))  AS returning,
       SUM(if(double6 = -2, _sample_interval, 0)) AS upgraded
FROM tt_telemetry
WHERE blob1 = 'app.active' AND timestamp > now() - INTERVAL '30' DAY
GROUP BY day ORDER BY day

-- Returning users by gap: double6 >= 8 is someone coming back after a lapse
SELECT double6 AS gap_days_min, SUM(_sample_interval) AS active_days
FROM tt_telemetry
WHERE blob1 = 'app.active' AND double6 > 0
  AND timestamp > now() - INTERVAL '30' DAY
GROUP BY gap_days_min ORDER BY gap_days_min

-- Retention mix: how old are the installs that are active today?
SELECT double5 AS install_age_days_min, SUM(_sample_interval) AS active_days
FROM tt_telemetry
WHERE blob1 = 'app.active' AND double5 != -99
  AND timestamp > now() - INTERVAL '30' DAY
GROUP BY install_age_days_min ORDER BY install_age_days_min

-- Stickiness: active-day frequency, counted once per install per month.
-- double7 >= 13 means used on roughly every other day or more.
SELECT double7 AS active_days_28d_min,
       SUM(double4 * _sample_interval) AS installs
FROM tt_telemetry
WHERE blob1 = 'app.active' AND double7 != -99
  AND timestamp > now() - INTERVAL '90' DAY
GROUP BY active_days_28d_min ORDER BY active_days_28d_min
```

In the stickiness query `double7` comes from each install's first active day of
the month, so it describes the 28 days before that day. For a current view, use
`SUM(_sample_interval)` over the last 7 days instead, which weights heavy users
by the number of days they were active.

Known skews:

- **Local days vs UTC buckets.** The app decides "new day", "first in week" and
  "first in month" on the user's local calendar, but `timestamp` is UTC. An
  event near local midnight can land in the neighbouring UTC day, week or
  month, so the DAU/WAU/MAU edges are off by a few hours of traffic per zone.
  `toStartOfWeek` also buckets from Sunday, while the app's weeks start on
  Monday (ISO), so a user active on both Sunday and Monday is counted twice in
  one bucket and zero times in another. Totals over several weeks are unaffected.
- **Bot filter.** Because `app.active` needs a UI interaction, it undercounts
  anyone who only uses the API or MCP server without opening the dashboard. That
  is the intended trade for dropping the headless launches that inflate
  `app.launched`.
- **Opt-outs and upgrades.** Installs with telemetry off send nothing, and the
  first `app.active` after upgrading an older install is `upgraded` (`-2`), not
  `new`, so new-install counts start clean from the release that adds the event.

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
| `blob17` | agent — a *single* harness | `blob18` | volume (bucketed count) |
| `double1` | agent_count | `double2` | isDebug (0/1) |
| `double3` | first_in_week (`app.active`) | `double4` | first_in_month (`app.active`) |
| `double5` | install_age, days (`app.active`) | `double6` | gap, days; -1 new, -2 upgraded (`app.active`) |
| `double7` | freq_28d, days (`app.active`) | | |

Note `blob13` and `blob17` are different things: `blob13` is the whole detected
set as a CSV (context, on every event), `blob17` is one harness — the subject of
a `harness.scanned`, or the panel being viewed on a `page.viewed`. Positions are
append-only; renumbering silently re-labels every historical row.

`double3`..`double7` are written on every event, holding `0` (flags) and `-99`
(bands) outside `app.active`; filter on `blob1` before reading them. Analytics
Engine allows at most 20 blobs and 20 doubles per data point, and blobs are at
18, so new props should go into doubles where they can be expressed as numbers.

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
