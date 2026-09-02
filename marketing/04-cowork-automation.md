# Cowork Setup — What's Automated vs Manual

Goal: Cowork handles ~80% (drafting, research, monitoring, summarizing); you handle the 20% that needs a human (posting, judgment, relationships).

## Automated — scheduled tasks (created in Cowork)

| Task ID | Schedule | What it does |
|---------|----------|--------------|
| `tt-daily-content-draft` | Weekdays 7:30 AM | Reads `marketing/02-weekly-content-calendar.md` for today's slots, checks recent commits/UPDATE.json for material, writes ready-to-post drafts to `marketing/drafts/YYYY-MM-DD.md` (X post + any LinkedIn/Dev.to due that day, with image suggestions) |
| `tt-weekly-release-roundup` | Thursday 5:00 PM | Reads the week's `git log` + UPDATE.json, drafts the Feature Friday X thread, the Discord #announcements changelog, and a LinkedIn milestone post → `marketing/drafts/feature-friday-YYYY-MM-DD.md` |
| `tt-weekly-metrics-digest` | Sunday 6:00 PM | Pulls GitHub stars/issues/PRs/forks via GitHub MCP, compares to last week, flags unanswered issues, suggests next week's content angle → `marketing/drafts/weekly-digest-YYYY-MM-DD.md` |

All tasks run when Claude Desktop is open (or on next launch). Drafts accumulate in `marketing/drafts/` — your only job is review-and-post.

## Manual — Claude does NOT do these

- **Posting.** Everything is human-posted. Authentic accounts outperform automated ones, and platform ToS (especially Reddit) punish automation. Posting from drafts takes ~5 min/day.
- **Reddit comments.** Genuinely engage; Cowork can find threads for you on request ("find Reddit threads from this week about Claude Code costs") but the words should be yours.
- **X replies.** Same — Cowork can suggest accounts/threads to engage with; you write replies.
- **Discord conversations.** Community smells automation instantly.
- **Strategic calls.** When to Show HN, what to build, partnership outreach.

## On-demand asks (no schedule — just ask in a Cowork session)

- "Draft a Dev.to article on <topic> from the repo README and docs"
- "Find this week's Reddit/HN threads about agent token costs"
- "Turn this Discord support thread into an FAQ entry and a tweet"
- "Write the Show HN post + first comment" (launch week)
- "Summarize what shipped this month for a recap thread"

## Daily loop (~45–60 min total)

1. **Morning (15 min):** open `marketing/drafts/<today>.md`, edit voice, post to X (+ LinkedIn if due). Quick Discord pass.
2. **Midday (15 min):** Reddit — answer 2–3 cost/usage questions found organically or via an on-demand Cowork search.
3. **Evening (15 min):** X replies, GitHub issues, second Discord pass.
4. **Friday +10 min:** post the Feature Friday thread and Discord changelog from the roundup draft.
5. **Monday +10 min:** read Sunday's metrics digest; adjust the week's angle.

## House rules for generated content

- Drafts must cite real data (actual commits, actual dashboard numbers) — no invented stats.
- Voice: builder-to-builder, concrete, zero marketing fluff (see `reference/marketing-positioning-strategy.md` §6 Voice & Tone).
- Never auto-include competitor bashing; comparisons stay factual ("they require SDK integration; TT reads existing logs").
