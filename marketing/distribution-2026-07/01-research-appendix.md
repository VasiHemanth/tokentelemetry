# Research appendix, distribution plan 2026-07-30

Eleven research agents reported before `00-DISTRIBUTION-PLAN.md` was written.
This file is their output, lightly organised, so any recommendation in the plan
can be traced back to its source. Findings are the agents' own; where the plan
overrode one, the override is noted in the plan (section 5, YouTube) rather than
edited out here.

Contents:

- Phase 1, audience personas: limit-hitter, local-llama, harness-hopper, eng-manager
- Phase 2, platform analysts: threads, linkedin, longform, video
- Phase 3, asset architects: video-pipeline, agent-browser, telemetry-stories
- Phase 4, cross-agent agreements and disagreements

---

# Phase 1: audience personas

## limit-hitter

**Headline:** GitHub is already converting ~97 stars a month while the entire
social funnel produced 13 install-page views, so the bottleneck is not reach
volume but the total absence of owned content and a measurable landing path; as
the target reader I dismissed his account the moment I saw a profile made only
of replies.

**Findings**

1. His real acquisition channel is GitHub, not social. Weekly digests record 107
   stars on 2026-06-14 rising to 283 on 2026-07-26 (+41, +62, +18, +26, +29 per
   week), about 97 stars in the same 30 days the site produced 13 install-page
   views. Stars outnumber install-page views roughly 7.5 to 1, so at least 86% of
   growth events never saw the homepage. (Basis: `marketing/drafts/weekly-digest-*.md`.
   Note the digest says 283 stars, the brief says 154; the deltas hold either way.)
2. The 0.0167% clickthrough is the profile, not the comment. 676 replies and zero
   original posts reads as a bot. A reply earns a click only when the profile
   behind it looks like a person who publishes.
3. Subscription users have no marginal dollar to save. Search intent is
   limit-shaped, not cost-shaped: "claude code weekly limit reset", "why did I hit
   my limit so fast", "cursor charged me extra". His own top placements include
   "Fable 5 plan limits" and "Why pay $385k when Cursor is $20/mo".
4. Production was never the bottleneck and he keeps investing there. 40 videos
   produced, 9 published. 24 dated draft files in `marketing/drafts` covering X,
   LinkedIn, Discord, Reddit and Dev.to per day, several post-ready, none shipped.
5. The cost-per-task reframe wins in feeds and loses in search. Vendors already own
   those SERPs (PointFive, ivern.ai, morphllm, The Register 2026-07-13), and nine
   consecutive vendor listicles rank for "how much does Claude Code cost per
   month" with no first-party measurement.
6. Launch-day comments reached him; steady-state comments annoyed him. News-day
   timing is the whole variable.
7. 61% mobile against a desktop curl-pipe-bash install means the homepage is being
   asked to do a job it cannot do. Clarity 86/100 rules out speed.
8. Measurement contradicts itself in four places: stars 283 vs 154, GA4 key
   events 0, Threads likes reaching 150,000,000, 676 rows all `status=posted` with
   no removal check on a 32% sample.

**Recommendations:** GA4 key events plus copy-to-clipboard handler plus a UTM
convention (2h one-time, 0.2 h/wk); build `tokentelemetry report` as a one-shot
terminal command and make it the primary CTA (8h one-time); one canonical
monthly-updated page on what agents actually cost him (5h then 1h/month); 3
original Threads posts per week instead of replies (1 h/wk); cut replies from
19.3/day to at most 1/day, launch windows only (1.2 h/wk); publish the video
back-catalogue on a fixed schedule and measure it for the first time (1 h/wk).

**Kill list:** the 19.3 automated comments/day; the daily five-platform draft
factory; LinkedIn, Discord and Dev.to as channels; Reddit as primary; X as
"primary channel"; "install the dashboard" as the mobile CTA; producing new
videos before the 31 are published; treating the current engagement logs as
evidence.

## local-llama

**Headline:** Before he posts anything to r/LocalLLaMA he has to rename the
metric his own code calls "tok/s" (output tokens divided by whole-session wall
clock, tool calls and idle included), because the first knowledgeable commenter
will catch it; once renamed, the post that community will upvote is not
"electricity cost of a local model" (already done twice by Towards Data Science)
but "I ran the same task under six harnesses on the same local model and the
harness burned more tokens than the model".

**Findings**

1. His shipped "tok/s" is not the tok/s this community means, and the UI labels it
   "Measured". `backend/insights.py::tok_per_sec_from_duration` (line 82) docstring
   says outright it is "a lower bound on pure-decode speed"; fed from
   `backend/main.py:2283`; rendered by `LocalInferenceCard.tsx:20` as "Measured"
   and `LocalPowerInsights.tsx:271` as "tok/s".
2. Watt numbers are GPU-die draw or a chip-tier guess.
   `backend/power_meter.py::_nvidia_smi_watts()` queries `power.draw` (GPU only)
   and returns `confidence="measured"`; line 106 states there is no root-free way
   to measure watts on Apple Silicon. This community measures wall power with a
   $25 meter.
3. "What does a local LLM cost in electricity per million tokens" is already
   answered content (two Towards Data Science pieces, plus
   llmconfigurator.com/guides/llm-electricity-cost).
4. The unpublished thing is harness token overhead on identical work: same task,
   same local model, six harnesses, with total tokens, wall clock and watt-hours
   per harness. That table exists in his logs and nobody else's.
5. The difference between an upvoted post and the banned behaviour is structural,
   not tonal: he owns the post, the data is a markdown table in the body, method
   and caveats stated first, tool link once at the bottom.
6. Post #1 should carry no link to tokentelemetry.com. Link the repo.
7. He cannot post from a standing start: r/LocalLLaMA history is mean 0.76 with
   negatives, on banned accounts.

**Recommendations:** rename the throughput metric everywhere before any post
(2-3h one-time); write and post the harness-overhead study as a self-post (6-8h
one-time); a follow-up on context refill per tool call plus a wall-vs-nvidia-smi
power delta from a smart plug (4-5h); cap hand-written comments at 5/week across
all platforms (2 h/wk); flip Threads from replies to original posts in the
proven shape (2 h/wk); instrument the install before post #1 (1-2h one-time).

