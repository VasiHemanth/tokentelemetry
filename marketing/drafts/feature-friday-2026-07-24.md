# Feature Friday — 2026-07-24

> Based on: `git log origin/main --since="7 days ago"` (Jul 17–23) + `origin/main:UPDATE.json`.
> **Note for maintainer:** the checked-out working branch (`feat/local-model-insights`) is *behind* `origin/main`, so I drafted from what's actually shipped on `origin/main`. Heads-up: **UPDATE.json's newest entry is dated 2026-07-12** — this week's features (below) don't have UPDATE.json entries yet, so I drafted straight from the `feat:` commits. Worth adding a release entry when you get a moment.
> Shipped this week (Jul 17–23, since the last Feature Friday on 07-17): **4 user-facing feature lines** — published artifacts per project (#193), reasoning/thinking effort for every agent that records one (#183), recurring-loop detection extended to Grok Build & Cline plus project loop tabs (#177), and a read-only agent feature-flags panel in Settings (#175). Plus fixes/perf: faster trace loading (#186), Hermes custom-endpoint $0 repricing (#178), OpenCode data-dir resolution (#179), Codex reasoning-summary normalization (#181/#182), refreshed models.dev pricing (#185), and Pi added to the supported-agents docs.
> This is a **feature** post (not a progress post) — plenty user-facing landed.

**Reviewer checklist before posting:**
- No contributor credits included: the four feature PRs (#175, #177, #183, #193) are all on `VasiHemanth/*` branches (maintainer). If any of the fix PRs (#178, #179, #181, #186) were community contributions, add a credit line before posting — I couldn't confirm external authorship from git alone.
- No numbers are invented — everything below is qualitative or comes directly from commit text.
- Headline is **published artifacts**. If you'd rather lead with reasoning-effort (more broadly relevant — it touches 6 agents), it swaps into the hook cleanly.
- Suggested visuals are marked inline; grab fresh screenshots from a running instance.

---

## X / Twitter Thread

**Tweet 1 — Hook**

Your coding agents have been quietly publishing pages and writing plan docs this whole time — you just had to go digging through `~/.claude` and `~/.gemini` to find them.

TokenTelemetry now surfaces every artifact your agents produce, grouped under the project they belong to.

Big week 🧵

*[Suggested visual: the new project Artifacts tab in Cards view — the scaled-down page previews + Antigravity doc cards]*

---

**Tweet 2 — Published artifacts**

Claude Code publishes hosted pages; Antigravity writes task / plan / walkthrough docs per session. Both now roll up into a new **Artifacts tab** on each project.

Cards view renders a live scaled-down preview of each page (sandboxed, click-through to the real URL); List view is a compact index. And because links are cached, they outlive the deleted transcript that made them.

---

**Tweet 3 — Reasoning effort**

Ever wonder what "thinking level" a session actually ran at?

Open a session and the context panel now shows the reasoning effort for every agent that records one — Claude, Codex, Grok, Copilot, Hermes, and Pi. If a run changed effort mid-way, you see the progression (e.g. `medium → xhigh`) and the exact reasoning card where it switched.

---

**Tweet 4 — Loops beyond Claude**

Recurring-loop detection isn't Claude-only anymore.

TokenTelemetry now catches **Grok Build** `/loop` schedules and **Cline** Scheduled Agents (from its cron.db) too — cadence, fire count, and lifecycle (active / expired / cancelled). Loops now also show up right inside a project's Config and Insights tabs, not just global Analytics.

---

**Tweet 5 — Agent feature flags**

New read-only panel in Settings: see which experimental/preview flags each agent has switched on in its *own* config — Copilot's `experimental`, Codex `[features]`, Claude's toggles.

Each card tells you the exact command to flip it yourself + links the official docs. Secret-free by design (allowlisted keys only — no tokens ever dumped).

---

**Tweet 6 — Close + install**

All of it is free, open source, and 100% local — nothing leaves your machine.

```
curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash
```

GitHub → https://github.com/VasiHemanth/tokentelemetry

---

## Discord #announcements Post

**TokenTelemetry — Feature Friday (2026-07-24)**

Good week for visibility into what your agents are actually doing. The highlights:

- **🗂️ Published artifacts, grouped by project.** Claude Code's hosted pages and Antigravity's task/plan/walkthrough docs now surface in a new **Artifacts tab** on each project. Cards view shows a live (sandboxed) preview of each page and an expandable preview for Antigravity docs; a compact List view is a click away, and your choice is remembered. Links are cached, so they survive even after the original transcript is pruned. No more digging through `~/.claude` or `~/.gemini` to find what a run produced.
- **🧠 Reasoning / thinking effort for every agent that records one.** The session context panel now shows the effort level for **Claude, Codex, Grok, Copilot, Hermes, and Pi** (Pi's row is labelled "Thinking Level", its own term). Agents that change effort mid-run show the progression — e.g. `medium → xhigh` — and each reasoning card in the trace carries the effort in effect at that step, so you see exactly where it switched.
- **🔁 Loop detection now covers Grok Build & Cline.** Recurring-loop tracking extended beyond Claude Code to **Grok Build** (`/loop` scheduler) and **Cline** ("Scheduled Agents" from its cron.db) — cadence, fire count, and lifecycle (active/expired/cancelled). Loops also now appear directly in a project's **Config** (inventory) and **Insights** (breakdown) tabs, with per-project numbers that match global Analytics exactly.
- **🚩 Agent feature flags in Settings.** A read-only panel surfaces the experimental/preview features each agent has enabled in its own local config (Copilot `experimental`, Codex `[features]`, Claude Code toggles). Each card shows the exact command/config path to change it yourself and links the official docs. Agents whose flags live in an opaque store (Antigravity, Cursor) are named honestly rather than silently dropped. Allowlisted, secret-free keys only — no auth tokens are ever read out.
- **🛠️ Fixes & perf:** trace loading is noticeably faster (mtime cache + O(n²)→O(n) pairing, #186); Hermes sessions on custom/proxy endpoints no longer misreport as $0.00 (#178); OpenCode's data dir resolves correctly across platforms/env, not just `~/.local/share` (#179); Codex structured reasoning summaries render cleanly (#181/#182); pricing data refreshed from models.dev (#185); Pi added to the supported-agents docs.

Update:
```
curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash
```

Full changelog: https://github.com/VasiHemanth/tokentelemetry/commits/main

---

## LinkedIn Post

**If an AI agent published a page or ran a scheduled loop overnight, could you find it the next morning? This week TokenTelemetry got a lot better at answering that.**

TokenTelemetry is a free, open-source, 100%-local dashboard for what your AI coding agents actually do and cost. Four things shipped this week, and the thread connecting them is the same one that matters if you're the person accountable for how these tools get used: the work agents do on their own is the hardest to see.

**The artifacts your agents produce now have a home.** Claude Code publishes hosted pages; Antigravity writes plan and walkthrough documents for each session. Until now those lived scattered in hidden folders on disk. They now roll up into an Artifacts tab on the relevant project — with live previews and cached links that survive even after the agent prunes the original transcript. The output of an autonomous run is no longer something you have to go spelunking for.

**You can see how hard a model was thinking.** The session view now surfaces the reasoning/thinking effort for every agent that records one — Claude, Codex, Grok, Copilot, Hermes, and Pi — including runs that shifted effort mid-session (shown as a progression like "medium → xhigh"). For anyone reasoning about quality-versus-cost tradeoffs, that setting was previously invisible.

**Scheduled and recurring work is easier to catch.** Loop detection now covers Grok Build and Cline in addition to Claude Code, and those loops surface directly inside each project rather than only in global analytics — with their cadence, fire count, and whether they're still active. Recurring, unattended workloads are exactly the ones that quietly run up usage; this makes them a visible line item.

**And your team's experimental settings are auditable.** A new read-only Settings panel shows which preview/experimental flags each agent has turned on in its own config, with the exact command to change them and a link to the docs — secret-free by design.

The through-line for anyone managing AI-agent adoption: the autonomous parts — what agents publish, how hard they think, what runs on a schedule, what's switched on — are the hardest to observe and the easiest to lose track of, and they're exactly what got more visible this week. Everything stays local and inspectable; nothing leaves your machine.

Free and open source, one line to install:

```
curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash
```

→ https://github.com/VasiHemanth/tokentelemetry
