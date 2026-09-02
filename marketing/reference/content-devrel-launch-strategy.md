# TokenTelemetry: Content, DevRel & Launch Calendar Strategy

> Prepared for Hemanth Vasi — June 2026  
> Based on research of Vercel, Anthropic, GitHub, Prisma, Tailwind CSS, OpenAI, and open source launch playbooks.

---

## Table of Contents

1. [12-Week Content Calendar](#1-12-week-content-calendar)
2. [Content Templates (Steal These)](#2-content-templates-steal-these)
3. [DevRel Strategy](#3-devrel-strategy)
4. [Video & Demo Strategy](#4-video--demo-strategy)
5. [Launch Day Checklist](#5-launch-day-checklist)
6. [Social Proof & Case Studies](#6-social-proof--case-studies)

---

## 1. 12-Week Content Calendar

### Strategy
Each week has **one anchor post** (blog / deep-dive) and **3-4 distribution pieces** (tweets, reddit posts, short-form video). Topics alternate between:
- **Viral / cost shock** (high shareability)
- **Technical deep-dive** (SEO + authority)
- **Comparison** (captures competitor search traffic)
- **Community / user story** (social proof)
- **Product update** (growth loop)

### Phase 1: Launch Blitz (Weeks 1-4)

| Week | Anchor Content | Distribution | SEO Target | Format |
|------|----------------|-------------|------------|--------|
| **1** | **"How Much Does Claude Code Actually Cost? I Tracked 100 Sessions"** — Real data from 100 Claude Code sessions. Average cost per task, hidden reasoning token waste, cost of "oops I forgot to set a budget." End with "here's how to track yours with TokenTelemetry." | Tweet storm (12 tweets), r/ClaudeCode, r/LocalLLaMA, Hacker News | "claude code cost", "claude code token usage", "claude code pricing" | Blog post + data viz |
| **2** | **"Claude Code vs Gemini CLI vs Codex: The $10,000 Token Showdown"** — Same 5 tasks across 3 agents. Measure tokens, cost, time, accuracy. Winner? "It depends." | Reddit r/MachineLearning, X thread with comparison table, YouTube short (60s) | "gemini cli vs claude code", "best ai coding agent 2026", "codex cli review" | Comparison post + embedded dashboard screenshots |
| **3** | **"I Monitored an AI Agent for 30 Days — Here's What It Did"** — Hermes Agent deep-dive. Run an autonomous agent for 30 days on Telegram + cron. Show the dashboard: gateway health, cost anomalies, skill usage heatmap. | X thread with Hermes dashboard GIF, r/selfhosted, Hermes Agent Discord, Nous Research community | "hermes agent observability", "autonomous agent monitoring", "hermes agent dashboard" | Technical case study + video walkthrough |
| **4** | **"Langfuse vs LangSmith vs Helicone vs TokenTelemetry: The Real Comparison"** — Head-to-head: setup time (5 min vs 2 hours), cost (free vs freemium), privacy (local vs cloud), supported agents. Killer table. | Tweet comparing setup times, r/programming, LinkedIn "hot take" post, cross-post to dev.to | "langfuse vs langsmith", "helicone alternative", "open source observability", "token telemetry vs langfuse" | Comparison page (SEO play) |

### Phase 2: Authority Building (Weeks 5-8)

| Week | Anchor Content | Distribution | SEO Target | Format |
|------|----------------|-------------|------------|--------|
| **5** | **"How to Track GitHub Copilot Token Usage (Without Paying for Enterprise)"** — Copilot doesn't expose per-session cost natively. TokenTelemetry does. Step-by-step guide with screenshots. | r/github, X (tag @github), Hacker News "Show HN" follow-up | "github copilot token usage", "github copilot cost tracking", "track copilot usage" | Tutorial blog post |
| **6** | **"Building a Multi-Agent Dashboard: The Architecture Behind TokenTelemetry"** — Technical deep-dive: how TT auto-detects agents, parses log formats, serves a local API. FastAPI + Next.js + zero-config philosophy. | HN "Ask HN: How do you monitor AI agent costs?", X thread on architecture, Dev.to | "ai agent observability architecture", "local llm monitoring", "fastapi nextjs dashboard" | Engineering blog post |
| **7** | **"I Let an AI Agent Run My Discord Server for a Month"** — Hermes Agent on Discord: moderation, Q&A, meme generation. What it cost, what broke, what surprised me. Dashboard screenshots. | r/Discord_bots, r/selfhosted, Nous Research community, X | "discord ai agent", "hermes agent discord bot", "autonomous discord moderation" | Community story + data post |
| **8** | **"The Hidden Cost of AI Coding Assistants: Why Your Team Needs Observability"** — Engineering manager POV. How AI spend grows silently, why per-developer budgets matter, how to justify tooling ROI. | LinkedIn (tag CTOs/EMs), r/programming, X thread for engineering leaders | "ai coding assistant cost", "engineering team ai spend", "developer tooling roi" | Thought leadership |

### Phase 3: Community & Growth (Weeks 9-12)

| Week | Anchor Content | Distribution | SEO Target | Format |
|------|----------------|-------------|------------|--------|
| **9** | **"How to Add a New Agent to TokenTelemetry (Tutorial + Contribution Guide)"** — Walk through adding support for a hypothetical new agent. Show how easy it is to contribute. | HN, r/opensource, GitHub Discussions, YouTube tutorial | "add new agent tokentelemetry", "contribute to open source observability" | Tutorial + contribution guide |
| **10** | **"Show HN: TokenTelemetry — Open source, local-only observability for every AI agent"** — The official HN relaunch with new features. | Hacker News, Product Hunt, X, Reddit | N/A (launch week) | Launch post |
| **11** | **"TokenTelemetry in Production: User Stories from the Community"** — 3 user stories collected over previous weeks. Real quotes, real dashboards, real savings. | X (user shoutouts), LinkedIn, newsletter | "token telemetry review", "ai agent observability tool" | Case study roundup |
| **12** | **"The State of AI Coding Agent Token Usage: 2026 Report"** — Aggregate trends from all opted-in users (anonymous). Average tokens per session, most expensive models, tool call frequency, session duration distributions. | HN, r/MachineLearning, X (tag Anthropic/OpenAI/Google), newsletter | "ai token usage trends 2026", "ai coding agent benchmark 2026", "llm cost trends" | Annual report / data journalism |

### Weekly Mini Content (Every Week)
- **Monday:** Screenshot/gif of a specific dashboard feature with a "did you know?" caption
- **Wednesday:** Quick tip (e.g., "You can rename projects in TT with `~/.tokentelemetry/aliases.json`")
- **Friday:** Open source spotlight — thank a contributor, highlight an issue, show a PR
- **Saturday:** "Agent of the week" — stats from one user's most-used agent (with permission)

---

## 2. Content Templates (Steal These)

### 2.1 Launch Day Blog Post Template

```
────────────────────────────────────────────────
  TITLE: Announcing TokenTelemetry: [VERSION/TAGLINE]
────────────────────────────────────────────────

  ┌─ SUBTITLE ─────────────────────────────────┐
  │                                            │
  │  [One sentence that captures the problem +  │
  │   the solution + why now.]                  │
  │                                            │
  │  Example: "Free, open-source, 100% local    │
  │  observability for every AI coding agent —  │
  │  one command, no signup, your data never    │
  │  leaves your machine."                      │
  │                                            │
  └────────────────────────────────────────────┘

  ┌─ [HOOK / OPENING] ────────────────────────┐
  │                                            │
  │  Start with a specific, relatable pain:    │
  │                                            │
  │  "Last week, I ran a Claude Code session    │
  │  that cost $12. I had no idea what it did, │
  │  what model it used, or how many tokens it  │
  │  burned through. I just got the bill."      │
  │                                            │
  │  (Keep this short. 2-3 sentences.)          │
  │                                            │
  └────────────────────────────────────────────┘

  ┌─ THE PROBLEM ──────────────────────────────┐
  │                                            │
  │  3 bullet points max. Make them sting:     │
  │                                            │
  │  • AI agents are expensive with zero        │
  │    visibility into costs                   │
  │  • Every agent stores logs differently,     │
  │    and none gives you a dashboard           │
  │  • Existing tools (Langfuse, Helicone)      │
  │    require SDKs, accounts, cloud — the      │
  │    opposite of zero-friction               │
  │                                            │
  └────────────────────────────────────────────┘

  ┌─ THE SOLUTION ─────────────────────────────┐
  │                                            │
  │  Introduce TokenTelemetry. 1 paragraph:     │
  │                                            │
  │  "TokenTelemetry changes this. It auto-     │
  │  detects every AI coding agent on your      │
  │  machine, reads their log files, and        │
  │  surfaces everything in a unified local     │
  │  dashboard. No SDK. No signup. No cloud."   │
  │                                            │
  └────────────────────────────────────────────┘

  ┌─ KEY FEATURES (with screenshots) ─────────┐
  │                                            │
  │  [Feature 1: Token Usage Dashboard]         │
  │  Real-time tokens in/out per agent, model,  │
  │  and project. Screenshot here.              │
  │                                            │
  │  [Feature 2: Session Traces with Waterfall] │
  │  Full prompt → reasoning → tools → response │
  │  Screenshot here.                           │
  │                                            │
  │  [Feature 3: Cost Tracking]                 │
  │  Exact $ per session, cumulative over time. │
  │  Screenshot here.                           │
  │                                            │
  │  [Feature 4: Multi-Agent Dashboard]         │
  │  Claude Code, Codex, Gemini, Cursor,        │
  │  Copilot, Hermes — one view. Screenshot.    │
  │                                            │
  │  [Feature 5: Hermes Agent Dashboard]        │
  │  Gateway health, skills, memory, cron,      │
  │  38 source platforms. Screenshot.           │
  │                                            │
  └────────────────────────────────────────────┘

  ┌─ QUICK START ─────────────────────────────┐
  │                                            │
  │  One code block. That's it.                │
  │                                            │
  │  curl -fsSL https://tokentelemetry.com/     │
  │    install.sh | bash                        │
  │                                            │
  │  Then open http://localhost:3000            │
  │                                            │
  └────────────────────────────────────────────┘

  ┌─ COMPARISON TABLE ─────────────────────────┐
  │                                            │
  │  Feature          ┊ TT ┊ Langf ┊ LangS ┊ HC │
  │  ─────────────────┼────┼───────┼───────┼──── │
  │  100% Local       ┊ ✅ ┊ ❌   ┊ ❌   ┊ ❌ │
  │  Zero Config      ┊ ✅ ┊ ❌   ┊ ❌   ┊ ❌ │
  │  No Signup        ┊ ✅ ┊ ❌   ┊ ❌   ┊ ❌ │
  │  10+ Agents       ┊ ✅ ┊ ❌   ┊ ❌   ┊ ❌ │
  │  Hermes Agent     ┊ ✅ ┊ ❌   ┊ ❌   ┊ ❌ │
  │  Open Source (MIT)┊ ✅ ┊ ✅  ┊ ❌   ┊ ❌ │
  │  Free Forever     ┊ ✅ ┊ $20/m ┊ $25/m ┊ $20/m │
  │                                            │
  └────────────────────────────────────────────┘

  ┌─ WHAT'S NEXT ─────────────────────────────┐
  │                                            │
  │  • Star on GitHub → [link]                 │
  │  • Join Discussions → [link]               │
  │  • Report a bug → [link]                   │
  │  • Add a new agent → [CONTRIBUTING.md]     │
  │                                            │
  │  Call to action: "Install it now. It takes  │
  │  30 seconds. Your data stays yours."       │
  │                                            │
  └────────────────────────────────────────────┘

────────────────────────────────────────────────
  META / SEO NOTES:
  • URL: /blog/announcing-tokentelemetry
  • OG Image: Dashboard screenshot with
    "TokenTelemetry" overlay
  • Tags: open source, observability, ai agents,
    local-first, developer tools
────────────────────────────────────────────────
```

### 2.2 Tweet Storm Template (10 Tweets)

```
🧵 1/10
I tracked every single token my AI coding agents burned through for 30 days.

The number was… terrifying.

$340 on Claude Code alone. For ONE developer.

Here's the breakdown. 👇

🧵 2/10
Most devs have NO idea what their agents cost.

Claude Code writes JSONL logs to ~/.claude/.
Gemini CLI logs to ~/.gemini/.
Codex logs to ~/.codex/.

Three different formats. Three different locations. Zero visibility.

🧵 3/10
I built a tool that reads ALL of them.

One dashboard. Every agent. Total cost, tokens, tool calls, reasoning traces.

No signup. No cloud. It's just a local web server.

It's called TokenTelemetry (and it's free + open source).

🧵 4/10
Here's what I learned in 30 days:

• Average Claude Code session: 47K tokens → ~$1.80
• Most expensive single session: $12.40 (reasoning mode ran away)
• Gemini CLI is 3x cheaper for the same task
• Codex burns through tool calls like they're free

🧵 5/10
The hidden cost nobody talks about: reasoning tokens.

Claude Code's extended thinking mode can add 40-60% to your bill BEFORE it writes a single line of code.

TokenTelemetry surfaces this automatically. Just open the dashboard.

🧵 6/10
Multi-agent setup?

TokenTelemetry shows Claude Code, Codex, Gemini, Cursor, Copilot, OpenCode, Qwen, Grok Build — all in one view.

Filter by agent, model, or project. See which one gives you the best ROI.

🧵 7/10
Oh, and Hermes Agent (Nous Research's autonomous agent framework)?

TokenTelemetry is the ONLY tool with a dedicated Hermes dashboard.

Telegram bots, Discord moderators, cron jobs — gateway health, skill usage, cost anomalies. All in one place.

🧵 8/10
The comparison against the "big players":

Langfuse: Requires SDK instrumentation, cloud account
LangSmith: Requires SDK, cloud account, paid
Helicone: Requires proxy setup, cloud

TokenTelemetry: curl → browser → done. Zero config. 100% local.

🧵 9/10
Install in 30 seconds:

curl -fsSL https://tokentelemetry.com/install.sh | bash

Then open http://localhost:3000

Your data never leaves your machine. MIT licensed. Free forever.

🧵 10/10
If you found this useful:

1. ⭐ Star the repo → github.com/VasiHemanth/tokentelemetry
2. 🐦 Follow @VasiHemanth for more AI dev tool breakdowns
3. 💬 Try it and tell me what you think

Your agents are spending money. It's time to know how much.

/done
```

### 2.3 Hacker News "Show HN" Post + First Comment Template

```
────────────────────────────────────────────────
  TITLE
────────────────────────────────────────────────
Show HN: TokenTelemetry – Open-source, 100% local
observability for every AI coding agent

────────────────────────────────────────────────
  SELF-POST (not a link post — write a narrative)
────────────────────────────────────────────────
We built TokenTelemetry because we had no idea
what our AI coding agents were costing us.

Claude Code, Codex, Gemini CLI, Cursor, Copilot —
each agent logs differently, and none gives you a
dashboard. You run a session, get a bill, and have
zero visibility into what happened.

TokenTelemetry auto-detects every agent on your
machine, reads their log files, and surfaces:
  • Real-time token & cost tracking per session
  • Waterfall traces (prompt → reasoning → tools →
    response)
  • Multi-agent dashboard (all agents, one view)
  • Per-project analytics & agent leaderboards
  • Dedicated Hermes Agent dashboard (gateway
    health, skills, memory, cron, 38 platforms)

100% local. No signup. No cloud. MIT licensed.

curl -fsSL https://tokentelemetry.com/install.sh | bash

I'd love your feedback — especially from folks
running multiple agents, or anyone using Hermes
Agent in production.

────────────────────────────────────────────────
  FIRST COMMENT (post immediately after submission)
────────────────────────────────────────────────
Hi HN! Builder here.

A bit more context on why I built this:

I run Claude Code, Gemini CLI, and Codex daily.
Every month I'd get my API bills and have no idea
which sessions cost what. I'd grep through JSONL
files to figure it out. It was absurd.

So I built a tool that just reads the logs my
agents already write. No proxy, no SDK, no
middleware. It's a FastAPI backend + Next.js
dashboard that runs entirely on localhost.

The biggest surprise during building: how different
every agent's log format is. Claude Code uses JSONL
with reasoning blocks, Gemini uses a custom session
format, Codex has its own schema. Normalizing all
of them was harder than expected — but now adding
a new agent takes ~2 hours of parser work.

The Hermes Agent dashboard was a happy accident.
Nous Research's framework has this incredibly rich
agent.log with per-API-call latency, cache hits,
subagent delegation — but no third-party tool had
ever built a UI for it. So we did.

What I'd love feedback on:
1. Any agents I'm missing that you want supported
2. Performance at scale (thousands of sessions)
3. Feature requests for the Hermes dashboard

Will be in the comments all day answering questions.
Cheers.

────────────────────────────────────────────────
  POSTING TIPS
────────────────────────────────────────────────
• Post Tuesday-Thursday, 9-11 AM ET
• Be in comments within 5 minutes of posting
• Reply to EVERY comment within 2 hours
• Don't link to Product Hunt in the post
• Link to GitHub README (not the website)
• Have 3-5 friends ready to comment with
  genuine questions/experiences
• Edit title if it doesn't gain traction in
  first 30 minutes
```

### 2.4 Product Hunt Listing Copy

```
────────────────────────────────────────────────
  PRODUCT HUNT LAUNCH
────────────────────────────────────────────────

Product Name: TokenTelemetry
Tagline: Free, open-source, 100% local observability
  for every AI coding agent
Website: https://tokentelemetry.com

Description (max 500 chars):
TokenTelemetry is a free, open-source observability
dashboard that tracks token usage, LLM costs, tool
calls, session traces, and reasoning steps across
ALL AI coding agents — Claude Code, Codex, Gemini
CLI, Cursor, Copilot, OpenCode, Qwen, Grok Build,
and Hermes Agent. One command, no signup, your data
never leaves your machine. Zero config: it auto-
detects agent logs and starts serving a dashboard
on localhost. MIT licensed, free forever.

First Comment (Maker's Comment):
"👋 Hey Product Hunt! I built TokenTelemetry because
I was tired of digging through JSONL log files to
figure out what my AI agents were costing me.

Key things that make this different:
1. 100% local — your logs never touch a server
2. Zero config — curl | bash, then open localhost
3. Multi-agent — Claude Code + Codex + Gemini +
   Cursor + Copilot + more, all in one dashboard
4. Hermes Agent dashboard — the only dedicated UI
   for Nous Research's autonomous agent framework

I'd love your feedback! What's the most expensive
AI agent session you've ever had?"

Hunter: Self-hunt or ask a well-known maker/hunter
  in the dev tools space (ideally someone who has
  launched open-source tools before)

Topics: Developer Tools, Open Source, AI,
  Analytics, Monitoring

Images:
  • Hero: Dashboard screenshot showing multi-agent
    view
  • Image 2: Session trace waterfall
  • Image 3: Hermes Agent dashboard
  • Image 4: Comparison table vs Langfuse/LangSmith
  • GIF: Install flow (copy command → browser opens
    → dashboard loads)

Launch Day Tactics:
  • Pre-notify 50 followers via DM the day before
  • Post on X with PH link at 12:01 AM PT
  • Share in Discord communities (DevHunt, OSS,
    AI tools)
  • Reply to every comment within 1 hour
  • Update README with "🏆 #1 on Product Hunt"
    badge if you win the day
```

### 2.5 Launch Email / Newsletter Template

```
────────────────────────────────────────────────
  SUBJECT: See exactly what your AI agents cost
────────────────────────────────────────────────

  ┌─ OPENING ─────────────────────────────────┐
  │                                            │
  │  Hey {name},                              │
  │                                            │
  │  Do you know how much your AI coding        │
  │  agents cost you last week?                │
  │                                            │
  │  I didn't either. That's why I built        │
  │  TokenTelemetry.                           │
  │                                            │
  └────────────────────────────────────────────┘

  ┌─ THE PROBLEM (with pain) ─────────────────┐
  │                                            │
  │  If you use Claude Code, Codex, Gemini CLI, │
  │  Cursor, or Copilot — you're spending more  │
  │  on tokens than you realize. But none of    │
  │  these agents shows you a dashboard.        │
  │                                            │
  │  Every agent logs differently. Every        │
  │  session is a black box.                    │
  │                                            │
  └────────────────────────────────────────────┘

  ┌─ THE SOLUTION ────────────────────────────┐
  │                                            │
  │  TokenTelemetry is a free, open-source      │
  │  dashboard that auto-detects every agent    │
  │  on your machine and shows you:             │
  │                                            │
  │  📊 Token usage & cost per session          │
  │  🔍 Full session traces (waterfall view)    │
  │  🛠️ Tool call analytics & success rates     │
  │  📁 Per-project insights & heatmaps         │
  │  🤖 Multi-agent dashboard (all in one)     │
  │                                            │
  │  100% local. No signup. No cloud.           │
  │                                            │
  └────────────────────────────────────────────┘

  ┌─ INSTALL ─────────────────────────────────┐
  │                                            │
  │  It takes 30 seconds:                      │
  │                                            │
  │  curl -fsSL https://tokentelemetry.com/    │
  │    install.sh | bash                       │
  │                                            │
  │  Then open http://localhost:3000           │
  │                                            │
  └────────────────────────────────────────────┘

  ┌─ BONUS: HERMES AGENT SUPPORT ─────────────┐
  │                                            │
  │  If you run Hermes Agent, TokenTelemetry   │
  │  is the ONLY tool with a dedicated          │
  │  dashboard for it.                         │
  │                                            │
  └────────────────────────────────────────────┘

  ┌─ CTA ────────────────────────────────────┐
  │                                            │
  │  ⭐ Star on GitHub                          │
  │  💬 Join the Discussion                     │
  │  🐦 Follow @VasiHemanth on X              │
  │                                            │
  │  — Hemanth                                 │
  └────────────────────────────────────────────┘

────────────────────────────────────────────────
  DISTRIBUTION CHANNELS:
  • Twitter/X (announcement thread)
  • LinkedIn (CTO/EM persona version)
  • Dev.to / Medium (cross-post)
  • Reddit (r/programming, r/selfhosted,
    r/MachineLearning, r/ClaudeCode)
  • Discord communities (AI Dev Tools, OSS,
    Nous Research)
  • Indie Hackers
────────────────────────────────────────────────
```

---

## 3. DevRel Strategy

### 3.1 Conference Talk Abstracts (That Would Get Accepted)

#### A. "Observability for AI Agents: Lessons from Building TokenTelemetry"

```
Conference Target: KubeCon NA / AI_Dev / O'Reilly AI Superstream
Format: 30-40 minute talk
Level: Intermediate

ABSTRACT:
Last year, I built an open-source observability tool
for AI coding agents. What I learned about how
Claude Code, Codex, and Gemini CLI actually work
under the hood — and how different they are — was
surprising.

In this talk, I'll share:
• The anatomy of an AI agent session: how prompts
  become reasoning → tool calls → responses
• Why every agent logs differently (Claude Code
  uses JSONL with reasoning blocks, Gemini uses
  a custom session format, Codex has its own
  schema) — and how we normalized them all
• The three types of observability every agent
  operator needs: token cost, tool call traces,
  and reasoning transparency
• The Hermes Agent pattern: why autonomous agents
  (Telegram bots, Discord moderators, cron jobs)
  need fundamentally different observability than
  coding agents
• Why 100% local observability matters for
  privacy, compliance, and latency

Attendees will leave knowing how AI coding agents
actually work internally, what observability
patterns apply to agentic systems, and how to
instrument their own agent workflows for
visibility.

KEY TAKEAWAYS:
- Understand the internal architecture of modern
  AI coding agents
- Learn the observability patterns that apply
  to agentic vs. non-agentic AI
- See a live demo of multi-agent observability
  across Claude Code, Codex, and Gemini CLI
- Walk away with a framework for building
  observability into any agent system
```

#### B. "The $10,000 Developer: What Happens When Every Engineer Has an AI Agent"

```
Conference Target: DeveloperWeek / CTO Summit / LeadDev
Format: 25-30 minute talk
Level: All levels

ABSTRACT:
In 2026, the average AI-literate developer spends
$200-500/month on agent tokens. A team of 10
engineers? $2,000-5,000/month — often invisible
because it's spread across personal accounts and
API keys.

I collected data from 100+ developers using AI
coding agents and found:
• 73% had no idea what their agents cost per
  session
• The most expensive agent pattern? Restarting
  the same task because the agent went down the
  wrong path (burning reasoning tokens on both
  attempts)
• Teams using 3+ agents simultaneously are
  spending 2.8x more than those using one —
  with no mechanism to compare efficiency

This talk presents the data, then offers a
practical framework for:
1. Tracking AI agent spend per developer
2. Comparing agent efficiency across tools
3. Building an observability culture for
   agentic workflows

No vendor pitch. Just data, patterns, and
actionable advice for engineering leaders.

KEY TAKEAWAYS:
- Real spending data from real developers using
  AI coding agents
- A framework for measuring AI agent ROI on your
  team
- How to build a culture of observability around
  agentic tools
```

#### C. "Hermes Agent in Production: Running Autonomous AI Agents at Scale"

```
Conference Target: AI Engineer Summit / AgentConf / Ray Summit
Format: 30-40 minute talk
Level: Advanced

ABSTRACT:
Nous Research's Hermes Agent runs across 38
source platforms — CLI, Telegram, Discord, Slack,
Feishu, cron, webhook — executing skills,
delegating to subagents, and maintaining persistent
memory. It's one of the most sophisticated open-
source agent frameworks available.

But running it at scale reveals hard problems:
• How do you monitor cost across 38 platforms?
• How do you detect when a subagent goes silent?
• How do you track skill usage and memory health?
• How do you handle cost anomalies (e.g., a cron
  job that suddenly burns 50K reasoning tokens)?

I built TokenTelemetry's Hermes Agent dashboard
to answer these questions. In this talk, I'll
share the architecture decisions, the log-parsing
challenges, and the patterns that emerged from
monitoring Hermes in production.

KEY TAKEAWAYS:
- Production monitoring patterns for autonomous
  agent frameworks
- How to detect and handle cost anomalies in
  agent systems
- Architecture for agent observability that
  scales across platforms
- Lessons from building the first dedicated
  Hermes Agent observability dashboard
```

### 3.2 Meetup / Webinar Workshop Plan

```
────────────────────────────────────────────────
  WORKSHOP: "AI Agent Observability 101"
────────────────────────────────────────────────
  Duration: 60-90 minutes
  Format: Live coding + demo
  Ideal for: Meetups (local dev groups, AI/ML
    meetups), online workshops, corporate lunch
    & learns

  AGENDA:

  0:00 - 0:05  Welcome & context
               • Why you should care about agent
                 observability
               • The "black box" problem

  0:05 - 0:15  The agent landscape in 2026
               • Claude Code, Codex, Gemini CLI,
                 Cursor, Copilot — what each logs
               • Demo: Grepping through JSONL files
                 (the painful way)

  0:15 - 0:30  Install & first look
               • Live install of TokenTelemetry
               • Open the dashboard
               • Walk through: agent detection,
                 session list, token charts

  0:30 - 0:45  Deep dive: session traces
               • Find an expensive session
               • Read the waterfall
               • Identify wasted tokens (over-long
                 reasoning, repeated tool calls)

  0:45 - 0:55  Hermes Agent observability
               • If anyone runs Hermes, show the
                 dedicated dashboard
               • Gateway health, skills, memory

  0:55 - 1:10  Hands-on: optimize an agent
               • Pick a session, identify waste
               • Discuss optimization strategies
               • Group share-out

  1:10 - 1:15  Q&A + resources

  MATERIALS:
  • Pre-loaded demo data (session logs from real
    agents — anonymized)
  • Install script ready
  • Workshop repo with sample outputs
  • Slides (10-12 slides max)

  OUTREACH PARTNERS:
  • Local AI/machine learning meetups
  • DevOps / SRE meetups (observability angle)
  • University CS clubs (research angle)
  • Corporate developer guilds
```

### 3.3 YouTube Tutorial Series Outline

```
────────────────────────────────────────────────
  SERIES: "The Agent Observatory"
  5 Episodes — 10-20 minutes each
────────────────────────────────────────────────

  EPISODE 1: "How Much Do Your AI Agents Cost?"
  • Duration: 12-15 min
  • Format: Screen recording + data overlay
  • Content:
    - Install TokenTelemetry live
    - Walk through the dashboard
    - Show real session costs
    - Reveal the most expensive patterns
  • CTA: "Install and share your top cost"
  • SEO: "how much do ai coding agents cost"

  EPISODE 2: "Reading Agent Traces Like a Pro"
  • Duration: 15-20 min
  • Format: Side-by-side code editor + dashboard
  • Content:
    - Open a session trace
    - Walk through prompt → reasoning → tools →
      response
    - Show how to spot wasted tokens
    - Compare a "good" vs "bad" session
  • CTA: "Find your most wasteful session"
  • SEO: "how to read ai agent traces"

  EPISODE 3: "Claude Code vs Gemini CLI vs Codex"
  • Duration: 18-20 min
  • Format: Split screen (3 terminals + dashboard)
  • Content:
    - Run the same task in all 3 agents
    - Compare tokens, cost, time, quality
    - Show the comparison in the dashboard
    - Give recommendations per use case
  • CTA: "Share which agent you use"
  • SEO: "claude code vs gemini cli vs codex"

  EPISODE 4: "Hermes Agent: The Autonomous Observability Tour"
  • Duration: 15-18 min
  • Format: Terminal + Hermes dashboard
  • Content:
    - What is Hermes Agent (quick explainer)
    - Show the /hermes dashboard
    - Gateway health, skill monitoring, cron jobs
    - Cost anomaly detection
  • CTA: "Try Hermes Agent + TokenTelemetry"
  • SEO: "hermes agent observability"

  EPISODE 5: "Building Your Own Agent Observability"
  • Duration: 18-20 min
  • Format: Code walkthrough (VS Code + dashboard)
  • Content:
    - How TokenTelemetry detects agents
    - How log parsing works
    - Add a new agent parser in real time
    - Architecture overview (FastAPI + Next.js)
  • CTA: "Contribute a new agent parser"
  • SEO: "build ai agent observability tool"

  PRODUCTION NOTES:
  • Record in 4K, export 1080p
  • Use OBS with clean transitions
  • Add captions (YouTube auto + manual review)
  • Thumbnail style: solid color background +
    bold text + dashboard screenshot
  • Post every 2 weeks (aligned with content
    calendar)
  • First 30 seconds must show the dashboard
    (hook before intro)
```

### 3.4 Twitch / Streaming Strategy

```
────────────────────────────────────────────────
  STREAMING STRATEGY: "Building in Public"
────────────────────────────────────────────────

  Platform: Twitch (primary) + YouTube simulcast
  Schedule: Weekly, Thursdays 4-6 PM PT
  Format: 2-hour build session

  STREAM TYPES (rotate):

  1. Agent Comparison Live
     • Open 3 terminals (Claude Code, Codex, Gemini)
     • Give each the same task
     • Watch them work — commentate on behavior
     • Reveal results + costs at the end
     • Chat votes on which agent "won"

  2. OSS Contribution Sessions
     • Work on open issues in TokenTelemetry
     • Read PRs, review code, merge
     • Onboard new contributors live
     • "First time contributor" pairing sessions

  3. "Ask the Dashboard" — Office Hours
     • Open the dashboard
     • Chat asks about their sessions
     • Help debug issues
     • Feature request discussions

  4. Guest Streams
     • Invite Hermes Agent users to share their setup
     • Invite other OSS maintainers
     • Invite AI agent power users to show their
       workflows

  PROMOTION:
  • Clip highlights → TikTok / YouTube Shorts / X
  • "This week on the stream" — posted Sunday on X
  • Post clips to r/LocalLLaMA, r/selfhosted
  • Build a !so command that shows latest GitHub
    stars

  METRICS TO WATCH:
  • Average concurrent viewers
  • New GitHub stars during stream
  • GitHub issues opened during stream
  • Discord joins during stream
```

---

## 4. Video & Demo Strategy

### 4.1 60-Second Demo Video Script

```
────────────────────────────────────────────────
  60-SECOND DEMO: "TokenTelemetry in 60 Seconds"
────────────────────────────────────────────────

  [0:00-0:08] HOOK
  VISUAL: Split screen — 3 terminal windows
    (Claude Code, Codex, Gemini) running
  VO: "Three AI agents. One hour. How much did
    they cost? You have no idea."

  [0:08-0:20] THE PROBLEM
  VISUAL: Close up of scrolling JSONL log file
    in terminal. Quick zoom out.
  VO: "Every agent logs differently. None shows
    you a dashboard. You're flying blind."

  [0:20-0:35] THE SOLUTION
  VISUAL: Terminal → `curl [install command]` →
    browser opens to dashboard
  VO: "TokenTelemetry installs in one command.
    Auto-detects every agent on your machine."

  [0:35-0:50] DASHBOARD WALKTHROUGH
  VISUAL: Quick pan across dashboard:
    • Agent cards (showing 4 agents detected)
    • Token usage graph (spiking)
    • Session trace waterfall (expanding)
    • Cost per project (bar chart)
  VO: "See tokens, costs, traces, and tool calls
    — all in real time. Claude Code, Codex, Gemini,
    Cursor, Copilot — one unified view."

  [0:50-0:58] CTA
  VISUAL: Heremes Agent dashboard flash,
    then back to install command on screen
  VO: "100% local. No signup. Open source.
    Try it free. Link in description."

  [0:58-1:00] OUTRO
  VISUAL: Logo + "TokenTelemetry" on dark bg
  VO: "Know what your agents cost."

────────────────────────────────────────────────
  PRODUCTION NOTES:
  • Fast cuts (2-3 seconds per shot)
  • Electronic background music (low intensity)
  • Subtitles throughout (spoken + visual text)
  • End card with GitHub star button + install cmd
  • Format: 9:16 (vertical) for TikTok/Reels/Shorts
  • Also export 16:9 for YouTube
────────────────────────────────────────────────
```

### 4.2 5-Minute Deep-Dive Video Script

```
────────────────────────────────────────────────
  5-MINUTE DEEP DIVE: "Full Tour of TokenTelemetry"
────────────────────────────────────────────────

  [0:00-0:30] HOOK
  VISUAL: Developer at desk. Decision time.
  VO: "You just finished a big refactor using
    Claude Code. It took 3 hours. It worked.
    But did it cost $2 or $20?"

  [0:30-1:00] INSTALL
  VISUAL: Screen recording — terminal
  VO: "Let me show you how to find out."

  SCREEN: curl install command → browser → dashboard
  VO: "This is the dashboard. It detected three
    agents automatically: Claude Code, Gemini CLI,
    and Codex. No configuration."

  [1:00-2:30] DASHBOARD TOUR
  VISUAL: Dashboard pans
  VO (walking through each):
  "Top: agent cards — green means active. Click
   any agent to see its sessions.

  Bottom: recent sessions — timestamps, duration,
   tokens, cost.

  Right: model distribution — pie chart of which
   models you're using.

  The burn rate graph — shows spend per hour."

  [2:30-3:30] SESSION TRACE DEEP DIVE
  VISUAL: Click a session → waterfall opens
  VO: "This is where it gets interesting. Every
    session is a waterfall:

  System prompt → user input → reasoning chain →
  tool calls → responses.

  See that long reasoning block? 18 seconds of
  thinking. That's $0.40 in Claude Opus 4.7
  reasoning tokens.

  And here — three failed tool calls before the
  successful one. Each failure cost money."

  [3:30-4:15] MULTI-AGENT COMPARISON
  VISUAL: Switch to Analytics view
  VO: "The real power: compare across agents.
   Claude Code cost $42 this week. Gemini CLI was
   $18 for similar work. Codex was $31.

   Per-project view: the API project consumed 60%
   of all tokens."

  [4:15-4:45] HERMES AGENT
  VISUAL: Click into /hermes dashboard
  VO: "If you use Hermes Agent, there's a dedicated
    dashboard. Gateway health, skill usage, cron
    jobs, cost anomalies. No other tool has this."

  [4:45-5:00] WRAP
  VISUAL: Back to install command
  VO: "Free. Open source. Your data never leaves
    your machine. Try it today — link below."

────────────────────────────────────────────────
  PRODUCTION NOTES:
  • Smooth zooms and pans (no jump cuts on
    dashboard)
  • Cursor movements should be slow and deliberate
  • Voiceover: calm, authoritative, measured pace
  • Background: terminal color scheme aesthetic
  • End card with GitHub QR code
  • Format: 16:9 YouTube
────────────────────────────────────────────────
```

### 4.3 Screenshot Tour for Website/README

```
────────────────────────────────────────────────
  SCREENSHOT TOUR (6 Images)
────────────────────────────────────────────────

  IMAGE 1: DASHBOARD OVERVIEW
  Caption: "Your command center. See all agents,
    recent sessions, model distribution, and
    token burn rate at a glance."
  Size: 1920x1080, full-width dashboard
  Focus: Agent cards row + session list + charts
  Highlight: Green "active" indicators on agents

  IMAGE 2: SESSION TRACE WATERFALL
  Caption: "Every prompt, reasoning chain, tool
    call, and response — in a single waterfall
    view. See exactly what your agent was doing."
  Size: 1200x800 (portrait-oriented)
  Focus: Expand one session to show reasoning
    block + 3 tool calls + final response
  Highlight: Time/cost per step

  IMAGE 3: MULTI-AGENT ANALYTICS
  Caption: "Compare token efficiency and cost
    across agents, models, and projects."
  Size: 1920x1080
  Focus: Bar chart comparing Claude Code vs Gemini
    vs Codex cost and tokens
  Highlight: The "most efficient" agent badge

  IMAGE 4: PROJECT HEATMAP
  Caption: "Per-project insights with activity
    heatmaps, agent leaderboards, and session
    timelines."
  Size: 1200x800
  Focus: Calendar heatmap + agent usage pie chart
  Highlight: Most active day/time

  IMAGE 5: HERMES AGENT DASHBOARD
  Caption: "The only dedicated dashboard for
    Nous Research's Hermes Agent. Gateway health,
    skills, memory, cron, and cost anomalies."
  Size: 1920x1080
  Focus: Agent overview + platform breakdown
    (38 sources) + recent tasks
  Highlight: "Dedicated dashboard" badge

  IMAGE 6: COMPARISON TABLE
  Caption: "TokenTelemetry vs the alternatives."
  Size: Full-width infographic
  Content: Feature comparison table (same as
    README comparison)

  STYLE GUIDE:
  • Dark background (#0d1117, GitHub dark)
  • Accent color: #58a6ff (blue) or #3fb950 (green)
  • Terminal font (JetBrains Mono)
  • Clean, minimal macOS window chrome (dark mode)
  • No UI distractions — crop tightly around content
  • Add subtle gradient overlay for hero images
  • Use 2x resolution (retina-ready)
```

### 4.4 GIF Walkthrough for Social Media

```
────────────────────────────────────────────────
  SOCIAL MEDIA GIFS (5 GIFs)
────────────────────────────────────────────────

  GIF 1: "Install → Dashboard" (15 seconds)
  Scene: Terminal install → browser auto-opens →
    dashboard loads
  Text overlay: "One command. Zero setup."
  Best for: X, LinkedIn, website hero

  GIF 2: "Session Trace Explore" (20 seconds)
  Scene: Click a session → waterfall expands →
    scroll through reasoning → expand tool calls
  Text overlay: "See every step your agent takes"
  Best for: X, Reddit

  GIF 3: "Multi-Agent Filter" (12 seconds)
  Scene: Filter dropdown → select Claude Code →
    dashboard filters to CC → select Gemini → filters
  Text overlay: "Compare agents instantly"
  Best for: X, LinkedIn

  GIF 4: "Cost Graph Zoom" (10 seconds)
  Scene: Hover over cost graph → tooltip shows
    exact $ per day → zoom into a week
  Text overlay: "Know exactly what you spend"
  Best for: X, Reddit

  GIF 5: "Hermes Dashboard Flash" (15 seconds)
  Scene: Open /hermes → shows platform breakdown →
    skills list → cron health → cost anomaly alert
  Text overlay: "Autonomous agent observability"
  Best for: X, Nous Research Discord

  TECHNICAL SPECS:
  • Resolution: 800x600 (Twitter/X), 1080p for
    website
  • Frame rate: 15-20 fps
  • Duration: 10-20 seconds each
  • Format: MP4 (auto-play, no audio)
  • File size: < 5MB per GIF-in-MP4
  • Tool: CleanShot X or ScreenFlow
  • Mouse clicks: Visualized with ripple effect
  • No cursor trails — use clean, fast movements
```

---

## 5. Launch Day Checklist

### 5.1 Pre-Launch Checklist (T-1 Week)

```
WEEK BEFORE
────────────────────────────────────────────────
  □ PRODUCT
    □ Final release candidate deployed
    □ Install scripts tested on macOS, Linux, Windows
    □ `curl | bash` path tested from clean machine
    □ Dashboard smoke-tested with real agent logs
    □ Known bugs documented + workarounds written
    □ Performance tested with 500+ sessions
    □ Privacy/security: confirm no data leaks
      (check all outbound calls)
    □ Update check configurable and documented
    □ README updated with latest screenshots, badges,
      comparison table

  □ WEBSITE
    □ Landing page copy finalized (hero, features,
      agents, FAQ)
    □ Blog post drafted, reviewed, scheduled
    ↑ DO NOT PUBLISH until launch day
    □ Comparison page live (vs Langfuse/Smith/Helicone)
    □ SEO: meta titles, descriptions, OG images set
    □ `/install` route redirects to correct install
    □ `/docs` has Getting Started guide
    □ GitHub star button in header

  □ ASSETS
    □ Product Hunt listing drafted (images, copy)
    □ Hacker News post + first comment drafted
    □ Tweet storm drafted and queued
    □ YouTube demo video rendered and uploaded
      (unlisted, publish on launch)
    □ Screenshots taken (see Section 4.3)
    □ GIFs created (see Section 4.4)
    □ Logo in all sizes (favicon, OG, social card)
    □ "Built with TokenTelemetry" badge designed

  □ COMMUNITY
    □ Discord server set up with channels:
      #general, #show-and-tell, #support,
      #contributing, #hermes-agent
    □ GitHub Discussions enabled
    □ Twitter/X profile optimized with link
    □ LinkedIn profile updated

  □ OUTREACH
    □ List of 20 influencers to DM on launch day
    □ List of 10 newsletters to submit to
    □ Product Hunt "hunter" confirmed
    □ Reddit posting accounts verified (no brand new
      accounts — use established ones)
    □ Cross-posting accounts on Dev.to, Medium ready
    □ 5-10 friends confirmed to comment on HN
      within first 10 minutes
    □ 20-30 followers confirmed to upvote on PH in
      first hour (ask, don't spam)
```

### 5.2 Pre-Launch Checklist (T-3 Days)

```
3 DAYS BEFORE
────────────────────────────────────────────────
  □ Final testing pass on all install paths
  □ Update version numbers everywhere
    (package.json, Cargo.toml if Rust, etc.)
  □ Screenshot tour updated if UI changed
  □ Blog post final review + proofread
  □ Product Hunt listing submitted for scheduling
    (or prepared for same-day manual post)
  □ Email draft finalized in Mailchimp/Buttondown
  □ Social media graphics in final format
  □ Check GitHub Actions / CI is green
  □ Test the entire "new user" flow on a clean VM:
    1. Open terminal
    2. Run install command
    3. Open browser
    4. See dashboard with data
    (use the simulation script if no real agents)
  □ Reply to any pending GitHub issues
  □ Merge any low-risk PRs that improve launch
    experience
```

### 5.3 Pre-Launch Checklist (T-1 Day)

```
1 DAY BEFORE
────────────────────────────────────────────────
  MORNING:
  □ Send pre-launch DMs to 10-15 people
    ("Hey, launching TokenTelemetry tomorrow at 9
     AM ET. Would mean a lot if you could check it
     out and share feedback.")
  □ Post a mysterious teaser on X:
    "Tomorrow. 9 AM ET. Something for everyone who
     uses AI coding agents and has no idea what
     they cost."
  □ Final read-through of all launch copy

  AFTERNOON:
  □ Product Hunt: upload all images, fill in all
    fields, SAVE AS DRAFT
  □ Hacker News: have the post drafted in a text
    file (DON'T POST YET)
  □ Tweet queue ready in Typefully/Buffer
  □ YouTube video set to UNLISTED (publish at
    launch time)
  □ Email list: send a "tomorrow" teaser to your
    warm list (optional — depends on list size)

  EVENING:
  □ Go to bed early. Seriously.
  □ Set 3 alarms (7:30 AM, 7:45 AM, 8:00 AM)
  □ Have coffee ready
  □ Charge laptop
  □ Close all unnecessary apps
  □ Have water + snacks on desk
```

### 5.4 Launch Day Hour-by-Hour

```
LAUNCH DAY — HOUR BY HOUR
All times Eastern.
────────────────────────────────────────────────

  7:30 AM — PREP
  □ Wake up, coffee, shower
  □ Check that the server is up, dashboard loads
  □ Start monitoring: GitHub star count, website
    traffic, install script hits
  □ Open all tabs: HN, PH, X, Reddit, Discord,
    GitHub, Google Analytics (if used)

  8:00 AM — WARM UP
  □ Post on X: "Launching TokenTelemetry in 1 hour.
    Free, open-source, local-only observability for
    every AI agent. One command. Your data stays
    yours."
  □ DM 20 influencers/friends: "Launching in 1 hour
    on HN. Would appreciate a share if you like it."
  □ Open the Product Hunt listing in a tab (ready
    to hit publish)

  9:00 AM — LAUNCH
  □ PUBLISH Product Hunt
  □ PUBLISH Hacker News "Show HN"
  □ Post HN first comment immediately
  □ PUBLISH blog post on website
  □ PUBLISH video on YouTube (set to public)
  □ PUBLISH tweet storm (10 tweets)
  □ SET PH link as pinned tweet
  □ UPDATE LinkedIn: "I built something. It's free.
    It's open source. Link in comments."
  □ SEND email to newsletter list

  9:00 AM - 10:00 AM — FIRST HOUR (critical)
  □ Reply to every HN comment within 5-10 minutes
  □ Reply to every PH comment
  □ Monitor GitHub stars — if not moving, share
    directly with 10 people
  □ Share PH link in Discord communities
  □ Post to Reddit: r/programming, r/selfhosted,
    r/MachineLearning, r/ClaudeCode
  □ Share in Indie Hackers

  10:00 AM - 12:00 PM — ACCELERATION
  □ Post update on X: "1 hour in, X stars on GitHub.
    Install it: [link]"
  □ Check HN front page ranking
  □ If on front page: stay in comments, reply to
    every new comment
  □ If NOT on front page: consider changing title
    (if within edit window)
  □ Cross-post blog to Dev.to, Medium
  □ Share PH link in more niche communities
    (r/opensource, specific agent subreddits)

  12:00 PM - 3:00 PM — AFTERNOON WAVE
  □ Post progress update on X (stars, top comments)
  □ Send personalized DMs to 10 more people
  □ Engage with anyone who tweets about
    TokenTelemetry — reply, retweet, thank
  □ Check analytics: where is traffic coming from?
  □ If on front page of HN: keep engaging
  □ Start collecting testimonials from early users

  3:00 PM - 6:00 PM — EUROPE WINDOW
  □ European developers are active — share again
    on X with EU-friendly time
  □ Post to Reddit again (different subreddits,
    different angle)
  □ Follow up with people who said they'd try it

  6:00 PM - 9:00 PM — WRAP UP
  □ Final HN check (reply to any unanswered
    comments)
  □ Post on X: "Day 1 recap: [X] GitHub stars,
    [Y] installs, #1 on Product Hunt [if true],
    front page of HN"
  □ Thank contributors, upvoters, commenters
  □ Update README with Product Hunt badge
    (if #1 or top 5)
  □ Log all metrics

  9:00 PM+ — REST
  □ Sign off. The algorithm will keep working.
  □ Tomorrow: respond to overnight comments.
```

### 5.5 Post-Launch Checklist

```
48 HOURS AFTER
────────────────────────────────────────────────
  □ Reply to all remaining HN/PH/Reddit comments
  □ Blog post: add link to HN discussion
  □ Write a "launch retrospective" thread on X
  □ Email newsletter #2: "How launch day went +
  what's next"
  □ Thank all early contributors publicly
  □ Fix any critical bugs reported during launch
  □ Convert the most engaged users into Discord
    moderators / community members
  □ Update GitHub issue templates based on launch
    feedback

1 WEEK AFTER
────────────────────────────────────────────────
  □ Publish "Week 1" content from content calendar
  □ Reach out to 5 users for case study interviews
  □ Fix non-critical bugs reported during launch
  □ Ship first post-launch feature request
  □ Post on X: "One week in — [X] stars, [Y]
    installs, top feedback was [Z]. Fixed it."
  □ Apply to awesome-* lists:
    • awesome-selfhosted
    • awesome-llm-apps
    • awesome-developer-tools
    • awesome-observability
  □ Submit to newsletters: TLDR, Bytes, DevURLs,
    Python Weekly, JavaScript Weekly
  □ Evaluate what worked and what didn't for
    distribution

1 MONTH AFTER
────────────────────────────────────────────────
  □ Publish the "one month" case study / user story
  □ Ship feature #2 from post-launch roadmap
  □ Host first community call / streaming session
  □ Conference CFP submissions (if abstracts are
    ready)
  □ Review growth metrics vs. targets
  □ Plan "v2" content push based on user feedback
  □ Consider second Product Hunt launch with
    significant new feature
  □ Update llms.txt for AI assistant discoverability
```

### 5.6 Metrics to Track

```
METRIC                TRACKING METHOD          TARGET
────────────────────────────────────────────────────────
  GitHub Stars         GitHub API              500 in 48h
                        (daily check)           2K in 30d

  Install Script       Server logs /           1K in 48h
  Downloads             GitHub release           5K in 30d
                         download count

  Docker Pulls         Docker Hub              500 in 7d
                         (if published)

  npm Install          npm download count      1K in 30d
                         (if published)

  Website Visitors     Plausible / Fathom      10K in 48h
                         (privacy-first)        50K in 30d

  Hacker News          HN front page?          Top 10 for
  Ranking               Upvote count            4+ hours

  Product Hunt         Daily rank              #1
  Ranking                                        Top 3

  Reddit Upvotes       Upvote count per post   200+ per post

  Twitter/X            Impressions,            50K in 48h
  Engagement            retweets, replies

  Newsletter           Open rate               > 50%
  Signups               Signup count           500 in 7d

  Discord              Member count            200 in 7d
  Community             Daily active users

  GitHub Forks         GitHub API              Fork rate > 5%
                         (forks/stars)

  Contributors         GitHub API               10 new
                         (new contributors)      in 30d

  Unique Sessions      Dashboard heatbeat      1K in 7d
  (users running TT)    (update check)

  Revenue              Zero (free project)     N/A for now
                         but track conversion
                         if future paid tier

  KEY DERIVED METRICS:
  • Install-to-star conversion rate (target: >25%)
  • Visitor-to-install conversion rate (target: >5%)
  • Star-to-contributor conversion (target: >2%)
  • Referrer breakdown (where is traffic coming
    from?)

  REPORTING CADENCE:
  • Daily: first 7 days
  • Weekly: weeks 2-4
  • Monthly: weeks 5+
```

---

## 6. Social Proof & Case Studies

### 6.1 Template for Collecting User Testimonials

```
────────────────────────────────────────────────
  USER TESTIMONIAL REQUEST TEMPLATE
────────────────────────────────────────────────

  [Send via DM, email, or GitHub Discussion]

  ┌─ SUBJECT ──────────────────────────────────┐
  │ Hi {name}! Love hearing how you're using     │
  │ TokenTelemetry — mind sharing a quick quote? │
  └─────────────────────────────────────────────┘

  BODY:
  Hey {name},

  I saw you've been using TokenTelemetry —
  really appreciate it!

  I'm collecting stories from early users for
  the website and README. Would you mind
  answering 3 quick questions?

  1. What were you doing before TokenTelemetry
     to track your AI agent costs/usage?

  2. What's the most surprising thing you've
     learned from the dashboard?

  3. Could I quote you on the README/website?
     (If yes: do you have a preferred title,
     company, and social link?)

  Totally fine if you'd rather not be quoted.
  Even anonymous feedback helps me make the
  tool better.

  Thanks!
  Hemanth

  ──────────────────────────────────────────────
  ALTERNATIVE: IN-APP PROMPT
  ──────────────────────────────────────────────

  After a user has had 5+ sessions logged,
  show a bottom-right toast:

  "🔍 Loving TokenTelemetry? Mind leaving a
   quick testimonial? Takes 30 seconds."
  [Share Feedback →] [Dismiss]

  ──────────────────────────────────────────────
  TESTIMONIAL DISPLAY FORMAT
  ──────────────────────────────────────────────

  "{short, specific quote about a concrete
   benefit}"

  — {Name}, {Title} @ {Company}

  Example:
  "I was spending $200/month on Claude Code with
  zero visibility. TokenTelemetry showed me that
  60% of my tokens were going to failed tool call
  retries. Fixed my prompts, cut cost by 40%."

  — Sarah Chen, Senior Engineer @ FintechCo
```

### 6.2 How to Create "Before/After" ROI Case Studies

```
────────────────────────────────────────────────
  CASE STUDY TEMPLATE: "Before & After"
────────────────────────────────────────────────

  FORMAT: 800-1200 words, 3-5 screenshots
  PUBLISH: Blog post + README mention + X thread

  STRUCTURE:

  TITLE: "How {Company/Role} Saved {X}% on AI
    Agent Costs with TokenTelemetry"

  SUBTITLE: {One-sentence summary of the result}

  ┌─ BEFORE ──────────────────────────────────┐
  │                                            │
  │  The problem (with numbers):               │
  │                                            │
  │  • "I was spending roughly $500/month on    │
  │    AI coding agents across Claude Code and  │
  │    Codex."                                  │
  │  • "I had no breakdown of which sessions    │
  │    cost what."                              │
  │  • "I assumed my agents were efficient."    │
  │                                            │
  │  Context: who they are, what tools they     │
  │  use, how many developers on the team.      │
  │                                            │
  └────────────────────────────────────────────┘

  ┌─ THE SMOKING GUN ─────────────────────────┐
  │                                            │
  │  What did the dashboard reveal?            │
  │                                            │
  │  • "Session trace showed 8 failed tool      │
  │    calls in a row — $2.40 in wasted tokens" │
  │  • "Reasoning mode was enabled for 47% of   │
  │    total token spend"                       │
  │  • "One model was 3x more expensive than     │
  │    another for the same quality output"     │
  │                                            │
  │  Include a dashboard screenshot highlighting │
  │  the discovered waste.                      │
  │                                            │
  └────────────────────────────────────────────┘

  ┌─ THE CHANGE ──────────────────────────────┐
  │                                            │
  │  What did they do differently?             │
  │                                            │
  │  • Switched default model                   │
  │  • Set reasoning token budgets              │
  │  • Improved prompts to reduce retries       │
  │  • Standardized on more efficient agent     │
  │    per task type                            │
  │                                            │
  └────────────────────────────────────────────┘

  ┌─ AFTER (RESULTS) ─────────────────────────┐
  │                                            │
  │  Quantified impact:                        │
  │                                            │
  │  • "Cost dropped from $500/mo to $280/mo —  │
  │    44% reduction"                           │
  │  • "Failed tool call rate dropped from      │
  │    23% to 8%"                               │
  │  • "We now have per-developer budgets for    │
  │    agent usage"                             │
  │                                            │
  │  Include "After" dashboard screenshot       │
  │  showing improvement.                       │
  │                                            │
  └────────────────────────────────────────────┘

  ┌─ KEY TAKEAWAYS ───────────────────────────┐
  │                                            │
  │  Bullet-point lessons for the reader:      │
  │  • You can't optimize what you can't see    │
  │  • Reasoning tokens are the hidden cost     │
  │  • Multi-agent comparison drives savings    │
  │  • Observability changes behavior           │
  │                                            │
  └────────────────────────────────────────────┘

  ┌─ CTA ─────────────────────────────────────┐
  │                                            │
  │  "Want to find savings in your own AI       │
  │  agent usage? Install TokenTelemetry —      │
  │  free, 30 seconds, your data stays local."  │
  │                                            │
  └────────────────────────────────────────────┘

  ──────────────────────────────────────────────
  OUTREACH FOR CASE STUDIES:
  • Find users with 50+ sessions in their TT
    dashboard
  • Ask: "I noticed you've been using TT heavily.
    Would you share your experience?"
  • Offer: featured on README + blog + social
    shoutout
  • Target: 3 case studies in first 60 days
```

### 6.3 "Built With" Badge Design Brief

```
────────────────────────────────────────────────
  "BUILT WITH TOKENTELEMETRY" BADGE
────────────────────────────────────────────────

  PURPOSE: Viral loop. Users who add this badge
  to their own READMEs/projects drive awareness.

  BADGE VARIANTS:

  Variant 1: Shield.io Style (README/website)
  ┌────────────────────────────────────┐
  │ [monitored by] [TokenTelemetry ✓]  │
  └────────────────────────────────────┘
  Colors: Dark bg (#0d1117), white text,
    green checkmark
  Link: https://tokentelemetry.com

  Variant 2: Minimal Footer Badge
  ┌────────────────────────────────────┐
  │ ⚡ TokenTelemetry — Know what your  │
  │   agents cost                       │
  └────────────────────────────────────┘
  Colors: Dark bg, green accent text
  Link: https://tokentelemetry.com

  Variant 3: Rich Card (for blog footers)
  ┌────────────────────────────────────┐
  │ ┌──────────────────────────────┐   │
  │ │        TokenTelemetry        │   │
  │ │  Open-source observability   │   │
  │ │  for AI coding agents        │   │
  │ │  ⭐ 100% local · no signup   │   │
  │ │  [GitHub] [Website] [Install]│   │
  │ └──────────────────────────────┘   │
  └────────────────────────────────────┘

  TECHNICAL:
  • Host badge images in the GitHub repo
    (badges/ directory)
  • Support both SVG and Markdown embed
  • Add a badge embed code block in README:
    [![Monitored by TokenTelemetry]
    (https://tokentelemetry.com/badge.svg)]
  • Track badge click-throughs via
    tokentelemetry.com (optional, privacy-
    respecting)

  PLACEMENT INCENTIVES:
  • "Add the badge → your project listed in
    the TokenTelemetry README showcase"
  • "Top 10 badge projects get featured on
    the website"
  • "First 100 badge users get a shoutout
    on X"
```

### 6.4 Influencer/Creator Outreach List

```
────────────────────────────────────────────────
  OUTREACH TARGETS (X/Twitter)
────────────────────────────────────────────────

  These are people to DM on launch day and
  tag in relevant posts weeks before.

  ┌─ CATEGORY 1: AI CODING TOOL POWER USERS ──┐
  │                                            │
  │  Who: Developers who tweet about Claude     │
  │    Code, Codex, Gemini CLI, AI coding.     │
  │  Why: They're the direct target audience.   │
  │  On X: Search for tweets with:              │
  │    "claude code" "codex cli" "gemini cli"   │
  │    "ai coding agent" "token usage"          │
  │  Angle: "Your tool of choice finally has    │
  │    observability. Want early access?"       │
  │                                            │
  │  Examples (find via search, follow these    │
  │  for relevance):                            │
  │  • @levelsio (indie dev, uses many tools)   │
  │  • @swyx (developer experience thought       │
  │    leader)                                  │
  │  • @danielalbu (Claude Code / coding agents)│
  │  • @nicknisi (VS Code / Copilot power user) │
  │  • @rauchg (Vercel CEO — aspirational,      │
  │    unlikely to reply but worth tagging on   │
  │    technical posts)                         │
  │                                            │
  └────────────────────────────────────────────┘

  ┌─ CATEGORY 2: OPEN SOURCE COMMUNITY ───────┐
  │                                            │
  │  Who: Maintainers of popular open source    │
  │    developer tools.                         │
  │  Why: They understand the OSS distribution  │
  │    model and may recommend TT.              │
  │  Angle: "It's MIT. No cloud. No signup.     │
  │    It's built the way we build."            │
  │                                            │
  │  Examples:                                  │
  │  • @thesephist (OSS builder, maintains      │
  │    many tools)                              │
  │  • @zenorocha (OSS veteran, dev tool        │
  │    builder)                                 │
  │  • @mattetti (open source community leader) │
  │  • @mitsuhiko (creator of Flask, Sentry)    │
  │                                            │
  └────────────────────────────────────────────┘

  ┌─ CATEGORY 3: DEV TOOL CONTENT CREATORS ──┐
  │                                            │
  │  Who: YouTubers and streamers who cover     │
  │    developer tools and AI.                  │
  │  Why: Video reviews drive installs.         │
  │  Angle: "I built a tool that tracks all AI  │
  │    agent spend locally. Want early access   │
  │    for a review?"                           │
  │                                            │
  │  Examples:                                  │
  │  • @fireship_dev (edgy, fast tutorials)     │
  │  • @ThePrimeagen (Vim/AI coding content)    │
  │  • @t3dotgg (Theo — dev tool reviews)       │
  │  • @cassidoo (developer newsletter + X)     │
  │  • @benawad (coding tutorials)              │
  │  • @jackherrington (dev tool deep dives)    │
  │                                            │
  └────────────────────────────────────────────┘

  ┌─ CATEGORY 4: NOUS RESEARCH / HERMES ──────┐
  │                                            │
  │  Who: Community around Hermes and Nous.     │
  │  Why: TT is the only Hermes dashboard.      │
  │  Angle: "Built a dedicated Hermes Agent     │
  │    dashboard — the only third-party tool    │
  │    that treats Hermes as a first-class      │
  │    observability target."                   │
  │                                            │
  │  Examples:                                  │
  │  • Nous Research team accounts              │
  │  • Hermes Agent GitHub maintainers          │
  │  • Telegram/Discord bot operators who       │
  │    tweet about their setups                 │
  │  • @Teknium1 (Nous Research founder)        │
  │                                            │
  └────────────────────────────────────────────┘

  ┌─ CATEGORY 5: CTOs / ENGINEERING LEADERS ──┐
  │                                            │
  │  Who: CTOs who tweet about engineering      │
  │    management, AI adoption, developer       │
  │    productivity.                            │
  │  Why: They control team tooling budgets.    │
  │  Angle: "I built a free tool that shows     │
  │    exactly what your team's AI agents       │
  │    cost. No signup, no cloud."              │
  │                                            │
  │  Examples:                                  │
  │  • @shreyas (product/engineering leader)    │
  │  • @gokulrajaram (CTO, engineering culture)│
  │  • @danveloper (engineering leadership)     │
  │  • @patio11 (software business + economics) │
  │                                            │
  └────────────────────────────────────────────┘

  ┌─ OUTREACH DM TEMPLATE ──────────────────────┐
  │  Hi {name},                                 │
  │                                              │
  │  I'm a huge fan of your work on {specific    │
  │  thing}. I built a free, open-source tool    │
  │  called TokenTelemetry that I think you'd    │
  │  find useful — it's a 100% local dashboard   │
  │  that tracks token usage and costs across    │
  │  ALL AI coding agents (Claude Code, Codex,   │
  │  Gemini CLI, etc.).                          │
  │                                              │
  │  No signup, no cloud — just `curl | bash`    │
  │  and you get a full dashboard.               │
  │                                              │
  │  Would love your thoughts if you try it!     │
  │  https://tokentelemetry.com                  │
  │                                              │
  │  — Hemanth                                   │
  └────────────────────────────────────────────┘

  ┌─ OUTREACH TIMING ──────────────────────────┐
  │  DON'T DM on launch day (too noisy).        │
  │  DM 1 week before: "Here's early access."    │
  │  DM on launch day: "Just launched! You had   │
  │    early access — would appreciate a share   │
  │    if you liked it."                         │
  │  Follow up 1 week after: "Did you get a      │
  │    chance to try it?"                        │
  └────────────────────────────────────────────┘
```

---

## Appendix: SEO Keyword Strategy

```
────────────────────────────────────────────────
  KEYWORD TIERS
────────────────────────────────────────────────

  TIER 1 (HIGH VOLUME, COMPETITIVE):
  Target with comparison pages + README SEO
  • "claude code token usage"
  • "ai agent observability"
  • "llm cost tracking"
  • "langfuse alternative"
  • "local llm monitoring"
  • "open source observability"

  TIER 2 (MEDIUM VOLUME, MODERATE):
  Target with tutorials + blog posts
  • "how to track gemini cli costs"
  • "codex token monitor"
  • "claude code session viewer"
  • "github copilot usage tracker"
  • "hermes agent dashboard"
  • "multi agent dashboard"

  TIER 3 (LOW VOLUME, EASY WIN):
  Target with targeted pages + README
  • "cursor ide analytics"
  • "antigravity agent tokens"
  • "qwen cli token usage"
  • "grok build cost tracking"
  • "open code agent telemetry"
  • "vibe coding agent analytics"

  ON-PAGE SEO QUICK WINS:
  • Title tag: "TokenTelemetry - Local observability
    for AI coding agents" (55-60 chars)
  • Meta description: "Free, open-source, 100% local
    dashboard to track token usage, LLM costs, and
    session traces across Claude Code, Codex, Gemini
    CLI, Cursor, Copilot, and more."
  • H1: "See exactly what your AI agents cost, think,
    and do"
  • H2s: Feature names, "Why TokenTelemetry?",
    "Supported Agents", "Quick Start", "FAQ"
  • URL: tokentelemetry.com (exact match domain ✓)
  • README keywords list (already exists at line 351
    of README.md — keep it updated)
  • Add /llms.txt and /opencode.json for AI crawlers
    (important given Tailwind CSS lesson)
```

---

*This document is ready to execute. Priority actions: Week 1 content creation, HN/PH launch prep, and DM outreach to target influencers — all can begin immediately.*