**Kill list:** all automated Reddit commenting; shipping "tok/s" with the hint
"Measured"; unqualified watt figures; leading with electricity cost per million
tokens; sending mobile-heavy sources to tokentelemetry.com; treating
`01-platform-strategy.md` and `02-weekly-content-calendar.md` as live; producing
anything further without publishing it.

## harness-hopper

**Headline:** You are not short of ideas, reach, or production capacity. You are
short of a publish step, and the one thing my cohort would follow you for
(observed dollars per finished task across the harnesses you really use) has
never been published once.

**Findings**

1. The bottleneck is the publish step. `marketing/drafts/` holds 23 daily drafts,
   6 feature-Friday files and 7 weekly digests dated inside the measurement
   window, several marked post-ready ("Variant B - post-ready, no placeholder"),
   against zero owned content shipped. Same shape as 40 videos produced and 9
   published.
2. Every published dollars-per-task number in this market is synthetic, derived
   from benchmark tasks on a rented harness (morphllm, firecrawl,
   techjacksolutions). Benchmarks have converged while costs diverged by roughly
   an order of magnitude, making cost-per-task the primary differentiator now.
3. In his cohort a like is what a good one-off take earns. A follow requires a
   recurring number you can look up next week and argue with.
4. Draft platform coverage points away from the only channel that works: X 25
   files, LinkedIn 22, Reddit 22, Discord 19, Threads 17 (passing mentions),
   Dev.to 11, Instagram 0, YouTube 0. LinkedIn, Discord and Dev.to appear nowhere
   in referrer data.
5. Threads is a lottery and the only variable he controls is event timing. Top 10
   placements are 58% of all views; 43% of tracked placements got under 100.
6. The 450,000 figure has two factors and he is only attacking the impression
   side. The conversion side is a physics problem, not a copy problem.
7. Measurement is broken in three places at once, so no plan is currently
   verifiable: GA4 key events 0, empty `performance_score` table, zero UTMs, the
   Threads likes scrape bug.

**Recommendations:** a weekly cost logbook as a versioned repo page
`docs/logbook/YYYY-WW.md` announced with one X and one Threads post, framed as a
logbook and never a leaderboard (1.5 h/wk); event-gated original Threads posts,
hard cap 4/month (0.5 h/wk); a 3-hour one-time build fixing the mobile CTA plus
UTMs plus one GA4 install-proxy event; a 4-hour one-time teardown of where 35
agents store their logs, submitted once to HN; ship the video back-catalog one
per week and record views this time (0.5 h/wk).

**Kill list:** the daily multi-platform drafting ritual; automated commenting at
volume; LinkedIn, Discord and Dev.to as content targets; calling X primary;
Reddit as highest-converting; new video production; Threads likes as a metric;
Threads posting on non-launch days.

## eng-manager

**Headline:** His content is invisible to my segment because he has published
676 replies and zero artifacts, and the one artifact that would reach me does
not exist anywhere: a dated, methodology-stated, cross-agent cost-per-finished-task
report built from his own real telemetry.

**Findings**

1. All 676 measured items are replies. A reply is not an artifact with a title, a
   date and a methodology line, so there is nothing to forward.
2. LinkedIn, the only channel that reaches this segment, sits below github.com's
   10 referrals in his own 30d table.
3. GA4 key events = 0, so he cannot say how many people install his tool. That is
   the credibility hole, not the traffic. Clarity Smart events show only Download
   5 and Outbound click 9 in 30d.
4. The cost question an EM has is different: cost per merged PR and its trend, the
   distribution across 12 engineers, substitution evidence, showback per team,
   commitment risk. His top Threads placement, "Why pay $385k when Cursor is
   $20/mo", was already a substitution argument.
5. No public cross-agent dollars-per-merged-PR benchmark exists. Vendors will not
   publish it and Langfuse/LangSmith data is per-customer.
6. curl-pipe-bash stops an EM cold, yet the properties that clear a security
   review (local only, no cloud account, logs never leave the machine, MIT, no
   SDK) are ones he already has and never states as review criteria.
7. He will not watch a video about agent cost, and no video reaches his desk.
8. 61% mobile against a desktop CLI is a segment mismatch, not a landing-page bug.

**Recommendations:** a monthly "Agent Cost Report" as a permanent dated page
(`/reports/2026-08`) with fixed sections and a methodology block, full text
pasted natively into LinkedIn on publish day, raw numbers committed as CSV (1.5
h/wk); original first-person LinkedIn text twice a week written for someone who
signs the invoice (1.5 h/wk); a 4-hour one-time `/security` page plus
`SECURITY-REVIEW.md` written for a reviewer, in the same build as the GA4 key
events; cut replies to at most 2/day on launch days only (1 h/wk); on report
publish day post the chart to Threads and X linking the report page, not the
homepage (0.5 h/wk).

**Kill list:** the automated commenting loop; X as primary; Reddit as
highest-converting; views as the metric; shipping the 31 unpublished videos as a
growth move; publishing any number without a date, sample size and stated
method; aiming any content at the homepage.

---

# Phase 2: platform analysts

## threads

**Headline:** Threads replies are structurally handicapped in the For You feed
and Meta is actively cutting the unconnected reach his whole engine depends on,
so the fix is to publish the exact content shape that already earned him 145K
views as original posts on his own account at 19:00 IST, and cut in-thread
replies from 8.7/day to 3/day.

**Findings**

1. Replies do appear standalone in For You but with reduced algorithmic
   visibility. His 145K-view reply is what the shape achieves while carrying a
   handicap.
2. Mosseri has said Threads is rebalancing toward followed accounts: unconnected
   reach down, connected reach up. All 789K of his views came from unconnected
   reach. Ads went global January 2026.
3. Published benchmark is 2 to 5 new followers per 1,000 views. 789,522 views
   should have produced 1,580 to 3,948 followers. Reply-borrowed views do not
   behave that way. Make followers per 1,000 views the primary KPI.
4. Link-in-post suppression is not real as of mid-2026. Mosseri: Threads does not
   downrank links and link ranking has been fixed. The link-in-first-reply
   workaround is obsolete. Threads has tracked link clicks natively since May
   2025.
5. Topic tags are the unused discovery surface. Threads' own guidance says posts
   with a topic get more views. All 306 of his actions were replies, which carry
   no topic tag.
6. 19:00 IST is the correct slot, because he can staff the 30-to-90-minute
   reply-velocity window (09:30 ET, 15:30 CET). The objectively bigger US evening
   slot is 04:30-06:30 IST and he cannot be awake for it. Presence beats peak.
   Skip Saturday.
