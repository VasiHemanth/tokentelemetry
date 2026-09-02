# Discord Server Structure — TokenTelemetry

Optimized for a solo founder: few channels, so the server never looks empty. Start with ~10 channels; split only when one gets noisy. (A fuller variant exists in `reference/go-to-market-growth-strategy.md` §4 — this is the trimmed launch version.)

## Channels

**📌 START HERE**
- `#welcome` — auto-greeting, rules, links (GitHub, site, install one-liner). Read-only.
- `#announcements` — releases, milestones. Read-only; this is where Feature Friday lands.
- `#introductions` — "what agents do you run?"

**💬 COMMUNITY**
- `#general` — everything goes here first. The single most important channel.
- `#show-your-dashboard` — screenshots of people's TT dashboards. **Your secret weapon**: every post here is shareable social content (with permission) and social proof.
- `#agent-talk` — Claude Code / Cursor / Codex / Hermes chatter not about TT itself. Keeps #general on-topic and gives lurkers a reason to stay.

**🛠 PRODUCT**
- `#support` — install issues, bugs. Forum-style channel so threads stay separate.
- `#feature-requests` — forum-style; ask people to upvote with 👍. Feeds your roadmap publicly.
- `#contributors` — for people working on PRs; link CONTRIBUTING.md in topic.

**🔔 FEEDS** (automation, no humans required — makes server feel alive)
- `#github-feed` — webhook: stars, releases, merged PRs (use GitHub's built-in Discord webhook).

## Roles

- `@Maintainer` — you
- `@Contributor` — merged a PR (assign manually; people display it proudly)
- `@Early Crew` — first 50 members, never given again. Costs nothing, drives early joins.
- Agent-pick roles via reaction in #welcome (`@Claude Code`, `@Cursor`, `@Hermes`, …) — lets you @-mention the right group when you ship agent-specific features.

## Onboarding flow

1. Land in #welcome → one-screen message: what TT is, install command, "introduce yourself"
2. Reaction-role prompt for which agents they use
3. Auto-greet bot message in #introductions (MEE6/Carl-bot free tier is fine)

## Solo-founder operating rules

- Check 2×/day, 5 min each (morning, evening). Cowork drafts the weekly changelog post for #announcements.
- Answer every #support question within 24h, even just "looking into it."
- Seed activity for the first month: post your own dashboard in #show-your-dashboard weekly, ask one question in #general per week. Empty servers stay empty; slightly-active ones grow.
- Don't create more channels because they "might be needed." Dead channels kill servers.

## Launch checklist

- [x] Create server, channels, roles above — done via Cowork (2026-06-12)
- [ ] GitHub webhook → #github-feed (repo Settings → Webhooks → Discord preset)
- [ ] Carl-bot or MEE6 for reaction roles + welcome message
- [ ] Permanent invite link → README badge, website header, X bio, Dev.to bios
- [ ] Post invite in launch-sequence posts (see 05-launch-sequence.md, Day 1)

## Live server facts (set up 2026-06-12)

- **Permanent invite: https://discord.gg/wQUMzVAK9u** (never expires, no use limit)
- Categories: 💬 COMMUNITY (#general, #show-your-dashboard, #agent-talk), 📌 START HERE (#welcome, #announcements, #introductions), 🛠 PRODUCT (#support, #feature-requests, #contributors, #github-feed), 🔔 FEEDS (empty)
- #welcome and #announcements are read-only for @everyone (send messages + thread creation denied)
- Roles created: Maintainer, Contributor, Early Crew (no colors/permissions set yet)
- Manual TODOs: drag #github-feed into 🔔 FEEDS; drag 📌 START HERE above 💬 COMMUNITY; assign yourself the Maintainer role; #support and #feature-requests are regular text channels (convert to Forum after enabling Community in Server Settings → Enable Community)
