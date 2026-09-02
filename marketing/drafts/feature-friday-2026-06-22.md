# Feature Friday — 2026-06-22

**What shipped this week (feat: commits, 2026-06-15 → 2026-06-21)**
- `feat(frontend)`: Antigravity session artifacts now surface in the trace Artifacts tab
- `feat(website)`: Documentation site (Fumadocs) + community resources page
- `feat(website)`: GA4 event instrumentation across all routes + SPA page_view
- `feat`: Anonymous product telemetry via Cloudflare Analytics Engine + website redesign

**Also landed (fix/chore):**
- Mobile nav menu on docs/website
- Pricing data refresh from models.dev
- Telemetry disclosure added to README
- Telemetry design docs retargeted to Cloudflare Analytics Engine

---

## 🐦 X/Twitter Thread

**Tweet 1 — Hook**
> TokenTelemetry now has real docs.
>
> A Fumadocs-powered documentation site just shipped — every concept, config flag, and integration explained in one place. Plus: Antigravity session artifacts are now visible in the trace view.
>
> 📸 Suggested asset: screenshot of the new docs site homepage or the Antigravity trace Artifacts tab
>
> Thread 🧵

---

**Tweet 2 — Docs site**
> The docs site is the thing I've been putting off longest.
>
> It's built on Fumadocs, lives alongside the main site, and has a Community Resources page for guides/integrations built by others.
>
> If you've been meaning to dig into how TokenTelemetry actually works — now there's a place for that.

---

**Tweet 3 — Antigravity artifacts**
> On the dashboard side: if you run Antigravity, the trace Artifacts tab now shows session artifacts alongside everything else.
>
> Before this, you'd have to dig in the file system to find what an Antigravity session produced. Now it's one click from the session view.

---

**Tweet 4 — Telemetry (transparency tweet)**
> We also added anonymous product telemetry this week — and yes, it's opt-out, disclosed in the README, and goes through Cloudflare Analytics Engine (no third-party data brokers).
>
> It tracks page views and feature events, nothing session-specific, nothing identifying.
>
> If you don't want it: TT_NO_TELEMETRY=1

---

**Tweet 5 — Close / Install**
> TokenTelemetry: 100% local, zero-config observability dashboard for AI coding agents.
>
> Tracks Claude Code, Codex, Cursor, Copilot, Grok Build, Antigravity, and more — tokens, costs, projects, subagents, all of it.
>
> Install in one line:
> ```
> curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash
> ```
>
> → https://github.com/VasiHemanth/tokentelemetry

---

## 💬 Discord #announcements

**TokenTelemetry — Feature Friday, June 22**

A few things landed this week:

**📚 Documentation site**
Finally. A real docs site, built on Fumadocs, with a Community Resources page for third-party guides and integrations. If you've been meaning to understand how something works under the hood, this is the place now.

**🗂 Antigravity session artifacts in the trace view**
If you use the Antigravity CLI or IDE, the Artifacts tab on any session page now shows what that session produced — no more hunting through your filesystem.

**📊 Anonymous product telemetry (opt-out)**
We added Cloudflare Analytics Engine-backed telemetry to understand which parts of the dashboard people actually use. It's opt-out (`TT_NO_TELEMETRY=1`), disclosed in the README, and no session data or identifying info is collected. The goal is to know whether we're building the right things.

**🌐 Website redesign**
The marketing site got a fresh pass alongside the docs launch.

---
Install: `curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash`
GitHub: https://github.com/VasiHemanth/tokentelemetry

---

## 🔗 LinkedIn Post

**When every AI coding agent has its own format for storing sessions, visibility into what you're actually spending is hard. TokenTelemetry was built to fix that — one local dashboard, no cloud, no config, 11 agents.**

This week, two things shipped that make it easier to get started and go deeper:

**A documentation site.** It's built on Fumadocs and covers every concept, configuration flag, and integration in one place. There's also a Community Resources page for guides and third-party integrations as the ecosystem grows. If you've been evaluating TokenTelemetry for your team and wanted proper docs before committing — that gap is closed.

**Antigravity session artifacts in the trace view.** For teams using the Antigravity CLI or IDE, session artifacts (files and outputs produced during a session) are now visible directly in the trace Artifacts tab. Previously you'd need to cross-reference the file system. Now it's part of the same session view where you already see tokens, cost, tool calls, and timeline.

We also shipped opt-out anonymous telemetry (Cloudflare Analytics Engine) to understand which parts of the product people actually use — no session content, no identifying data. It's disclosed in the README and can be disabled with `TT_NO_TELEMETRY=1`.

TokenTelemetry is open source, free, and runs entirely on your machine. If your team is using Claude Code, Codex, Cursor, GitHub Copilot, Grok Build, or Antigravity and you want cost visibility without sending your data anywhere, it's worth a look.

→ https://github.com/VasiHemanth/tokentelemetry
→ Install: `curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash`

---

*Drafted by scheduled task on 2026-06-21. Review before posting Friday morning.*