7. Threads shipped indented nested replies in April 2026, burying replies deeper
   than when the campaign started.
8. His engine is 10 lucky tickets, not a system: top 10 = 58% of views, 43% of
   placements under 100 views.

**Recommendations:** one original post per day Tuesday to Friday at 19:00 IST
with one topic tag and the link in the body (1.5 h/wk); staff the reply-velocity
window on his own post for 60 to 90 minutes (1.75 h/wk); cut in-thread replies
to a hard max of 3/day, model-news only, thread under 2 hours old (0.9 h/wk); a
3-hour one-time mobile CTA fix (star the repo, copy the command, email it to
yourself); a 45-minute one-time measurement setup (professional account, UTMs,
GA4 key events) plus a 15-minute weekly read.

**Kill list:** 8.7 automated Threads comments/day; raw views as the KPI;
links in a first reply or only in bio; publishing zero original posts; replying
to non-news threads; posting on Saturday; scheduling into a slot he cannot
staff; `01-platform-strategy.md` as current; the "2-3 helpful comments/day"
Reddit line in `02-weekly-content-calendar.md`.

## linkedin

**Headline:** LinkedIn earns a real slot because its clicks land on desktop
machines that can actually run his installer and its top format is the
dashboard-numbers carousel he already produces, while X is worth un-pausing only
as a cheap derivative bookmark channel behind a hard four-week kill test.

**Findings**

1. 69.16% of linkedin.com browser visits are desktop, against his measured 61%
   mobile. Judge LinkedIn on install-page views per session, not referral volume.
2. LinkedIn's highest-reach format is a native PDF document carousel: 6.60-7.00%
   engagement vs about 2% for text-only, and personal-profile carousels outperform
   company-page carousels by 63% (Socialinsider 2026, 1.3M posts).
3. Any external link destroys the post: 60% average reach penalty, and the
   link-in-first-comment workaround is detected, costing up to 80% of comment
   visibility.
4. The May 2026 update penalises posts with average dwell under ten seconds and
   flags generic AI-sounding content with 94% accuracy. Personal-anecdote posts
   get about 4x the dwell. Daily posting with a repeated structure gets throttled
   inside two weeks. His standing writing rule is a ranking advantage here.
5. LinkedIn assigns profile-level Topic DNA and suppresses off-niche posts. His
   profile has no established agent-harness niche.
6. X in 2026 rewards the opposite of volume commenting: bookmarks weighted around
   +10 against +0.5 for a like, and long substantive replies are explicitly
   rewarded.
7. X cannot be a traffic channel at any effort level: non-Premium link posts have
   had near-zero median engagement since March 2026, link posts suppressed up to
   80%, X about 0.4% of publisher referral traffic and falling. Premium at
   $8/month is the entry fee for visibility.
8. `01-platform-strategy.md` prescribes 1 post/day plus 3-5 replies/day on X, that
   is 28-42 outbound replies a week, the same shape that got the Reddit accounts
   banned.

**Recommendations:** a weekly LinkedIn document carousel from his own telemetry,
personal profile, no links anywhere (1.25 h/wk); one weekly LinkedIn text post
teaching one technique from his working day (0.5 h/wk); a 1.5-hour one-time
setup (headline and About rewrite for Topic DNA, Featured link with UTM, GA4 key
event, delete the falsified X cadence from the strategy doc); a 2-hour one-time
carousel renderer, built only after two carousels have been hand-made; un-pause X
in strictly derivative form behind a kill test, Premium first, max 3 items/week
on real news days (0.75 h/wk).

**Kill list:** calling X primary and the 1-post-plus-3-5-replies cadence;
external links in LinkedIn posts and the first-comment workaround; posting to X
while non-Premium; treating either platform as click-volume; repurposing
non-existent X threads; milestone posts as a LinkedIn staple; pointing
agent-browser at LinkedIn commenting; shipping LinkedIn text that reads as
generated.

## longform

**Headline:** He has never used his Hacker News slot and is sitting on a
genuinely unique measured dataset (1,264 sessions, 15 harnesses, $4,381.67,
393.6M tokens, 16 months) while every page ranking for his terms fakes
cost-per-task from list prices, so the right move is a small number of
first-person data posts canonical on his own domain, led by that dataset, with
HN entered as an article rather than as the seventh token dashboard to flop
there.

**Findings**

1. His HN slot is unused (Algolia: zero results for "tokentelemetry" and
   "VasiHemanth"), and the Show HN graveyard for his category is brutal: Claumon
   7 pts, Tokens 4 Breakfast 5, Llmtop 5, WakaTime AI Metrics 3, Agentic Metric 2,
   ObservAgent 2, Tokemon 1. Median Show HN is 2 points. A cost-analysis blog post
   ("No, it doesn't cost Anthropic $5k per Claude Code user") hit 480; CodeBurn hit
   112 as a plain github.com link.
2. He owns the dataset nobody has: 1,264 sessions, 15 harnesses, 47 models,
   $4,381.67, 393.6M tokens, 2025-04-05 to 2026-07-29. Measured USD per million
   tokens ranges 60.34 (Claude Code) to 0.30 (Gemini CLI). Codex burned 127.8M
   tokens for $61.41 while Claude Code burned 69.6M for $4,198.41. The honest
   thesis is that the per-harness dollar number is mostly a billing-mode artifact.
3. That central claim is not yet queryable: `billing_mode` is NULL for all 1,264
   rows, 503 sessions (40%) carry cost=0 covering 8.3M unpriced tokens, and
   per-agent session counts are unbalanced enough to mislead (antigravity 343
   sessions for $54, claude 341 for $4,198).
4. `README.md` and `website/public/llms.txt` both claim 10 coding agents plus
   Hermes; grep for "35+" in the README returns zero matches. Both are surfaces
   answer engines quote.
5. llms.txt is not a channel: 408 requests out of 500M+ AI bot visits, Google
   confirms no support, 1 of the top-50 AI-cited domains has one, 8 of 9 sites saw
   no traffic change.
6. dev.to is the only syndication target with measured AI-engine traffic (51.74%
   Google organic, 35K ChatGPT, 20K Perplexity, 15K Gemini) and its `canonical_url`
   still points the signal home. Drop Hashnode and Medium.
