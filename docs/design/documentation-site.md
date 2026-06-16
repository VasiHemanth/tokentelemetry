# Design: Documentation site + community resources

A per-feature documentation section (shadcn-style) and a curated community
resources page, added to the existing marketing site. Decision recorded in
[ADR-0003](../adr/0003-docs-site-fumadocs.md).

## Goal

Today `website/` is a Next.js 16 marketing site (static export → GitHub Pages,
custom domain `tokentelemetry.com`). It sells the product but doesn't *teach* it.
We want two new surfaces:

1. **Docs** — one page per feature (like shadcn's component docs): what it is, a
   screenshot, a short video walkthrough, how to use it, how to configure it.
   Reachable both from the public site (discovery/SEO) **and** from inside the
   locally-running app (where installed users actually are).
2. **Resources** — a curated directory of community-built blocks (skills, hooks,
   MCP servers, workflows, guides) with a one-line summary and link each, so
   users can lift things into their own workflow.

Planning only — this doc is the blueprint; implementation follows in a later PR.

## Two audiences, one source of truth

The product runs locally (`frontend/` on `localhost`). The people who most need
feature docs are **installed users**, who have no reason to revisit the marketing
site. So docs serve two audiences from a single hosted source:

- **Pre-install / discovery** — someone googling "how does TokenTelemetry track
  subagent cost" lands on `/docs/...`. Doubles as SEO and onboarding.
- **Post-install / in-app** — the local app gets a global **Docs** link plus
  per-page contextual help icons that **deep-link out** to the matching hosted
  page (e.g. the Hermes page's help icon opens `tokentelemetry.com/docs/hermes`
  in the browser).

The local app **does not bundle a copy** of the docs — it links to the live ones.
One source of truth, never stale, zero added download weight. (The MDX files live
in the repo, but the repo is only cloned by contributors; end users install the
published app, which never includes `website/`.)

## Architecture

```
website/  (existing Next.js 16 app, output: "export" → GitHub Pages)
├── src/app/
│   ├── page.tsx              marketing home (unchanged)
│   ├── docs/[[...slug]]/     ← Fumadocs route group (NEW)
│   └── resources/            ← community blocks page (NEW)
├── content/docs/            ← MDX, one file per feature (NEW)
│   ├── index.mdx · installation.mdx · quick-start.mdx · supported-agents.mdx
│   ├── dashboard.mdx · analytics.mdx · projects.mdx · traces.mdx
│   ├── summarization.mdx · artifacts.mdx · hermes.mdx
│   ├── configure-summarizer.mdx · local-models.mdx · billing.mdx
│   ├── retention.mdx · privacy.mdx · remote-access.mdx · data-directory.mdx
│   └── cli-reference.mdx · faq.mdx · troubleshooting.mdx
└── content/resources.json   ← curated community blocks (NEW)

frontend/  (the local app)
└── Docs link in nav + per-page "?" help icons → deep-link to tokentelemetry.com/docs/<feature>
```

- **Framework: Fumadocs** — Next.js App-Router-native, Tailwind v4, MDX, builds
  under `output: "export"`. Shares the site's theme, header, domain. Sidebar
  auto-generates from `content/docs/` — adding a feature doc = adding one file.
- **Search: Orama static** — a prebuilt client-side index (required because static
  export has no server routes). The one deliberate config step for GitHub Pages.
- **Video: YouTube/Loom embeds** via a small `<VideoEmbed>` MDX component. Repo
  stays lean; recordings can be any length and re-recorded without a commit.
- **Screenshots: reuse** the 7 PNGs already in `website/public/screenshots/`.

## Information architecture (sidebar)

The content the docs must cover, grounded in the actual feature surface
(verified across `frontend/`, `backend/`, `bin/cli.js`). Each leaf is one MDX page.

### 1. Getting Started  *(user-prioritised)*
- **Introduction** — what TokenTelemetry is, local-first promise, who it's for,
  the "what you'll see" tour. Reuse `README.md` problem/solution table + `llms.txt`.
- **Installation** — three paths (curl one-liner, Windows PowerShell, clone & run).
  Requirements: Node 18+, Python 3.9+, npm, agents already installed.
- **Quick Start** — first launch, auto-detection, opening the dashboard, the
  `AGENT_HARNESS_NO_OPEN` note.
- **Supported Agents** — the 10 coding agents + Hermes, how each is detected
  (`~/.claude/`, `~/.codex/`, `~/.gemini/`, `~/.cursor/`, `~/.vscode/`,
  `~/.local/share/opencode/`, `~/.hermes/`, `~/.grok/`, `~/.qwen/`), and what each
  captures. Reuse `website/src/data/agents.ts`.

### 2. Features  *(one page each — the shadcn "per-element" model)*
- **Dashboard** — KPI strip (sessions, tokens, projects, API-equiv cost), live
  15s sync, connected-agents split (coding vs autonomous), recent-activity feed,
  agent/model distribution charts, local-power toggle.
- **Analytics** — date presets + custom range, granularity (day/week/month),
  agent/model multi-select filters, token area chart, cache efficiency, per-agent
  & per-model tables, and the **Delegation & Ecosystem** section (subagent spend,
  delegation ranking, skills used, MCP servers). Note the data-availability/
  durable-history notice. Cross-link [durable-history.md](durable-history.md).
- **Projects** — cards per working dir, search/sort/grid-vs-list, then the four
  sub-pages: **Activity**, **Insights** (365-day heatmap, streaks, tool usage),
  **Configuration** (skills/MCP/memory/commands/subagents/plugins with
  "installed but never used" overlays), **Plans** (extracted plan-mode output).
- **Traces / Session Detail** — replayable trace: Events/Messages/Tools/Artifacts/
  Plans tabs, kind-aware highlighting, step nav, timeline, honest labelling of
  encrypted reasoning, token/cost header, parent-session link for delegated work.
- **Trace Summarization**  *(user-prioritised)* — deterministic **brief** (What /
  Tools / Why / Next) vs LLM **narrative**; Generate/Regenerate; caching by
  content hash; classified (never-raw) error cards. Configuration lives under §3.
- **Artifacts** — screenshots, browser recordings (Antigravity thumbnail strips),
  documents (task.md / plan.md / walkthrough.md) viewable inline.
- **Hermes Agent** — autonomous-agent hub: gateway health, sources across 38
  platforms, per-call latency/cache-hit, cost-anomaly flags, scheduled jobs, plus
  the 7 sub-pages (Skills, Tools, Profiles, Soul, Memory, Gateway, Schedules).
  Cross-link the **Hermes Dashboard plugin** (port 9119 launcher).

### 3. Configuration & Guides  *(user: "how to configure")*
- **Configure the Summarizer** — pick a backend (Claude / Codex / Gemini / Qwen /
  Ollama / Antigravity / OpenAI-compatible), model pickers, OpenAI-compat tuning
  (endpoint, api_key, max_tokens, temperature, sampling, enable_thinking), and the
  per-backend timeout env vars (`TT_OLLAMA_TIMEOUT`, `TT_CODEX_TIMEOUT`,
  `TT_OPENAI_COMPAT_TIMEOUT`).
- **Local Models & Power Cost**  *(user-prioritised)* — wattage (chip-aware Apple
  Silicon defaults; the Measure button / 4s calibration), electricity rate
  ($/kWh), grid carbon intensity, local vs subscription endpoint classification,
  the energy/savings/CO₂ readouts. Reuse the `/local-models` page copy.
- **Billing & Cost Modes** — subscription / api / local / unknown, auto-detection
  per agent, manual override; "label only, never changes the math" caveat.
- **History & Retention** — durable history, per-agent retention, transcript
  archival opt-in, storage readout, delete-transcripts (keeps rollup).
- **Update Check & Privacy** — update-check toggle + `TT_NO_UPDATE_CHECK`;
  anonymous telemetry toggle + `TT_NO_TELEMETRY`; what is and isn't sent.
- **Custom Data Directory** — `--data-dir` / `TOKENTELEMETRY_DATA_DIR` /
  `TOKENTELEMETRY_HOME` precedence; what lives in `~/.tokentelemetry/`.
- **Ports & Networking** — `--port` / `--api-port`, `NEXT_PUBLIC_API_PORT`,
  port-in-use behaviour.
- **Remote Access** — `--host`, auto-generated token, `--auth-token`,
  `--allowed-origins`, QR scan-to-open, `--insecure-no-auth` (tailnet only), and
  the SSH-tunnel pattern. Stress: token is the boundary, CORS is not.

### 4. Reference
- **CLI & Environment** — full flag table + every `TT_*` / `TOKENTELEMETRY_*` /
  `OPENAI_COMPAT_*` / `HERMES_HOME` env var.
- **Data Directory Layout** — every file in `~/.tokentelemetry/` and its purpose.
- **FAQ** — reuse the 9 site FAQ items + README FAQ.
- **Troubleshooting** — per-agent "not detected", ports, summarizer failures,
  remote-access auth.

### 5. Resources  *(separate top-level tab — not part of docs nav)*
- Data-driven cards from `content/resources.json`
  (`{ title, author, url, summary, tags }`), with tag filters
  (`skill` / `hook` / `mcp` / `workflow` / `guide`) and text search. Adding a
  resource = one JSON entry. **Hand-curated for v1**; community submission via a
  GitHub issue-form → PR that appends to the JSON is a fast-follow.

## Per-feature page template

Every Features page follows the same shape so they read consistently and are
cheap to author:

```
1. One-paragraph overview — what it does, why you'd use it
2. Screenshot (existing PNG)
3. <VideoEmbed id="..."/> — short walkthrough (YouTube/Loom)
4. "How to use" — numbered steps for the common path
5. Options / configuration — toggles, filters, settings that affect it
6. Tips & gotchas — edge cases, empty states, honest limitations
7. Related — links to adjacent docs and the in-app page
```

## Hosting & placement decisions

Settled with the maintainer (see [ADR-0003](../adr/0003-docs-site-fumadocs.md)):

- **GitHub Pages, same `website/` app, same domain.** No new infra; the existing
  `deploy-website.yml` already rebuilds on `website/**`.
- **Subdirectory, not subdomain** — `tokentelemetry.com/docs` + `/resources`, not
  `docs.tokentelemetry.com`. A subdirectory inherits the main domain's accumulated
  authority and consolidates ranking signals (search engines treat a subdomain as
  a largely separate site); docs are the project's strongest long-tail SEO asset,
  so they should feed and draw from the main domain. Also: zero DNS work, one
  analytics property, unified branding, one codebase.
- **Fumadocs over Nextra / Docusaurus / a hosted SaaS** — native to the existing
  Next.js + Tailwind stack, shadcn-style aesthetic, MDX-per-feature, static-export
  compatible, self-hosted (matches the local-first/own-your-stack ethos).
- **YouTube/Loom embeds over committing video** — keeps the repo and the
  contributor clone lean; recordings can be re-done without touching git.

## Build sequence (when greenlit)

1. Scaffold Fumadocs in `website/`: route group, MDX source, Orama static search,
   `<VideoEmbed>`, add **Docs** + **Resources** to `SiteHeader`. Verify
   `npm run build` still produces a clean static export to `out/`.
2. Author **Getting Started** + **Features** pages (reuse screenshots,
   `features.ts`, `agents.ts`, README/llms.txt prose).
3. Author **Configuration & Guides** + **Reference** pages (CLI/env tables from
   `bin/cli.js` + backend).
4. Build **/resources** (cards, `resources.json`, tag filter + search).
5. Record & embed walkthrough videos.
6. Add in-app **Docs** nav link + per-page help deep-links in `frontend/`.
7. Fast-follow: community-submission issue-form → PR flow for resources.

## Out of scope (tracked on the board)
- **Offline in-app docs** — serving a stripped MDX copy from the local backend at
  `localhost:8000/docs`. Deliberately deferred: link-out is simpler and never
  stale. Revisit only if users ask for offline docs.
- A second `docs.` subdomain (would only make sense if docs became their own
  product with a separate team).
- Auto-generating docs from code; versioned docs; i18n; in-page interactive demos.
- Migrating the marketing home or `DESIGN.md`/ADRs into Fumadocs.

## Open questions
- Resources curation model for v1 confirmed **hand-curated**; community-submission
  flow is a fast-follow, not a launch blocker.
- Whether `cli-reference` should be hand-maintained or generated from `bin/cli.js`
  `--help` (lean hand-maintained for v1).
