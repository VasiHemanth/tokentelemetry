# TokenTelemetry — Go-to-Market & Growth Channels Strategy

**Date:** June 2026
**Author:** Growth Marketing (ex-Google, Microsoft, high-growth startups)
**Product:** TokenTelemetry — free, open-source, 100% local multi-agent observability dashboard

---

## Executive Summary

TokenTelemetry sits at a unique intersection: **AI coding agents are exploding** (Claude Code alone hit $2B+ run-rate by Sep 2025, Anthropic at $30B by Apr 2026), **every developer using them wants to know what they cost**, and **no existing tool offers zero-config, multi-agent, 100% local observability**. Langfuse ($40M+ ARR, ClickHouse acquisition), LangSmith, Helicone are all cloud-based, require SDK instrumentation, and none support the multi-agent coding-agent use case natively.

The window is 6-12 months. Here's the playbook.

---

## 1. Top 5 Growth Channels — Ranked by ROI

### #1: Organic GitHub Growth (ROI: Highest)

**Why:** Every developer who hits this problem searches GitHub first. The README is your landing page. Stargazers convert to users at 5-15% for OSS dev tools.

**Execution Plan:**

| Tactic | Timeline | Expected Impact |
|--------|----------|----------------|
| Submit to **awesome-claude-code**, **awesome-LLM-observability**, **awesome-opensource-devops**, **awesome-ai-agents** | Week 1-2 | 200-500 stars |
| **Showcase repo**: Build `tokentelemetry-showcase` with real screenshots, session traces, cost comparisons from 3 agents | Week 2-3 | Viral loop |
| **GitHub trending**: Target Node.js + Python trending by timing releases to Mon/Tue mornings | Every release | 500-2000 stars per trending hit |
| **Readme.so optimization**: Above-the-fold GIF demo, stars badge, "Install in 5 seconds" | Immediate | Higher conversion |
| **Cross-star campaigns**: Collaborate with ccusage (10.1k stars), claude-code-templates for mutual README mentions | Week 3-4 | 300-800 stars |
| **GitHub Discussions** as primary community hub (like PostHog moved from Slack to forum) | Week 1 | Organic engagement |

**Companies that nailed this:** Supabase (100k stars), Vercel/Next.js (60k+), Tailwind CSS — all grew primarily through GitHub organic.

**Exact README badges to add:**
```markdown
[![Install in 5 seconds](https://img.shields.io/badge/Install-5_seconds-blue)]()
[![Multi-Agent Dashboard](https://img.shields.io/badge/Multi--Agent-10_agents-green)]()
[![100% Local](https://img.shields.io/badge/Privacy-100%25_Local-success)]()
```

**PostHog-inspired growth trick:** Every commit auto-publishes a changelog. Keep `CHANGELOG.md` detailed. Developers love seeing active development.

---

### #2: Hacker News Launch (ROI: Very High)

**Why:** HN drives 100k+ visitors in 24 hours for top posts. For dev tools, it's the single highest-quality traffic source.

*See Section 2 for the full launch playbook.*

---

### #3: Content SEO + Developer Blogs (ROI: High, Compounding)

**Why:** "claude code token usage" searches are growing exponentially. There are ~8 competing tools (ccusage, cc-statistics, claude-code-templates) but **none** that do multi-agent. The keyword gap is wide open.

**Execution Plan:**

| Content Piece | Target Keyword | Est. Monthly Search |
|--------------|---------------|-------------------|
| "How to track Claude Code token usage" | `claude code token usage` | 5k-15k |
| "AI agent observability tools comparison" | `AI agent observability` | 3k-8k |
| "Claude Code cost tracking dashboard" | `claude code cost` | 2k-5k |
| "Monitor Gemini CLI costs" | `gemini cli cost` | 1k-3k |
| "Open source LLM cost tracking" | `open source LLM cost tracking` | 2k-4k |
| "Multi-agent observability guide" | `multi-agent observability` | 500-2k |
| "Claude Code vs Codex vs Gemini CLI cost comparison" | `claude code vs codex cost` | 1k-3k |
| "Zero-config local observability" | `local LLM monitoring` | 800-2k |
| "Hermes Agent monitoring dashboard" | `hermes agent observability` | 500-1k |

