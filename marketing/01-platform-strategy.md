# Platform-by-Platform Strategy

Core message everywhere: **"See what your AI agents actually cost — locally, in 30 seconds, zero config."** The differentiator vs Langfuse/LangSmith: no SDK, no cloud account, no code changes. Lead with that contrast constantly.

Deep playbooks live in `reference/` (HN strategy, SEO, 12-week calendar). This doc is the operating summary.

## Twitter/X — @VasiHemanth (primary channel)

**Why:** Your exact audience (Claude Code / Cursor / Codex power users) lives here and shares dashboards screenshots compulsively. Build-in-public works.

**What to post:**
- Screenshots of the dashboard with a real insight ("My refactor yesterday cost $4.20 — here's the trace")
- Feature announcements as short video/GIF threads
- Token-cost takes: "Most people have no idea what their agent sessions cost. Here's mine for the week."
- Replies to anyone tweeting about agent costs, Claude Code usage limits, token burn — reply with helpful data, link only if asked or natural
- Weekly "This week in TokenTelemetry" thread (ships from UPDATE.json)

**Cadence:** 1 post/day + 3–5 replies/day. Replies grow accounts faster than posts at your size.
**Format rules:** Always attach an image/GIF. First line must work standalone. No hashtags except occasionally #buildinpublic.

## Reddit (highest-converting, highest-risk)

**Why:** r/ClaudeAI, r/ChatGPTCoding, r/LocalLLaMA, r/selfhosted, r/opensource — these subs are full of people asking "how do I track Claude Code costs?" Answering that question IS the marketing.

**What to post:**
- 1 value post/week max per sub: "I built a local dashboard that reads Claude Code logs — here's what I learned about my own token usage" (data-first, tool-second)
- Daily: search for cost/usage questions and answer them genuinely; mention TT only when directly relevant
- Never post the same content to 2 subs the same day

**Cadence:** 1 post/week, 2–3 helpful comments/day.
**Rule:** 10:1 give:promote ratio or you get banned and the brand burns.

## LinkedIn

**Why:** Engineering managers and platform teams care about AI spend visibility — different framing of the same product. Lower competition for dev-tool content than X.

**What to post:**
- "Cost of AI coding agents" angle: budgets, team visibility, ROI of agent tooling
- Milestone posts (stars, integrations, releases) — LinkedIn rewards milestones
- Repurpose X threads as longer single posts with the same screenshot

**Cadence:** 2–3 posts/week. Don't daily-post here; it dilutes.

## Dev.to (+ cross-post to Hashnode)

**Why:** SEO. "track claude code token usage", "claude code cost tracking" — these searches grow monthly and have almost no good content. Posts rank for years.

**What to post:**
- Tutorials: "How to see exactly what Claude Code costs you (free, local, 2 min)"
- Architecture posts: "How TokenTelemetry parses logs from 35+ agents with zero config"
- Comparison content: "Langfuse vs LangSmith vs TokenTelemetry: when you need each"
- Each weekly feature → short "how it works" post when substantial

**Cadence:** 1 article/week. Canonical URL → your own site if you add a blog later.

## Discord (community home — see 03-discord-structure.md)

**Why:** Converts drive-by stars into contributors and evangelists. Also your support channel, which feeds content (every support question = future post/FAQ).

**Cadence:** Check 2×/day (5 min each). Weekly changelog post in #announcements.

## GitHub (the product IS the marketing)

- README is your landing page — keep the GIF/screenshot above the fold current
- Pin a "Roadmap" discussion + "Show us your dashboard" discussion
- Respond to issues within 24h — speed of maintainer response is the #1 trust signal for early OSS
- Tag releases properly; release notes feed all other channels

## Hacker News (event, not channel)

Save the Show HN for week 2+ of the launch sequence (see 05-launch-sequence.md and reference/go-to-market-growth-strategy.md §2). One shot — title format: "Show HN: TokenTelemetry – local, zero-config cost dashboard for Claude Code and 35+ agents".

## Priority order (1 hr/day budget)

1. X replies + 1 post (20 min)
2. Reddit comments (10 min)
3. Discord + GitHub issues (15 min)
4. Review Cowork drafts for tomorrow (15 min)

LinkedIn and Dev.to run on Cowork-drafted content you approve in batch — they don't consume daily time.