7. Show HN slot timing: Monday 00:00 UTC is strongest (10.8% chance of 50+) but
   that is 05:30 IST; Sunday 02:00 UTC (9.8%) is Sunday 07:30 IST and staffable.
   Front page is decided in the first 60 to 90 minutes; 92% of star-getting is
   over in 48 hours; roughly 1.4 stars per upvote.
8. A new domain can rank on a narrow topic now (February 2026 Discover update
   removed domain-level authority evaluation), but human-written content generates
   5.4x the traffic of AI-generated, and the June 2026 spam update judges networks.

**Recommendations:** five pieces in priority order, canonical on
tokentelemetry.com/blog: (1) the flagship "What 1,264 AI coding sessions across
15 harnesses actually cost me", (2) "How to track Claude Code costs without an
SDK" for the head term, (3) "Cost per finished task is the right metric. Here is
why nobody's numbers are real" as the HN submission, (4) "Where each coding
agent writes its logs" as an extractable reference, (5) the
TokenTelemetry/Langfuse/LangSmith/ccusage comparison page. One piece every 2 to
3 weeks, 2.5 h/wk average. Plus: a 3-hour one-time `/blog` route and GSC
verification; the HN submission at Sunday 07:30 IST with 07:30-09:00 blocked; a
1-hour README and llms.txt fact fix plus the `billing_mode` backend fix; 2 hours
of one-time outreach to the six pages already ranking for his terms; and making
the flagship recur quarterly on the same URL with a dated changelog.

**Kill list:** "Publish weekly article"; Hashnode and Medium; spending the Show
HN slot on the dashboard; llms.txt as a growth investment; Reddit as the
AI-citation play; the strategy docs as operating plans; dev.to without
`canonical_url`; any per-harness average-cost-per-session ranking; a staged
same-tasks-across-10-harnesses benchmark as the flagship.

## video

**Headline:** His video pipeline is not unproven, it is measured and it failed:
32 live Shorts have produced 2,051 lifetime views and 13 subscribers, which is
40x worse per unit of work than a single Threads reply, so video should move to
native Threads video on hot model-news threads with YouTube demoted from
distribution surface to biweekly searchable destination, shot as raw screen
capture in his own voice.

**Findings**

1. The brief's video paragraph was computed from the TEST database. The real
   published catalog is 3.5x bigger: `prod_tracker.sqlite` has 61 videos and 139
   posting rows, 36 YouTube / 33 Instagram / 36 Facebook successes across 20
   publishing days from 2026-02-26 to 2026-04-06, then a hard stop until one
   long-form on 2026-07-28. The brief's claim that no performance data was ever
   recorded stays true.
2. Measured for the first time: @hemanth_with_ai has 13 subscribers and 32 live
   Shorts totalling 2,051 lifetime views. Mean 64.1, median 34.5, min 4, max 289.
   25 of 32 under 100 views. View-to-subscriber 0.63%. 12 of the 36 recorded
   Shorts are gone. Data at
   `marketing/distribution-2026-07/youtube-measured-2026-07-30.csv`. (First scrape
   pass was contaminated by neighbouring Shorts' metadata; the CSV is the
   corrected id-scoped pass.)
3. Per unit of work a Threads reply delivered 2,580 views and a published Short
   delivered 64.1, which is 40.3x. The entire 5-month YouTube history is worth
   0.34 site clicks at his measured clickthrough.
4. The brief's inference that 21 of 40 are already GenAI so the catalog is close
   to the new subject is wrong in substance. Titles are cloud-architect interview
   prep for job seekers on GCP managed services. Not one of the 61 mentions Claude
   Code, Cursor, Codex, token cost, or any coding-agent harness.
5. YouTube's inauthentic-content policy applies to monetization eligibility only,
   not reach, and explicitly permits a series where each video has a distinct
   focus. So the old catalog is a waste of time, not a strike risk, and a
   per-episode-varied series is safe.
6. Threads native video autoplays muted and ranks on completion rate; useful range
   15 to 60 seconds. The payload must be legible with no sound.
7. All 789,522 Threads views came from replying into other people's already-viral
   threads. Moving purely to original posts abandons the mechanism that produced
   the number, so publish each video file twice: once as a reply on one hot thread,
   once as an original post.
8. He should record his own voice, for authority reasons rather than any algorithm
   penalty. A synthetic voice narrating his own first-person data undermines the
   only thing that makes it credible.

**Recommendations:** Threads native video with dual placement, 20-40s raw screen
capture, no voiceover, 2 per week (45 min/wk); one YouTube long-form series
"Cost Per Finished Task", 8-12 min, his own voice, biweekly (~55 min/wk, costed
high on purpose); a 70-minute one-time measurement build
(`scripts/youtube_stats.js` backfilling all 33 live videos, plus a Studio read of
average view duration and a channel standing check); unlist all 32 interview-prep
Shorts and repoint the channel (15 min one-time); cross-post the strongest 30
seconds of each episode as X native video and as a Shorts trailer (~5 min/wk).

**Kill list:** reviving the 31 unshipped renders; the 35-second synthetic-voice
Remotion Shorts format; Remotion diagram animation as the default visual;
Instagram Reels; Facebook video; LinkedIn as a video surface; batch-publishing
near-duplicates; publishing any video without recording its view count; a weekly
long-form cadence.

---

# Phase 3: asset architects

## video-pipeline

**Headline:** The pipeline was never the bottleneck: renders work in 28s and
carousels in 6.6s, but the documented publish command (`node scripts/post.js`)
exits 0 and publishes nothing, the YouTube refresh token died the exact day
publishing stopped, and the carousel entry point dies on a discontinued Gemini
CLI.

**Findings**

1. The documented publish step is a silent no-op. `node scripts/post.js --number
   101 --platforms youtube,meta` exits 0 with zero output and writes no `postings`
   row; `scripts/post.js` only ever exported `postToAllPlatforms`. The real
   publisher is `node upload.js`. The phantom command appeared at `CLAUDE.md:16,
   :28, :297`, `AGENTS.md:17`, `GEMINI.md:15, :27, :109`, and
   `.claude/skills/generate-video/SKILL.md:87`. The project's own wiki caught it at
   `docs/wiki/subsystems/social-posting.md:48-53` and nothing was fixed. Now fixed:
   all 8 references corrected and `scripts/post.js` errors instead of pretending
   to work.