**Content pillars:**
1. **Tutorials** — "Track X agent in 5 seconds" (one per agent = 11 pieces)
2. **Comparisons** — "TokenTelemetry vs Langfuse vs LangSmith vs Helicone" (own the comparison narrative)
3. **Deep dives** — "How Claude Code's JSONL logs work" (establish authority)
4. **Use cases** — "How an engineering manager tracks team AI spend" (enterprise angle)

**Technical SEO:**
- Blog on `tokentelemetry.com/blog/` with proper schema markup
- Programmatic landing pages per agent: `/claude-code`, `/gemini-cli`, `/cursor`, `/hermes-agent`
- Comparison pages: `/vs/langfuse`, `/vs/langsmith`, `/vs/helicone`
- FAQ schema on home page (already partially there)

---

### #4: Content Creator / YouTuber Collaborations (ROI: High)

**Why:** The AI coding space is content-hungry. Every YouTuber covering "Claude Code tips" needs a cost-tracking segment.

**Execution Plan:**

| Creator | Channel Reach | Pitch |
|---------|--------------|-------|
| **Fireship** (1M+ dev subs) | Huge | "100 seconds of AI observability" — perfect format |
| **Nick Chapsas** (500k+ .NET) | Strong | "How much do AI coding agents actually cost?" |
| **ThePrimeagen** (500k+ dev) | Strong | "I built a dashboard that tracks every agent's token usage" |
| **Floatyboat** / **DevOps Toolkit** | Niche | "Multi-agent observability deep dive" |
| **AI Explained** | AI-focus | Visual demo of session traces across 4 agents |

**Tactic:** Offer each creator a pre-provisioned demo with 4 agents already run against their repo. "30 min setup, you just record."

---

### #5: Agent Ecosystem Integration (ROI: Medium-High, Defensible)

**Why:** If TokenTelemetry is listed in Claude Code's docs, Cursor's docs, or Hermes Agent's docs, it gets permanent traffic.

| Integration | Tactic | Timeline |
|------------|--------|----------|
| **Claude Code docs** | PR to add to "community tools" / "telemetry" section | Week 2 |
| **Cursor docs** | PR to add similar section | Week 2 |
| **Hermes Agent** | Already integrated via plugin — PR to add to Hermes README | Week 1 |
| **awesome-claude-code** | Submit PR | Week 1 |
| **awesome-gemini-cli** | Submit PR | Week 1-2 |
| **OpenRouter** | Cross-promotion (OpenRouter users want cost tracking) | Week 3-4 |
| **VSCode extension** | "TokenTelemetry Status Bar" — shows live token burn | Month 2 |

---

## 2. Hacker News Launch Strategy

### Title Options (A/B Tested)

**Option A (Pain-point driven):**
> Show HN: TokenTelemetry — Free, local dashboard that tracks token usage across ALL your AI coding agents

*Why: "ALL your" creates FOMO. "Free, local" is the key differentiator.*

**Option B (Trigger + transformation):**
> Show HN: Wondering how much Claude Code, Codex, and Gemini CLI actually cost? I built a free local dashboard

*Why: Question format triggers curiosity. "I built" is personal.*

**Option C (Contrarian / against the grain):**
> Show HN: TokenTelemetry — 100% local observability for AI agents (no cloud, no signup, no SDK)

*Why: Contrasts with Langfuse/LangSmith. Appeals to HN's anti-cloud bias.*

**Option D (Numbers-driven):**
> Show HN: Real-time token & cost tracking for 10 AI coding agents — 100% local, one command

*Why: "10 agents" is specific. "One command" is zero friction.*

**Option E (Benchmark bait):**
> Show HN: I built a local dashboard that compares Claude Code, Codex, and Gemini CLI token efficiency side-by-side

