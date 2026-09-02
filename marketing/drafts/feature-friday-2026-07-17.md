# Feature Friday — 2026-07-17

> Based on: `git log origin/main --since="7 days ago"` + `origin/main:UPDATE.json`.
> **Note for maintainer:** the checked-out working branch (`feat/local-model-insights`) is *behind* `origin/main`, so I drafted from `origin/main`, which is what's actually shipped. Its UPDATE.json has newer entries than the working tree's.
> Shipped this week (Jul 11–16, since the last Feature Friday on 07-10): **5 feature lines across 4 UPDATE.json releases** — /loop telemetry (#169), Pi Coding Agent support (#135), and the three-part Hermes profiles suite (per-profile usage, burn/budgets/kanban, and a profile diff view, #143). Plus fixes: subagent token attribution in traces (#166), auth-token redaction in access logs, Windows uvloop install, dashboard/analytics scope labels (#168), and a dependabot + committed-lockfile hardening pass.
> This is a **feature** post (not a progress post) — plenty user-facing landed.

**Reviewer checklist before posting:**
- Contributor credits are pulled straight from UPDATE.json: Pi support thanks **Tharun-tharun** (issue #135); profile diff thanks **mvinca-bandwidth** (issue #142). Confirm handles/spelling before posting publicly.
- No numbers are invented — everything below is qualitative or comes from commit/UPDATE.json text.
- If you'd rather not lead with /loop, the Hermes profiles suite is the bigger story and swaps into the hook cleanly.

---

## X / Twitter Thread

**Tweet 1 — Hook**

Ever left a `/loop` or a cron running overnight and found out from the bill?

TokenTelemetry now detects recurring loops from the actual scheduling calls — active, expired, or cancelled — and shows what each one is quietly costing.

Big week. Here's everything that shipped 🧵

*[Suggested visual: the new "Recurring loops" section in Analytics, or a session trace header showing the Loop badge]*

---

**Tweet 2 — /loop telemetry**

Open any session trace and the header now shows a Loop badge with its live state and cadence — which loop ran, its job id, and why it ended.

Analytics gets a "Recurring loops" section counting active/expired/cancelled loops with their fire counts and cost. A forgotten hourly loop burning tokens is now obvious instead of invisible.

---

**Tweet 3 — Hermes profiles**

If you run multiple Hermes profiles (work, personal, per-client), you now get real per-profile cost visibility:

Scope the whole dashboard to one profile. Per-card 14-day sparkline + 7-day burn, with the share spent *unattended* (cron, subagents, kanban workers) broken out — so the overnight-swarm surprise gets caught early.

---

**Tweet 4 — Hermes: kanban + diff**

Two more for the profile crowd:

A Kanban cost board prices every swarm task by its linked session — per-worker lanes, failure/retry burn included.

And a profile diff view: pick any two profiles, see sessions, tokens, cost, burn and top models side by side. (thanks @ the contributor who requested it 🙏)

---

**Tweet 5 — Pi Coding Agent + fixes**

Pi Coding Agent is now supported — its sessions show up automatically, grouped by project with full traces, priced per-turn (local/Ollama turns by electricity). Nothing to configure.

Also fixed: dynamic-subagent tokens now attribute correctly in Claude traces, and the auth token is redacted from access logs.

---

**Tweet 6 — Close + install**

All of it is free, open source, and 100% local — nothing leaves your machine.

```
curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash
```

GitHub → https://github.com/VasiHemanth/tokentelemetry

---

## Discord #announcements Post

**TokenTelemetry — Feature Friday (2026-07-17)**

Busy week — a lot landed. The highlights:

- **🔁 See which sessions ran a loop.** Session traces now carry a **Loop badge** (active / expired / cancelled) with the loop's cadence and job id, and Analytics has a new **Recurring loops** section that counts them and shows their cost. Detected from the real scheduling calls, so it catches loops even when the `/loop` command left no trace — a forgotten hourly loop quietly burning tokens is easy to spot now.
- **👤 Hermes profiles: per-profile cost.** Filter the whole dashboard by profile (or view all, color-matched to Hermes desktop). Each profile card shows a 14-day sparkline, 7-day burn with trend, and how much was spent **unattended** (cron/subagents/kanban workers). Set an alerts-only monthly budget right on the card.
- **🗂️ Kanban swarm board with per-task cost.** Every board's tasks by status, each priced by its linked session, with per-worker cost lanes and failure/retry burn.
- **⚖️ Profile diff view.** Pick any two profiles and compare sessions, tokens, cost, burn and top models side by side. Thanks to **mvinca-bandwidth** for requesting this (issue #142)!
- **🤖 Pi Coding Agent support.** Pi sessions are detected and tracked automatically alongside Claude Code, Codex, Cursor and the rest — full traces, per-turn cost, local-model turns priced by electricity. Thanks to **Tharun-tharun** for requesting it (issue #135)!
- **🛠️ Fixes:** dynamic-workflow subagent tokens now attribute correctly in Claude traces (#166); auth token is redacted from uvicorn access logs; clearer total-tokens/cost scope labels on dashboard vs analytics (#168); Windows uvloop install fixed; committed lockfiles + dependabot added for supply-chain hygiene.

Update:
```
curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash
```

Full changelog: https://github.com/VasiHemanth/tokentelemetry/commits/main

---

## LinkedIn Post

**Where did the tokens go? This week TokenTelemetry got a lot better at answering that.**

TokenTelemetry is a free, open-source, 100%-local dashboard for what your AI coding agents actually cost. Three things shipped this week that matter if you're the one who has to explain the bill.

**Forgotten loops now have a paper trail.** It's easy to schedule a recurring prompt — a `/loop`, a cron, a self-perpetuating agent — and forget it's running. TokenTelemetry now detects those loops from the real scheduling calls (not just the command text, so it catches them even when nothing was logged) and surfaces them two ways: a Loop badge on the session trace showing whether it's still active, and a "Recurring loops" section in Analytics that counts them and totals their cost. The quiet overnight token burn becomes a line item you can see.

**Cost attribution per persona.** For teams running multiple Hermes profiles — work vs. personal, or one per client — each profile now reports its own sessions, tokens, cost, and 7-day burn, with the portion spent *unattended* (cron jobs, subagents, swarm workers) broken out separately. You can set an alerts-only monthly budget per profile, get a per-task cost board for swarm work, and diff any two profiles side by side. It's observational — TokenTelemetry never blocks an agent — so it answers "which persona is driving spend, and is it attended or autonomous?" without getting in the way.

**One more agent covered.** Pi Coding Agent joins the supported list; its sessions are detected automatically and priced per turn, including local/Ollama turns billed by electricity rather than API rates.

The through-line for anyone managing AI-agent spend: autonomous and recurring workloads are the hardest to see and the easiest to overspend on, and they're exactly what got more visible this week. Everything is local and inspectable — nothing leaves your machine.

Free and open source, one line to install:

```
curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash
```

→ https://github.com/VasiHemanth/tokentelemetry