2. A second silent failure hit the same week: the YouTube OAuth refresh token is
   dead (`invalid_grant`), access token expired 2026-04-06T11:06:47, the exact date
   of the last successful posting row. Meta is healthy (token valid, expires never,
   `instagram_content_publish` and `pages_manage_posts` granted).
3. 56 finished videos are unpublished and 55 have a rendered mp4 on disk; 31 are
   on-topic for the new subject. `content_tracker.sqlite` is the TEST database;
   `prod_tracker.sqlite` holds 61 videos and 39 distinct SUCCESS postings.
4. The carousel renderer works but its entry point is hard-broken:
   `carousel_pipeline.js` dies at step 1 with `IneligibleTierError` from the
   discontinued Gemini CLI. Calling `renderCarousel()` directly with a
   hand-written `slides.json` about coding-agent costs produced 3 clean slides at
   1080x1080 in 6,639ms. A `list` slide with 3 items leaves the bottom half empty;
   author 5-6 items or use `card`.
5. There is no Threads publisher anywhere in the repo. `scripts/carousel_post.js`
   handles Instagram and Facebook only.
6. Performance is not merely unrecorded, it is unrepresentable: neither
   `postings` table has a metrics column, and `pipeline.db semantic_store.performance_score`
   has 0 rows.
7. The local Qwen TTS is an asset on cost (15.4s of audio in 10.2s wall clock,
   2.14x realtime, deterministic under a fixed seed) and a liability for the
   personal-authority track. `scripts/generate_voice.py:96` hardcodes
   "Follow for daily cloud architecture breakdowns." into every video.
8. Rendering is fully reusable (900 frames in 28 seconds on Remotion 4.0.428) and
   the GCP-era identity is five named strings plus a Meta page literally named "AI
   Cloud Architect". `domains/coding-agents.md` and `domains/token-economics.md`
   were written and wired into CLAUDE.md.

**Recommendations:** re-auth YouTube once (10 min) then publish the 31 on-topic
backlog videos via `node upload.js` (0.75 h/wk); a 3-hour one-time build
stripping the dead LLM head off the carousel path plus a carousel SKILL.md and a
`threads` caption key; an owned model-news carousel on Threads within 24 hours of
any announcement, max 2/week (1.5 h/wk); cross-post each carousel to Instagram
and Facebook and rename the Meta page (0.25 h/wk plus 0.5h one-time string
fixes); a 2.5-hour one-time build making outcomes recordable (`ALTER TABLE
postings ADD COLUMN views`, plus `scripts/fetch_metrics.js`); stop automated
comments and cap replies at 3/week (0.5 h/wk).

**Kill list:** 19.3 automated comments/day; running `node scripts/post.js`;
rendering new videos while 56 sit unpublished; `carousel_pipeline.js` as an entry
point; Reddit as primary and X as primary; shipping anything under the "AI Cloud
Architect" identity; the Qwen TTS narrator on anything positioned as him
speaking about what he measured; publishing without recording outcomes.

## agent-browser

**Headline:** The bridge separates cleanly and should be published narrowly for
citation rather than adoption, but the highest-value asset in this repo is the
fully instrumented record of a distribution loop whose own metrics pipeline was
deleting the bad news.

**Findings**

1. The bridge is mechanically separable at zero engineering cost. `server/index.js`
   is 11 generic tools with no import of any social file. A clean tool needs
   `server/index.js`, `extension/`, `server/package.json` and a new README.
2. The obvious value proposition is commoditized (chrome-devtools-mcp
   `--autoConnect` in Chrome M144, mcp-chrome, real-browser-mcp). The one thing not
   found elsewhere is `extension/background.js`'s `agentVisualFeedback`: a green
   pill with a per-tab task label, a viewport border glow and a click ripple, so a
   human can see a bot is driving. That is an honesty primitive, not a capability.
3. The worst artifact is one line of instruction:
   `skills/tt-social-post/SKILL.md:234` reads "**Never** append (disclosure: I
   build it) ...". `AGENTS.md:43` repeats it. Early CSV rows still carry
   "(disclosure: I build it)"; rows from 2026-07-09 onward do not, so the log shows
   the disclosure being deliberately removed partway through.
4. Nothing is publicly exposed yet, but a scrub commit will not work. The remote is
   private, 0 stars, and `origin/master` already contains
   `server/posted_comments.csv` with 115 rows; local HEAD has 294 and the working
   tree 694. Tracked source enumerates 380 third-party Threads post IDs and 311
   third-party Reddit post URLs, plus real handles in `parallel_post.js` sample
   JOBS. Publish as a NEW repo with fresh history.
5. He diagnosed his own ban in a code comment and shipped the fix too late.
   `server/author_cooldown.js` (dated 23 Jul, after the bans) opens: the DONE sets
   stop commenting on the same post twice and do nothing about replying to the
   same person repeatedly, so an unattended loop converges on high-frequency
   accounts and "several replies from one handle in a day reads as a bot".
6. His measurement pipeline was deleting the bad news. `server/score_feedback.js`
   records that the parser used `(\d+)`, which cannot match a leading minus, so
   every downvoted comment was stored with an empty score. `server/doc_links.js`
   records a parallel blindness: no bare price figure or "per million" in
   `DOC_MAP`, so the two most on-topic posts of a run matched nothing.
7. `setup.sh` lines 13-18 and 97-106 symlink every skill into
   `$HOME/.claude/skills`, `$HOME/.grok/skills`, `$HOME/.codex/skills`,
   `$HOME/.cursor/skills`, `$HOME/.agents/skills`, so anyone who runs setup gets a
   spam workflow available in every project.
8. His own compiled wiki is falsified on the most sensitive point:
   `docs/wiki/conventions/posting-safety.md` asserts "Nothing posts without
   explicit user approval" while `README.md:3`, `README.md:73`, `AGENTS.md:43` and
   `INSTALL.md:130` all state there is no approval gate. The page is pinned to a
   SHA 9 commits back.

**Recommendations:** one long-form postmortem on his own domain built from the
three engineering findings then the numbers unhedged then his own SKILL.md:234
quoted against himself (6-8h one-time); stop replying and start posting, 2
original Threads posts plus 1 X thread per week, event-timed, zero Reddit (90
min/wk); a NEW public repo with fresh history containing only the bridge, README
leading with the visible automation indicator and the fail-closed env parsing,
threat model in section two, three legitimate uses in section three (4-5h
one-time); a hand-picked reply budget of at most 3/week with mandatory
disclosure and author cooldown enforced (20 min/wk); fix measurement first: UTMs,
one GA4 key event on the install-page copy-command click, and a mobile-aware note
on the install path (2h one-time).