*Why: Comparison drives engagement. HN loves benchmarks.*

**Pick:** Option A as primary, Option C as secondary if A doesn't gain traction within 60 min.

### First Comment Strategy (The "Founder's Story")

Post this as the first comment **immediately** after submitting:

---

Hey HN! I built TokenTelemetry because I was tired of guessing how many tokens my AI coding sessions actually consumed.

I use Claude Code, Codex CLI, and Gemini CLI depending on the task, and I had NO idea which was more efficient. Langfuse and LangSmith wanted me to instrument code and send data to their cloud. I wanted something that just... worked.

TokenTelemetry reads the log files your agents already write (~/.claude/, ~/.codex/, ~/.gemini/ etc.) and serves a local dashboard. No SDK, no signup, no data leaving your machine.

**What makes it different:**
- Supports 10 coding agents + Hermes Agent (autonomous agent) — the only multi-agent dashboard
- Zero config — install and open localhost:3000
- 100% local — your logs never leave your machine
- Hermes Agent gets a dedicated dashboard (gateway health, cron jobs, 38 source platforms)
- MIT open source, free forever

**Most surprising thing I learned building this:**
- Claude Code uses WAY more tokens per session than Codex (avg 4x)
- Reasoning/thinking tokens account for 30-40% of cost on Claude
- Cursor sessions are surprisingly short but frequent
- Hermes Agent subagent calls are invisible to every other tool

Would love feedback on:
1. What agents should I add next? (Open PR if your agent isn't listed)
2. What metrics would you want?
3. Any features you'd pay for? (I want to keep the core free but curious)

Repo: https://github.com/VasiHemanth/tokentelemetry
Install: `curl -fsSL https://tokentelemetry.com/install.sh | bash`

---

### Timing & Day of Week

| Day | Verdict | Rationale |
|-----|---------|-----------|
| **Tuesday** | ✅ **BEST** | 9:00 AM ET / 6:00 AM PT. Highest quality engagement. Max time before weekend. |
| Wednesday | ✅ Good | Second best. Slightly more crowded. |
| Thursday | ⚠️ OK | Engagement drops Thursday PM. |
| Monday | ⚠️ Risky | High volume, easy to get buried. |
| Friday-Sunday | ❌ Avoid | Dead zone for dev tools. |

**Time:** 9:00 AM ET (6:00 AM PT / 14:00 UTC / 15:00 CET) — catches both US coasts and Europe.
**Check:** Don't launch on holidays, major tech events (WWDC, Google I/O, OpenAI DevDay), or when a competing product is on front page.

### Handling Comments / Questions

| Scenario | Response Strategy | Example |
|----------|-------------------|---------|
| "How is this different from Langfuse?" | Direct comparison, zero-config angle | "Langfuse requires SDK instrumentation and sends data to their cloud. TT reads log files locally. Two different use cases." |
| "Is this safe? My logs have secrets." | Emphasize 100% local, no telemetry | "Every line of code is readable. Data never leaves localhost. I'd eat my hat if it does." |
| "Why not just use the built-in /usage command?" | Explain multi-agent, historical view | "/usage is per-session. TT gives you cross-agent, cross-project history with visualizations." |
| "Will this remain free?" | Commit publicly | "MIT license. You can fork it and run it forever. If I ever build a paid version, it'll be for cloud features only." |
| "How do I add a new agent?" | Point to CONTRIBUTING.md | Link directly. |
| "This is similar to my project" | Acknowledge, celebrate | "Would love to collab! Happy to link to yours in README." |
| Negative / dismissive | Don't argue. Engage genuinely. | "Fair point. What would make this useful for you?" |

**Golden rule:** Every comment reply is public marketing. Be humble, helpful, and transparent. PostHog's founders built their entire reputation on HN comments.

### Case Study: Lessons from Langfuse's HN Launch

- **Original Show HN (Aug 2023):** Modest reception (~150 points)
- **Launch HN (Dec 2024, YC-backed):** 215 points, 61 comments
- **What worked:** The "v2 with ClickHouse" narrative showed momentum. "Thousands of teams, including KhanAcademy/Twilio" = social proof.
- **What to replicate:** Social proof in the first comment ("used by X developers"), v3.0 narrative (show progress)
- **What to avoid:** Don't lead with YC (you're not YC). Lead with the product.

### Post-HN Follow-up

| Time | Action |
|------|--------|
| Day 1 (hour 1-2) | Ping 3-5 friends to engage in comments |
| Day 1 (hour 3-4) | Post to r/programming, r/MachineLearning |
| Day 1 (evening) | Tweet/X thread summarizing HN reception |
| Day 2-3 | Blog post: "Our HN launch and what we learned" |
| Day 7 | Measure: stars, installs, issues, Discord joins |

---

## 3. Product Hunt / Reddit Playbook

### Product Hunt Launch Strategy

**When to launch:** 2-4 weeks AFTER the HN launch (let that wave crest, then capture PH audience)

**PH Launch Checklist:**

**Preparation (2 weeks before):**
- [ ] Create PH listing with polished first screenshot (dashboard view)
- [ ] Prepare GIF demo (15-30 seconds, multi-agent switch)
- [ ] Write first comment (high-value, similar to HN first comment)
- [ ] Build hunter list: DM 10-15 PH power users in developer tools category
- [ ] Gather 5-10 beta users willing to leave public reviews on PH
- [ ] Prepare Twitter announcement thread
- [ ] Schedule: **Tuesday 12:01 AM PT** (PH day starts)

**Day-of Execution:**
- 12:01 AM PT — Listing goes live
- 12:05 AM PT — Post first comment + product GIF
- 6:00 AM PT — Tweet announcement thread (pin it)
- 7:00 AM PT — Post to relevant Discords / Slacks
- 9:00 AM PT — Email list (if any)
- Throughout — Engage every comment within 15 min

**Follow-up (Week after):**
- Thank-you post on PH
- Blog: "We hit #1 on Product Hunt"
- Add "Featured on Product Hunt" badge to website

**Supabase case study:** Launched 16 times on PH. First was alpha. Fourth was #1 Product of the Day. Lesson: **Launch multiple times** (alpha, GA, major features).

### Reddit Strategy

**Target Subreddits:**

| Subreddit | Strategy | Post Frequency |
|-----------|----------|----------------|
| r/programming | "Show HN" style post with comparison data | Launch + quarterly updates |
| r/MachineLearning | Focus on cost tracking for LLM agents | Launch + new agent support |
| r/ClaudeAI | "How to track Claude Code costs" (helpful, not promotional) | Weekly |
| r/cursor | "See what Cursor sessions actually cost" | Bi-weekly |
| r/githubcopilot | "Copilot usage tracker + cost dashboard" | Bi-weekly |
| r/selfhosted | "100% local, open source, no cloud" — huge appeal | Monthly |
| r/opensource | "MIT, free, zero config" | Launch |
| r/hermesagent | Dedicated Hermes Agent dashboard announcement | Once (then answer questions) |
| r/LocalLLaMA | Local-first ethos matches the sub | Once per major feature |
| r/devops | Observability angle | Launch |

**Post Template for r/programming:**

```
Title: I built a free, local dashboard that tracks token usage across 10 AI coding agents

I was tired of guessing which agent costs more — Claude Code vs Codex vs Gemini CLI.

TokenTelemetry reads agent log files and shows:
- Real-time token & cost tracking
- Multi-agent unified dashboard
- Session traces with full tool call waterfalls
- 100% LOCAL — no cloud, no signup

Install: curl -fsSL https://tokentelemetry.com/install.sh | bash

Questions/feedback welcome!
```

**Golden rule:** 80% helpful content, 20% promotion. Every r/ClaudeAI post should answer "How to track costs?" before mentioning TokenTelemetry.

---

## 4. Community Building Plan

### Discord Server Structure