**Kill list:** the auto-post loop entirely; the no-disclosure instruction, not
just the practice; `server/posted_comments.csv` tracked in git; `setup.sh`
installing skills user-wide; the repo name and its current description; the
strategy docs as live; citing `docs/wiki/` pages; the hardcoded `MY_HANDLE` and
Reddit account defaults.

## telemetry-stories

**Headline:** Hemanth already holds the only cross-harness measured agent-cost
dataset in this niche (1,264 sessions, 15 harnesses, $5,908 of real spend, 7.78
billion cache-read tokens), but he cannot publish a dollar figure until he fixes
three integrity holes in his own pricing path that understate his headline total
by 25.8%.

**Findings**

1. His headline cost understates real spend by 25.8%. `sessions.cost` sums to
   $4,381.67. `claude-opus-5` is absent from `PRICING`, so 7 sessions carrying
   1,173,097,601 cache-read tokens and 1,261,955 output tokens were billed at
   $0.0514 total; repriced at the Opus tier already in his table those sessions are
   $618.12, a $618.07 hole. Separately, subagent spend of $908.22 across 796 spawns
   is computed and displayed in the delegation panel (`main.py:6727`,
   `analytics/page.tsx:713`) but never added to the headline total. Corrected total:
   $5,907.96.
2. The bill is a cache-read bill: fresh input $126.13 (2.2%), output $1,206.56
   (21.5%), cache reads $4,282.71 (76.3%). Cache reads are 97.66% of all tokens
   read (7,783,585,057 vs 186,400,698). Cache share of read tokens by harness:
   Claude Code 99.95%, Codex 94.79%, Hermes 85.83%, pi 85.27%, Copilot 54.34%,
   Vibe 51.31%, Gemini CLI 46.01%, OpenCode 43.73%, Antigravity 39.92%.
3. Dollars per finished task is computable today, and the alarming 31x
   month-over-month swing is a denominator artifact. Naive: June $197.49 / 20
   merged PRs = $9.87; July $2,470.32 / 8 = $308.79. Time-aligned: June $192.79 /
   20 = $9.64, Jul 1-10 $202.17 / 8 = $25.27, a 2.6x rise. Blended output price
   paid rose from $77.03 to $138.05 per 1M output tokens, which accounts for most
   of it.
4. $2,153.01 of agent spend across 43 sessions and 14,825,138 output tokens sits
   on branches that never merged, which is 87% of July's TokenTelemetry spend.
5. The local-model power and CO2 story has effectively no data: 3 local sessions
   out of 1,264, 1,080 output tokens, $0.0000000078 of electricity, `tok_per_sec`
   NULL in 1,264 of 1,264 rows so `resolve_tok_per_sec` falls back to 30 tok/s
   everywhere, and `power.json` hand-set at 22W / $0.20 per kWh.
6. Subagent economics are measurable per type but only for Claude Code: across 796
   spawns, workflow-subagent 430 spawns / $527.03 ($1.23 each), general-purpose 298
   / $336.76 ($1.13), Explore 30 / $22.00 ($0.73), analytics-architect 4 / $7.26,
   telemetry-implementer 1 / $3.83. Every other harness returns
   `tokens_recorded: false`.
7. Tool-call and MCP behaviour is not durable: `tool_counts` is absent from
   `history_store.py _ECOSYSTEM_KEYS`, and Claude Code prunes transcripts at 30
   days. Durable: 290 archived Claude transcripts totalling 332,926,345 bytes,
   plus `mcp_usage` (6,773 claude-in-chrome calls) and `skills_used` (loop 181,
   tt-threads-post 95, goal 43).
8. The n=1 boundary is sharper than the totals suggest: 92% of spend is in June
   and July 2026, two harnesses carry 96%, and the 8 most expensive Claude sessions
   are $2,528 or 57.7% of the total. The `project` field is the working directory,
   so marketing and docs work inside a repo path counts as that repo's spend.

**Recommendations:** a monthly "Agent Cost Report" at `tokentelemetry.com/report`
with six fixed sections and a 12-story pool ordered by news-hook availability (6h
one-time build, then 3h/month); a metric specification page at
`/docs/metrics/dollars-per-finished-task` settling six definitional questions
plus `tokentelemetry report --metric dpft` as the reference implementation (4h +
4h one-time); a one-time integrity build before the first report (add the 11
missing models with cache rates and a regression test, surface `delegated_cost`,
add `tool_counts` to `_ECOSYSTEM_KEYS` and backfill from the 290 archived
transcripts, roughly 6h); replace automated replies with original model-launch
posts on Threads and X, replies capped at 2/day hand-picked (3 h/wk); ship
`tokentelemetry report` so readers can reproduce the report on their own machine
(6h one-time); one video per month tied to the report, view counts recorded from
video 1 (0.4 h/wk).

**Kill list:** `tt-threads-post` (95 invocations), `tt-social-post` (35),
`tt-hot-topics-post` (28); replies as the primary channel; treating tracked
engagement numbers as ground truth for anything except Threads views; citing the
strategy docs; any local-model power, energy or CO2 data story; publishing any
dollar figure before the pricing gap and delegation bucket are fixed; clearing
the 31 unpublished videos as a batch.

---

# Phase 4: where the agents agreed and disagreed

## Unanimous or near-unanimous (10 or 11 of 11)

- Stop all automated commenting. Volume only decreases. Every agent said this.
- Zero owned content is the actual bottleneck, not reach.
- The winning shape is a hot model-news event plus the dollars-per-finished-task
  reframe plus his own measured number.
- Fix instrumentation first: GA4 key events (0 today), UTMs (none today), and a
  measured install proxy. Nothing else is falsifiable without it.
- The strategy docs are falsified on Threads, Reddit and X and must be archived.
- The homepage is the wrong destination for anything; send traffic to the artifact.
- 61% mobile against a desktop CLI is a physics problem, and the mobile CTA has to
  become something a phone can do.

## Real disagreements, and how the plan resolved them

| Question | Positions | Resolution in the plan |
|---|---|---|
| Engine cadence | Weekly logbook (harness-hopper) vs monthly report (eng-manager, telemetry-stories) vs every 2-3 weeks (longform, which kills weekly as arithmetically impossible) | Both: monthly report is the primary owned format, weekly logbook is its sub-30-minute feeder, because the documented failure is the publish step. Section 4. |
| LinkedIn | Kill it (limit-hitter, harness-hopper: absent from referrer data) vs primary authority channel (eng-manager, linkedin: 69% desktop) | Keep, reduced: a repurposing destination for the report, ~35 min/month, with a kill gate. No referrals from a channel with zero published posts is not evidence. Section 3 and 5. |
| Video backlog | Publish the 31 on-topic videos (limit-hitter, harness-hopper, video-pipeline, telemetry-stories) vs the catalog is off-subject and the format is a measured failure (video) | Side with `video`. Do not publish. Unlist the old Shorts. This is the plan's one explicit override of a majority. Section 5. |
| Threads: replies or originals | Cut replies to 3/day and go original (threads) vs keep the hot-thread piggyback because that is what produced the 789K (video) | Original posts are the channel; the reply tail survives inside the 5-per-week global ceiling and only on live news. Sections 5 and 7. |
| X | Restart as an authority channel (agent-browser) vs derivative echo behind a kill gate (linkedin) vs park it (limit-hitter) | Derivative echo, $8 Premium, no separate authorship, dropped 2026-08-31 if nothing clears 5,000 impressions or 10 bookmarks. Section 5. |
| Reddit re-entry | 3 weeks of hand-written comments then post (local-llama) vs burned surface (eng-manager) vs closed as the AI-citation play (longform) | Closed 90 days. One appeal per banned account through the official route. No new accounts, because ban evasion forecloses Reddit permanently. Section 7. |
| HN entry shape | Show HN the tool vs submit an article as a normal story (longform) | Article as a normal story, once, Sunday 07:30 IST. Hold the Show HN slot. Section 9. |
| Local power story | An anchor data story (earlier framing) vs no data behind it (local-llama, telemetry-stories) | Killed as a data story. One methodology post at most. Section 11. |
| Publishing dollar figures | Publish the dataset now (longform) vs gated on integrity fixes (telemetry-stories, local-llama) | Gated. Week 1 fixes pricing, delegation and metric labels, and 08-10 independently recomputes the total before anything ships. Sections 8 and 11. |

---

# Critique log, revision of 2026-07-30

Two adversarial critics reviewed the first draft of `00-DISTRIBUTION-PLAN.md`.
Critic 1 attacked feasibility and ban risk (20 findings), Critic 2 attacked
novelty and authority (15 findings). I re-verified every code-level claim on this
machine before acting on it. Verdicts below.

## Verified independently before acting

| Claim | Check | Result |
|---|---|---|
| The GA4 conversion events already ship | `website/src/lib/track.ts`, `Hero.tsx:23`, `FinalCTA.tsx:16`, `SiteHeader.tsx:46,54` | Confirmed. `copy_install_command`, `click_github`, `click_install`, `click_nav`, `copy_plugin_command`, `faq_open`, `page_view` all live. The plan's three invented names were wrong. |
| Analytics is consent-gated | `Analytics.tsx:52`, `analyticsEnabled = consent === "granted" && !local`, `localStorage` key `tt-consent` | Confirmed. Every GA4 figure is a consented subset. |
| The homepage understates the agent count | `Hero.tsx:48` renders an "11 agents" chip, `:66` says "& 7 more", `src/data/agents.ts` has 11 entries, `llms.txt:25` says 10 | Confirmed, and the plan had missed the homepage entirely. Backend `main.py` yields 12 agent ids, so "35+" is not reproducible from any surface. |
| No author surface exists | `ls website/src/app/` | Confirmed: `api docs privacy resources` only. No about, author or blog route. |
| The site is a static export on GitHub Pages | `next.config.ts` `output: "export"`; `dig tokentelemetry.com` returns 185.199.108-111.153 | Confirmed. No server, so no mail path, and no Cloudflare zone, so no Web Analytics beacon without a DNS move. |
| The weekly digest is silently dead | `logs/weekly-digest.err` holds 3x `Operation not permitted`; `digests/` holds only `2026-07-12.md`; exec bit set | Confirmed. macOS TCC denies launchd-spawned bash access to `~/Documents`. Third silent failure in the stack. |
| Posting skills are live symlinks | `ls -la ~/.claude/skills` shows `tt-social-post`, `tt-threads-post`, `tt-hot-topics-post` pointing at `quirky-borg/skills/` | Confirmed across the user-level directories. |
| The star count was stale | `gh api repos/VasiHemanth/tokentelemetry` | 291 stars, 41 forks. Both 154 and 283 were wrong. Reconciliation paragraph deleted, figure written in. |

## Fixed in the plan