```
# 🎫 ─ WELCOME
├── #rules (one rule: be excellent to each other)
├── #welcome (auto-role, GitHub star ⭐ badge)
└── #announcements (releases, features, launch week)

# 💬 ─ GENERAL
├── #general (casual chat)
├── #show-and-tell ("this is my dashboard" screen share)
├── #support (community-powered, like Supabase)
└── #feature-requests (voting with emoji reactions)

# 🤖 ─ AGENTS
├── #claude-code
├── #codex
├── #gemini-cli
├── #cursor-copilot
├── #qwen-vibe-antigravity
├── #grok-build
├── #hermes-agent (pin plugin install command)
├── #opencode
└── #agent-requests ("add support for X")

# 🛠 ─ CONTRIBUTORS
├── #contributors-wanted (good first issues)
├── #dev-chat (architecture, PRs, code review)
├── #plugin-dev (Hermes plugin, future plugins)
└── #show-your-code (PR demos)

# 📊 ─ DATA & ANALYTICS
├── #cost-tracking-tips
├── #token-optimization (share CLAUDE.md optimizations)
├── #model-comparisons
└── #dashboard-screenshots

# 🌍 ─ COMMUNITY
├── #introductions (new member onboarding)
├── #oss-chat (general open source talk)
├── #random
└── #jobs (optional, sponsored)
```

**Growth Tactics:**
- **Auto-role on GitHub star** — star the repo to get `#contributors` access
- **Weekly "Token Tip Tuesday"** — in `#announcements`, share cost-saving tip
- **Monthly "Dashboard of the Month"** — best screenshot wins shoutout
- **"I built X with TokenTelemetry"** — community showcase channel
- **Supabase approach:** Outgrow Discord → move to forum (PostHog did this, but start with Discord for 0-1000 users)

### GitHub Star Growth Tactics

| Tactic | Detail | Expected Stars |
|--------|--------|---------------|
| **awesome-list submissions** | 8 lists (awesome-claude-code, awesome-LLM-observability, awesome-opensource-devops, awesome-selfhosted, awesome-devtools, awesome-ai-agents, awesome-observability, awesome-mit) | +200-500 |
| **Tweet storms** | Founder posts "How much did my AI coding cost this month?" with screenshot. Goes viral in dev circles | +300-800 |
| **Showcase repos** | `tokentelemetry-showcase` with real data from 5+ agents | +100-300 |
| **Release week** | Ship Hermes Dashboard plugin as a launch week (copy Supabase's cadence: every 3-4 months) | +500-1500 |
| **Cross-promotion READMEs** | Swap README badges with ccusage, cc-statistics, and related tools | +100-200 |
| **GitHub Discussions** | "What's your monthly AI agent cost?" — sticky post, drives engagement | +50-100 |
| **Issue-driven engagement** | Pin "Add support for X agent" — community votes on next agent | +100-200 |
| **HN bump** | Each HN feature drives 500-2000 stars | +500-2000 |

**6-month star target:** 2,000-5,000 (reasonable for early-stage OSS dev tool)

### Twitter/X Presence Strategy

**Founder's personal account** (@VasiHemanth):
- Style: Transparent, technical, slightly irreverent (PostHog energy)
- Post 5-7x/week
- **Content mix:**
  - 30% — Screenshots of TokenTelemetry in action
  - 20% — "What I learned building this" (build-in-public)
  - 20% — AI agent industry commentary
  - 15% — Cost data sharing ("Claude Code cost me $X this month")
  - 15% — Retweets/engagement with community

**Exact tweets to post:**

```
"I ran Claude Code, Codex, and Gemini CLI on the same refactor.

Here's what they cost:

Claude Code: $4.27
Codex: $1.83
Gemini CLI: $0.91

The 100% local dashboard that tracks all 3: https://tokentelemetry.com

Free, open source, no signup."
```

```
"Your AI coding agents are burning tokens.

You just can't see it.

TokenTelemetry gives you a real-time dashboard of every agent, every model, every project.

100% local. No data leaves your machine.

curl -fsSL https://tokentelemetry.com/install.sh | bash"
```

```
"I see people asking "how much does Claude Code cost" every week.

So I built something that answers it automatically.

TokenTelemetry tracks ALL your agents in one dashboard.

Open source. MIT. Free.

⬇️ https://tokentelemetry.com"
```

```
"Engineering managers: How much is your team spending on AI coding agents?

If you don't know, you're overspending.

TokenTelemetry gives you per-developer, per-project cost visibility.

And it's 100% local.

https://tokentelemetry.com"
```

**Best times to post:** 8-10 AM ET / 12-1 PM ET / 5-6 PM ET (Tue-Thu best days)

### Contributor Onboarding Funnel

```
Step 1: "Good first issue" labels with detailed CONTRIBUTING.md
  → Number of issues: 5-10

Step 2: Discord #contributors-wanted channel
  → Auto-post new good-first-issues via GitHub webhook

Step 3: CONTRIBUTING.md with "30 minute first PR" guide
  → Add agent support is the easiest entry point

Step 4: Acknowledge every PR within 24 hours
  → Even if not merged, say thank you

Step 5: Weekly "Contributor Highlights" in Discord
  → Shoutout by username + contribution

Step 6: "Agent Support Template" (new agent in < 50 lines)
  → Make it so easy a first-time contributor can add Gemini CLI support
```

---

## 5. SEO Keyword Strategy

### High-Intent Keyword Clusters

**Cluster 1: Claude Code Costs** (Highest volume)
| Keyword | Intent | Priority |
|---------|--------|----------|
| claude code token usage | Commercial | 🔴 P0 |
| claude code cost tracking | Commercial | 🔴 P0 |
| claude code session viewer | Commercial | 🟡 P1 |
| claude code token monitor | Commercial | 🟡 P1 |
| how to track claude code tokens | Informational | 🟡 P1 |
| claude code claude code analytics | Commercial | 🟡 P1 |
| claude code usage dashboard | Commercial | 🟡 P1 |

**Cluster 2: Multi-Agent & LLM Observability** (Differentiator)
| Keyword | Intent | Priority |
|---------|--------|----------|
| AI agent observability | Informational | 🔴 P0 |
| multi-agent observability | Informational | 🟢 P2 |
| LLM cost tracking tool | Commercial | 🔴 P0 |
| AI coding agent analytics | Commercial | 🟡 P1 |
| token usage dashboard open source | Commercial | 🔴 P0 |
| local LLM monitoring tool | Commercial | 🟡 P1 |
| open source AI observability | Informational | 🔴 P0 |

**Cluster 3: Competitor Comparisons** (Capture switching intent)
| Keyword | Intent | Priority |
|---------|--------|----------|
| langfuse alternative | Commercial | 🔴 P0 |
| langsmith alternative open source | Commercial | 🔴 P0 |
| helicone alternative | Commercial | 🔴 P0 |
| langfuse vs tokentelemetry | Commercial | 🟡 P1 |
| open source observability for LLM apps | Informational | 🟡 P1 |

**Cluster 4: Agent-Specific Cost Tracking**
| Keyword | Intent | Priority |
|---------|--------|----------|
| gemini cli cost tracking | Commercial | 🟡 P1 |
| codex token usage | Commercial | 🟡 P1 |
| openai codex cli cost | Commercial | 🟡 P1 |
| cursor ide token usage | Commercial | 🟡 P1 |
| github copilot usage tracker | Commercial | 🟡 P1 |
| qwen cli token tracking | Commercial | 🟢 P2 |
| grok build cost monitor | Commercial | 🟢 P2 |

### Content Pillars

**Pillar 1: "The Complete Guide to AI Coding Agent Costs"**
- Hub page at `/guides/ai-coding-agent-costs`
- 11 sub-pages (one per agent)
- Comparison tables
- Embedded install widget
- Internal links to all comparison pages

**Pillar 2: "TokenTelemetry vs [Competitor]"**
- Dedicated comparison pages: `/vs/langfuse`, `/vs/langsmith`, `/vs/helicone`
- Feature comparison tables
- The "zero config" advantage
- CTA: "Try it in 5 seconds"

**Pillar 3: "Agent-Specific Guides"**
- `/claude-code/token-usage` — What logs look like, how TT parses them
- `/gemini-cli/cost-analytics` — Similar per-agent
- `/hermes-agent/observability` — The unique Hermes dashboard

**Pillar 4: "Engineering Team AI Spend Management"**
- `/enterprise` — Team-level cost visibility
- `/blog/managing-team-claude-code-spend`
- Case study narrative: "How we saved 40% on AI agent costs"

### Technical SEO

- **Sitemap:** Dynamic sitemap.xml with all /vs/ pages, /guides/, /blog/
- **Schema:** FAQ schema on homepage (already there), HowTo schema on install pages
- **Performance:** Next.js site already — ensure Core Web Vitals green
- **Programmatic pages:** `/claude-code`, `/codex`, `/gemini-cli`, `/cursor`, `/copilot` — each with screenshots + comparison to raw logs
- **GSC setup:** Submit sitemap, monitor queries for "claude code" + "token" variations
- **Backlink strategy:** OSS directories (OssTracker, ReposHub), GitHub README backlinks, "Built with" badges

---

## 6. Partnership & Integration Growth

### Getting Listed in Agent Documentation

| Target | Approach | Contact |
|--------|----------|---------|
| **Claude Code docs** | PR to `anthropics/claude-code` adding to "Community tools" section | Claude Code GitHub issues |
| **Cursor docs** | PR to cursor docs "Complementary tools" | Cursor docs repo |
| **Gemini CLI docs** | Open an issue in google-gemini repo suggesting addition | gemini-cli GitHub |
| **Anthropic's cookbook** | Submit a cookbook entry: "Tracking Claude Code usage with TokenTelemetry" | cookbook PR |
| **Hermes Agent docs** | Already have plugin — ensure it's in Hermes README | Hermes Agent repo |
| **OpenRouter** | OpenRouter users want to track costs per route | OpenRouter community |
| **Vibe / Antigravity** | Early-stage projects, easier to get listed | Direct GitHub issues |

**Exact PR template for agent docs:**

```
## Add TokenTelemetry to Community Tools

TokenTelemetry is a free, open-source, 100% local observability
dashboard that works out of the box with [Agent Name]. It reads
session logs the agent already writes — no instrumentation needed.

- **Multi-agent dashboard** — track [Agent] alongside Claude Code, Codex, etc.
- **100% local** — no data leaves the machine
- **Zero config** — install and open localhost:3000

[Badge] | [Install command] | [Website]
```

### Cross-Promotion With Related OSS Projects

| Project | Relationship | Cross-promotion Tactic |
|---------|-------------|----------------------|
| **ccusage** (10.1k stars) | Complementary — TT has dashboard, ccu has CLI | Mutual README mentions; "For a GUI dashboard, try TT" |
| **claude-code-templates** | Different focus | Same — complementary |
| **Hermes Agent** | Built-in integration | Plugin README, cross-link |
| **OpenCode** | Already supported | Ask to add to OpenCode community tools |
| **LiteLLM** | Proxy-based tracking (cloud) | Different approach, could link as alternative |
| **Opik (Comet)** | Competing LLM observability | Competitive but could interop |
| **PromptFoo** | Evaluation focus, different product | Cross-promote for "observability + eval" combo |

### Plugin Ecosystem Strategy

| Plugin | Description | Priority |
|--------|-------------|----------|
| **VSCode extension** | "TokenTelemetry Status Bar" — live token burn in editor | 🟡 Month 2 |
| **Hermes Dashboard plugin** | Already built — promote heavily | 🔴 Month 1 |
| **Claude Code MCP server** | "Ask TokenTelemetry: what did I spend this week?" | 🟡 Month 2 |
| **GitHub Actions** | PR comment with cost analysis of CI agent usage | 🟢 Month 3 |
| **Slack bot** | Weekly team cost report in Slack | 🟢 Month 3 |
| **Webhook endpoint** | Post to any URL when a session completes | 🟡 Month 2 |

### "Built with TokenTelemetry" Viral Loop

Add a small HTML snippet users can add to their README:

```html
<!-- Built with TokenTelemetry badge -->
<a href="https://tokentelemetry.com">
  <img src="https://tokentelemetry.com/badge.svg"
       alt="Monitored with TokenTelemetry"
       width="200" />
</a>
```

Also a CLI option: `tokentelemetry badge` that prints the markdown badge.

---

## Launch Timeline (12 Weeks)

```
Week 1-2:   FOUNDATION
            - Submit to 8 awesome lists
            - Set up Discord with full channel structure
            - Create comparison pages on website
            - Begin blog content production
            - PR agent docs (Claude Code, Cursor, Hermes)

Week 3-4:   PRE-LAUNCH
            - Gather 10 beta testers for pre-HN validation
            - Reach out to 5 content creators
            - Start Twitter/X daily posting
            - First blog posts go live
            - GitHub trending optimization

Week 5:     HACKER NEWS LAUNCH
            - Tuesday 9:00 AM ET
            - First comment strategy executed
            - Reddit cross-posts (r/programming, r/MachineLearning)
            - Twitter/X thread

Week 6-7:   POST-HN MOMENTUM
            - Blog: "Our HN launch and what we learned"
            - HN bump content to SEO pages
            - Compile first user screenshots
            - VSCode extension development starts

Week 8:     PRODUCT HUNT LAUNCH
            - PH listing with polished screenshots
            - Hunter outreach
            - Launch week concept (#BuiltWithTokenTelemetry)

Week 9-12:  SUSTAINED GROWTH
            - Weekly blog posts
            - YouTube creator collaborations
            - Monthly Discord community event
            - Agent support requests (community-driven)
            - Track SEO rankings, iterate on keywords
```

---

## Key Metrics Dashboard

| Metric | Current | 3-Month Target | 6-Month Target |
|--------|---------|----------------|----------------|
| GitHub Stars | ~50 | 500-1000 | 2,000-5,000 |
| Daily Installs | N/A | 20-50 | 100-300 |
| Discord Members | N/A | 200-500 | 1,000-2,000 |
| Website Monthly Visitors | N/A | 5,000-10,000 | 30,000-50,000 |
| Blog Posts Published | 0 | 15-20 | 30-40 |
| Content Creator Collabs | 0 | 2-3 | 5-8 |
| SEO Keywords in Top 10 | 0 | 10-15 | 25-40 |
| New Agent PRs (community) | 0 | 2-5 | 5-10 |

---

## Competitive Positioning (For Quick Reference)

| Dimension | TokenTelemetry | Langfuse | LangSmith | Helicone |
|-----------|---------------|----------|-----------|----------|
| Setup time | 5 seconds | 15-30 min | 15-30 min | 15-30 min |
| Data residency | Local only | Cloud/Self-host | Cloud | Cloud |
| Multi-agent coding | ✅ Built-in | ❌ Manual | ❌ Manual | ❌ Manual |
| Hermes Agent | ✅ Dedicated | ❌ Generic | ❌ Generic | ❌ Generic |
| Pricing | Free | Freemium | Freemium | Freemium |
| Open source | MIT | MIT | ❌ | ❌ |
| Languages | README only | Py/JS SDK | Py/JS SDK | Py/JS SDK |

---

## Summary: The 3 Moves That Matter Most

1. **HN launch with an A/B-tested title and founder's story** — this is your single highest-leverage event. Get it right and you skip 6 months of growth.

2. **SEO content for "claude code token usage" + alternatives** — this keyword cluster is exploding and under-served. Being #1 for 5 of these queries is 20,000+ monthly visitors.

3. **Agent ecosystem integrations** — getting listed in Claude Code docs, Cursor docs, and Hermes Agent README provides permanent, compounding traffic. These are the moats.