| Critic | Finding | What changed |
|---|---|---|
| 1.1, 2.1, 2.9 | Measurement runs through consent-gated GA4; Day 1 invented event names | Day 1 is now config only, no code: the three shipped events marked key in the GA4 UI, plus a new `consent_choice`. Every GA4 figure is labelled a lower bound in §1 and in the scorecard's source column. |
| 1.2 | No install-page event exists | One new event, `install_page_view`, on the docs install page. Renaming shipped events is on the kill list. |
| 1.3, 1.13 | Daily milestones impossible at 14 sessions/day; targets set against Unknown baselines | Scorecard is weekly totals. `copy_install_command` target is 3 consecutive non-zero weeks. Threads follow-rate target is set from the median of the first two posts. LinkedIn's week-4 question is impressions plus `utm_source=linkedin` sessions. |
| 1.4, 1.17 | Report #2 unscheduled; §5 and §9 totals irreconcilable; no slack | Min/day column deleted; §5 is per-week. §9 shows news-week 225 and quiet-week 90 summed line by line, plus the monthly 750-min arithmetic. Last two Fridays and last Saturday of each month reserved for report production. Fortnight cut to 10 working days with 4 declared slack days; post-publish days made relative. |
| 1.5 | `tok_per_sec` rename is a migration on user machines | Display string and docs only. Renaming the column or API field is on the kill list. |
| 1.6, 2.10, 2.11 | Headline percentages computed with the pricing the plan says is broken; contradictory averages | All exact percentages removed from the plan. The stop condition now covers every number in the report, not just the total. Day 2 runs `pricing_sync.py` and refreshes `pricing_data.json`. Dollars per finished task demoted from a mean to a distribution with n and top-session share. |
| 1.7, 2.10 | Cache-share ranking is the ranking the plan forbids | Published unsorted, with session count and task type beside each harness and an explicit "measures how I used it, not harness quality" line. Descending bar charts killed. The **ratio rule** in §4 states why cache share survives and cost per session dies. |
| 1.8, 2.8 | Ban-risk residue not covered; the rule already existed and was overridden | §7 now removes the *capability*: 15 symlinks, `~/.claude.json` entries, credentials, cookies, browser profiles, plus a `POSTING_DISABLED` hard exit. Inoperative gate 5 replaced with a 30-day per-handle rule and a greppable `marketing/replies.md`. Explicit line that original Threads posts are typed by hand in the app, no bridge, ever. Kill list forbids ever making the private posting repo public. |
| 1.9 | Every recurring job fails silently; a third live example | §12 diagnoses the TCC failure; §13 schedules the relocation, the logbook-absence check, and the Monday "did last week's artifacts exist" line. |
| 1.10 | Mobile email feature unimplementable on a static export | Replaced with a prefilled `mailto:` link. Email capture moved to the forks list with its real cost (provider, privacy edit, Turnstile). |
| 1.11 | Postmortem sequenced ahead of the appeals and possibly the employer | Appeals week 1 before anything publishes. Postmortem only after they resolve or after 2026-10-30. Kill list forbids submitting it to HN or LinkedIn. |
| 1.12 | The 450,000-to-25,000 improvement is an instrumentation artifact | 450,000 frozen as "unmeasured, not comparable". First post-instrumentation month is the real baseline; month-over-month only, within identical instrumentation. Stated in §10 and required in the methodology block. |
| 1.14, 2.2 | "35+" unenumerated, and the highest-traffic wrong claim is the homepage | The enumerated log-paths table is built first and becomes authority artifact one. Day 4 sets README, `llms.txt`, `Hero.tsx` and `src/data/agents.ts` to the number it proves. The plan asserts no count. |
| 1.15 | Reply-ceiling contradiction | Ceiling defined as replies in other people's threads; own-post replies exempt; the X reply consumes one of the 5. |
| 1.16 | HN slot lands in US dead hours | HN moved to a weekday 18:30 IST (09:00 ET) with 18:30 to 20:30 blocked. |
| 1.18 | Unverified dependencies; untracked branch | 291 stars written in. X Premium priced at $8 with the gate expected to fail. Day 4's untracked-test exit criterion removed, and the branch land-or-park decision surfaced as a fork. |
| 1.19, 2.12 | Citation targets with no collection mechanism | Google Alerts, the Search Console links report, and a monthly `site:` sweep list. Answer-engine checks demoted to labelled anecdote. Reports ship a JSON, a CC-BY licence, and standalone chart images with his name in the attribution line. |
| 1.20 | The metric denominator excludes most adopters | Primary denominator (merged PR) plus one documented fallback (explicit completed-task marker), stated as not comparable across people. |
| 2.3 | No byline, so citations credit the product | `/about` and `/writing` shipped on Day 5, byline on every report, same display name and avatar across all six platforms. The authority metric is now **named references to him**, not pages quoting a number. |
| 2.4 | Plan is 100% cost telemetry against a harness-technique goal | One of the two monthly long-form slots reserved for harness technique, with the two agent-browser and education_video pieces named. |
| 2.5 | The winning shape spent on the worst-converting surface | On launch day the number goes to a permanent repo URL first (20 min), then to the people writing the widely-read posts. |
| 2.6 | Every borrowed-audience play was dropped | Awesome-list PRs (60 min once), newsletter submissions per report (15 min), one ccusage message. |
| 2.7 | The 35 harness maintainers are the obvious peer network | Reduced to 2 or 3 maintainers, pre-publication correction offer 48 hours ahead, 30 min per report. It is the only named peer mechanism and it doubles as the n=1 defence. |
| 2.11 | The thesis is a commodity reframe | Thesis is now "cost is a harness-design property, not a model-price property". Dollars per finished task demoted to the unit of measure. |
| 2.13 | Restatements read as advice already ignored | The two genuine inversions labelled as such in §9: HN story rather than Show HN, and LinkedIn/Dev.to untested rather than failed. |
| 2.14 | Video kill overreached | Narrowed from "any new video" to "any video channel or cadence". One 60-second dashboard recording allowed as a crop asset. |

## Left alone, and why

| Item | Why |
|---|---|
| The YouTube backlog override | Well evidenced from the 2026-07-30 channel measurement and correctly overrides the brief's "21 of 40 are GenAI" inference. Critic 1 agreed. Only the wording was narrowed. |
| The 5-reply ceiling and the 90-day Reddit closure | Both critics called this the plan's most important decision. Unchanged except for the enforcement mechanism. |
| Critic 1.16's split Threads block | Half taken. The next-morning 07:00 to 07:15 pass is in, but as a *replacement* for minutes inside the 60-minute cap, not an addition, because the binding constraint is peak load. |
| Critic 2.15, `--export` crowdsourced n | Deliberately deferred. The critic ranks it last itself, it needs an audience that does not exist yet, and it is ~4 hours. Revisit after report #2. |
| A cookieless visitor counter | Deferred to the forks list. `dig` shows GitHub Pages IPs, so it needs a DNS move onto a Cloudflare zone first, which is a decision and not a task. |
| Email capture on `/report` | Deferred to the forks list with its real cost. Correctly identified as the only fix for owning no audience, but it is not free and not a fortnight item. |
| Per-channel metrics in the §5 table | Deleted, not because a critic asked but because they duplicated the §10 scorecard. §10 is now the single source for targets and kill gates. |

## Length

Original: 410 lines / 25,981 bytes across 12 sections. Revised: 452 lines /
29,616 bytes across 14 sections. Two of those sections did not exist before and
were required: §13 one-time builds with the 440-minute total, and §14 Decisions
made for you. Net of those ~3,350 bytes, the twelve original sections came in at
roughly 26,270 against 25,981, so the plan is at parity while absorbing about 30
findings. The deletions that paid for the additions were the star-count
reconciliation paragraph, the min/day column, most of the YouTube and Show HN
evidence recitals, the local-power detail, and four of the seven risk essays in
§12, all of which are preserved in this appendix.
