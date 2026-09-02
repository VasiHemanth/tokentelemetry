# Distribution plan, 2026-08 onward

Written 2026-07-30, revised after two adversarial reviews. Supersedes
`marketing/01-platform-strategy.md` and `02-weekly-content-calendar.md`.
Evidence, agent disagreements, critique log: `01-research-appendix.md`.

---

## 1. Where you actually are

Roughly 450,000 social impressions per install-page view: 0.0167% Threads
clickthrough chained with 1.33% homepage-to-install-page. In five weeks, 676
comments and zero original posts, videos or articles, so none of it carries your
byline, is citable, or is findable next month. Reddit accounts banned. Stars 291.
Site speed is fine (Clarity 86/100); the problem is a desktop curl-pipe-bash CLI
meeting phone traffic.

One limit governs every number below. `Analytics.tsx:52` gates GA4 and Clarity on
`consent === "granted"` in `localStorage`, which the mobile in-app webviews that
are 61% of traffic often partition or clear per session, so 436 sessions and 13
install-page views are a consented subset of unknown size. **Every GA4 ratio here
is a lower bound and is labelled as one, and 450,000 is frozen as an unmeasured
estimate rather than a baseline to beat.** Reddit's 1.36 mean score is
likewise survivor-biased, and Threads likes are unusable (scrape bug), so views is the
only Threads figure you can quote.

## 2. What the data says works

Every top placement you have, on both platforms, was a model-news thread. One shape:

> a model launch or pricing change less than 24 hours old
> + the reframe that the useful check is dollars per finished task, not the benchmark chart
> + one measured number from my own logs
> + first person

43% of tracked placements got under 100 views and all top ten were news-timed, so
the variable is event timing, not volume. Two changes: publish it as a post you own
instead of a reply you rent, and on launch day put the number at a permanent URL
first (a dated file in the repo, 20 min) so the people writing the widely-read posts
have something to cite.

## 3. The three corrections

| The doc says | Measured | Corrected position |
|---|---|---|
| No Threads section at all | #1 referrer, 113 sessions/30d, 789,522 views, the only real view engine | Primary reach channel. Original posts only, event-gated, typed by hand. |
| Reddit "highest-converting, highest-risk" | 82 sessions, mean 1.36, 79% at zero upvotes, banned | Burned. Closed to 2026-10-30. One appeal per account, week 1. |
| X "primary channel", 1 post/day + 3-5 replies/day | 7 posts ever, paused. That cadence is 28-42 replies/wk, the shape that got you banned. | Derivative echo behind a hard kill gate. Never a channel you write for. |

Fourth correction, a real inversion rather than a restatement: LinkedIn and Dev.to
were never tested, not proven to fail. 22 LinkedIn drafts and zero published posts, and
absence from referrer data on a channel with zero posts is not evidence. Discord goes,
Dev.to survives as a canonical syndication target, LinkedIn stays reduced because 69%
of linkedin.com visits are desktop against your 61%-mobile conversion wall.

## 4. The engine

**A monthly Agent Cost Report at a permanent per-month URL (`/report/2026-08`),
`/report` as the always-latest alias, byline "by Hemanth Vasi" linking to
`/about`.** Every number followed by the SQL that produced it and the session
count. Fixed sections:

1. Cost decomposition: fresh input, output, cache reads, as shares of the bill.
2. Cross-harness cache share of read tokens, **unsorted**, session count and task
   type beside each harness, and one sentence saying it measures how I used each
   harness rather than harness quality. Never a descending bar chart.
3. Dollars per finished task as a distribution with n and the top-session share
   beside it, never a headline mean (eight sessions are 57.7% of spend), and
   unmerged work-in-progress cost as its own separate line.
4. Subagent unit costs by type, labelled Claude Code only because no other harness
   records them (`by_subagent_type`, `test_delegation.py:426`), plus one
   model-launch spot check.
5. Methodology block: dates, session count, how a task was counted, pricing
   coverage percentage, what is not covered, and the ratio rule.

**The ratio rule, printed in every report.** Ratios inside a harness are
defensible; comparisons across unlike workloads are not. Cache share survives
because it is a ratio within each harness. Average cost per session dies because
Antigravity is 343 sessions for $54 and Claude Code 341 for $4,198, so it measures
what I chose each harness for. Claim ratios, mechanisms and arithmetic, never
population averages.

**The thesis.** Not "dollars per finished task, not the benchmark chart", a
commodity reframe anyone can repeat without crediting you. The thesis is the finding
underneath: cache re-reads dominate the bill, fresh input is close to negligible, and
cache share varies by more than 2x across harnesses. What everyone optimises, prompt
and context size, is a rounding error. What nobody looks at, how often the harness
re-reads its own context, is most of the bill. **Cost is a harness-design property,
not a model-price property.** Dollars per finished task stays the unit of measure. No
exact percentage is published until Day 6 clears it.

**Made quotable:** `report/2026-08.json` beside every report, CC-BY licence, each
chart a standalone image at a permanent URL with your name in the attribution line.

**The feeder: a weekly logbook at `docs/logbook/YYYY-WW.md`, 10 min,** because it is
an edit-and-publish of Monday's automated digest. Its job is cadence; an engine
whose smallest unit costs an hour reproduces the publish-step failure.

```
Monday's automated digest -> weekly logbook entry (10 min)
   -> monthly report (own domain, permanent URL, JSON + CC-BY)
        -> dev.to copy, canonical_url pointing home (15 min)
        -> 2 or 3 AI/dev newsletter submissions (15 min)
        -> Threads original post: strongest chart + one number + UTM link
        -> LinkedIn native PDF carousel, no link in post or first comment
        -> X native post, same screenshot, no link
        -> one Hacker News story submission when a report is genuinely good
```

Nothing is authored twice. Everything after the report is a crop of it.

## 5. Platform allocation

Minutes are per week. A per-day column smears work across days that do not exist.

| Platform | Format and cadence | News wk | Quiet wk |
|---|---|---|---|
| tokentelemetry.com | Monthly report + weekly logbook. Both tracks. | 70 | 70 |
| Threads | Original post with chart, in-post UTM link, one tag, **typed by hand in the app**. 2/wk max, event-gated. Installs and reach. | 105 | 0 |
| LinkedIn | Native PDF carousel cropped from the report, 1 carousel + 1 text post/mo. Authority. | 30/mo | 30/mo |
| dev.to | Syndicated copy, `canonical_url` set, per report. Authority via search. | 15/mo | 15/mo |
| X | Report-day native post plus one hand-written launch-day reply, 3 items/wk max. Echo only. | 15 | 0 |
| Hacker News | One story submission, not Show HN | 0 | 0 |
| Replies in others' threads | Hand-written, disclosed, 5/wk ceiling | 15 | 0 |
| **Reddit** | **Closed to 2026-10-30.** Appeal only, week 1. | 0 | 0 |
| **YouTube** | **No channel, no cadence.** Unlist old Shorts once. | 0 | 0 |
| **Instagram, Facebook, Discord, Medium, Hashnode, llms.txt** | **Drop** | 0 | 0 |

Per-channel success metrics and kill gates live in the section 10 scorecard, so
they are not duplicated here.

YouTube overrides four of eleven research agents: 2,051 lifetime views across 32
Shorts, median 34.5, and every title is a GCP interview question. Do not publish the
31-video backlog. One exception, a crop asset and not a channel: one 60-second screen
recording of the dashboard's cache-read decomposition, reused in the Threads post, the
carousel and the mobile CTA block.

## 6. The authority track

The report is the install track's artifact. Authority gets its own artifact, metric and
collection mechanism, or it is product marketing in a hat.

**Artifact one: where each coding agent writes its logs, and how many there are.** A
per-harness table of paths and formats, with the agent count derived from it rather
than asserted. Today README says nothing, `llms.txt` says 10 and the 978-view homepage
says 11. Enumerate first, publish the number the table proves, set all four surfaces to
it (Day 4).

**Artifact two: the metric spec** at `/docs/metrics/dollars-per-finished-task`, with
`tokentelemetry report --metric dpft` as the reference implementation. Seven things
your own data proves ambiguous:

| Decision | Because |
|---|---|
| Numerator includes delegated subagent cost and cache-read spend, excludes unpriced models with a stated coverage percentage | $908.22 of $5,907.96 is delegated, cache reads are most of the bill, and unpriced models read as free |
| Primary denominator is a merged PR, time-aligned to the merge window, PRs segmented not pooled, attribution by working directory | The naive version swings 31x, and a pricing-sync PR is not a feature PR |
| Documented fallback denominator: an explicit completed-task marker, **not comparable across people** | Solo and non-git work cannot compute the PR version, and a spec nobody can run does not get used |
| WIP spend after the last merge is its own line | $2,153.01 across 43 sessions would inflate it |

**The byline, without which every citation credits the product and not you.**
`website/src/app/` has no about, author or blog route today. `/about` carries your name,
face and one paragraph on what you measure and why; `/writing` is a permanent
reverse-order index of every report and long-form piece; the same display name and
avatar go on Threads, X, LinkedIn, GitHub, dev.to and HN. Without the index, ten months
of work is ten orphan URLs.

**The peer mechanism, 30 min per report.** 48 hours before each report publishes,
email the two or three harness maintainers whose product appears in it: their own
numbers, the SQL, and an offer to correct anything before publication. You have
measured data about their products they cannot get themselves. It is the only thing
here that produces named peers, and it hardens the numbers against the n=1 attack.

**One of the two monthly long-form slots is harness technique, not cost,** because a
plan made entirely of cost telemetry measured by your cost product is marketing. Two
pieces only you can write, neither pointing at the dashboard: "how I drive a Remotion
video pipeline from three different CLI agents with one skill set", and "one MCP
browser bridge, seven agents, what broke in each".

**Borrowed audiences, zero comment volume added.** PRs adding TokenTelemetry to four
awesome lists (60 min once), each report to two or three AI/dev newsletters (15 min
per report), one message to the ccusage maintainer about a mutual mention.

**The authority metric: named references to *you*, not the tool,** in third-party
posts, docs or repos, plus citations of the metric spec URL. Collected from Google
Alerts on "dollars per finished task" and "TokenTelemetry", the Search Console links
report, and a monthly `site:` sweep list in `scorecard.md`. Target 3 by report #3. The
answer-engine check runs logged out, 3 trials, verbatim answer and date recorded, and
is **anecdote, not a KPI**, because personalisation contaminates it.

## 7. Commenting, rebuilt

Ceiling: **5 hand-written replies per week, all platforms, zero automated.** Down from
135. The ceiling covers replies inside other people's threads; replies on your own
posts are exempt and required for reach. The X launch-day reply consumes one of the 5.
It only ever goes down. Zero replies in a no-news week is correct, not a miss.

Gates, all must pass:

1. The thread is a live model launch or pricing change, under two hours old.
2. You have a measured number from your own logs that answers the actual question.
3. The reply carries an explicit "I build TokenTelemetry" line.
4. No link unless someone asks.
5. Never reply to the same handle twice in 30 days. Keep a plaintext
   `marketing/replies.md` of handle plus date and grep it before posting.
   `server/author_cooldown.js` cannot enforce this; a hand-typed reply never touches
   that server.
6. You found the thread while reading, not via a script.

**The ceiling has to be structural, because this rule already existed and had 0%
compliance.** `04-cowork-automation.md:17` said "everything is human-posted" on
2026-06-12 and three auto-posting skills followed. Automation happens because it is
the only thing that produces output when the manual budget is one hour, so remove the
capability:

- `rm` the 15 symlinks in `~/.claude/skills`, `~/.grok/skills`, `~/.codex/skills`,
  `~/.cursor/skills`, `~/.agents/skills` (all point at `quirky-borg/skills/`).
- Remove the registrations in `~/.claude.json` (lines 2413-2414, 3175, 3207, 3211).
- Hard exit on a `POSTING_DISABLED` check at the top of
  `quirky-borg/server/parallel_post.js` and `post_x.js`.
- Delete the posting credentials, cookies and browser profiles they drive.
- **Original Threads posts are typed in the Threads app on the phone. No agent-browser
  bridge, no claude-in-chrome, ever.** 306 automated comments sit inside Meta's
  retroactive-enforcement window, Threads is 100% of your measured reach, and posting
  through the bridge reproduces the fingerprint that ended Reddit on the one account
  you cannot lose.

**Reddit recovery.** One appeal per banned account through the official route in week 1,
before anything publishes, stating plainly what was automated and that it has stopped.
No new accounts: that is ban evasion, and device-level action forecloses Reddit
permanently. Closed to 2026-10-30 regardless; if restored, re-entry is original posts on
launch days only.

## 8. First fortnight: 10 working days, 4 declared slack

| Day | Deliverable | Min |
|---|---|---|
| 1. Mon 08-03 | Kill the automation (section 7) **first**. Then config only, no code: mark the shipped `copy_install_command`, `click_github`, `click_install` as key events in the GA4 UI, add `consent_choice`, verify Search Console, set the Alerts, write `marketing/utm-convention.md` against the shipped names. File the Reddit appeals. | 60 |
| 2. Tue 08-04 | Pricing. Re-search provider prices, run `pricing_sync.py`, commit refreshed `pricing_data.json` (its `updated` field reads 2026-07-06; 2,341 models priced but the newest Anthropic entry is `claude-4.7-opus`, so every `claude-opus-5` session prices at $0), add the curated `claude-opus-5` entry with cache rates, plus a regression test that fails when any model in `history.db` has no pricing entry. Includes `UPDATE.json`, the pre-push hook and the PR. | 60 |
| 3. Wed 08-05 | Delegated cost. Surface the $908.22 beside the headline total, explicitly labelled. Record the 503 zero-cost sessions and the pricing coverage percentage. PR overhead included. | 60 |
| 4. Thu 08-06 | Enumerate the agents from the backend, produce the log-paths table, set `README.md`, `llms.txt:25`, `Hero.tsx:48,66` and `src/data/agents.ts` to the number it proves. Change the tok/s **display string and docs only** to "effective tok/s (output tokens / wall-clock session, includes tool calls)"; do not touch the column or the identifier. | 60 |
| 5. Fri 08-07 | `/report`, `/about`, `/writing` routes plus sitemap entries. Byline in the report template. `/report` carries its own copy-install block and mobile fallback, or it inherits the homepage leak one layer down. | 60 |
| Sat 08-08, Sun 08-09 | **Declared slack.** Catch-up, or two of the section 13 builds. | 0 |
| 6. Mon 08-10 | Save the query set as `marketing/report-queries.sql`, run it, independently recompute a second way from the archived transcripts. **The stop condition applies to every number that will appear in the report, not just the total; any pair disagreeing by more than 2% slips the publish.** No approximate numbers, no hedges. | 60 |
| 7. Tue 08-11 | Draft sections 1 to 4. | 60 |
| 8. Wed 08-12 | Draft sections 5 to 7 plus the methodology block. Email the harness maintainers their numbers and the SQL, 48 hours ahead. | 60 |
| Thu 08-13 | **Declared slack.** Buffer for a failed recompute or a fighting chart renderer. | 0 |
| 9. Fri 08-14 | Charts from the renderer under `carousel_pipeline.js` (works; only the Gemini CLI entry point is dead). Read the page at 390px. Publish `/report/2026-08` with the JSON and CC-BY line. Syndicate to dev.to, `canonical_url` verified in view-source. Submit to two newsletters. | 60 |
| 10. publish+1 | Threads original post 19:00 to 20:00 IST, typed in the app. Second pass 07:00 to 07:15 IST next morning (21:30 ET the prior evening), which catches the US reply wave the 19:00 block misses. Same numbers as a native X post, no link. | 60 |
| publish+2 on | **Declared slack.** Scorecard row #1 rides the steady-state Monday; the carousel rides the monthly slot. | 0 |

Post-publish days are relative, not date-pinned, because the Day 6 stop condition can
legitimately slip Day 9.

**Fortnight arithmetic: 10 working days x 60 min = 600 min = 10.0 hours over 14
calendar days = 43 min/day average, peak day 60.** Day 1 is all config and no code
because the instrumentation step has the same failure record as the publish step:
`06-analytics-findings.md` specified these exact events and this exact mobile path on
2026-06-23 and five weeks later neither shipped.

## 9. Weeks 3 to 8, steady state

| Day | Work | News wk | Quiet wk |
|---|---|---|---|
| Mon | Scorecard row. First line is "did last week's artifacts exist": last week's digest file, logbook file, `postings` row. | 20 | 20 |
| Tue | Threads original post if a launch or pricing change happened, 19:00 to 20:00 IST plus the 07:00 next-morning pass. Otherwise nothing. | 60 | 0 |
| Wed | Weekly logbook: edit and publish Monday's digest. | 10 | 10 |
| Thu | Threads post #2 if there is news, plus the X echo. Otherwise nothing. | 45 | 0 |
| Fri | One deep-work hour. Weeks 1 and 2: long-form, alternating cost and harness technique. Weeks 3 and 4: report production. | 60 | 60 |
| Sat | Publish or queue what is due. Last Saturday of the month is a report hour. | 30 | 0 |
| Sun | Off. | 0 | 0 |
| | **Week total** | **225 (3.75 h)** | **90 (1.5 h)** |

```
Monthly, two news weeks and two quiet weeks:
  2 news weeks               2 x 225 = 450 min
  2 quiet weeks              2 x  90 = 180 min
  last-Saturday report hour (60 not 30) +30 min
  monthly extras: carousel 30 + dev.to 15 + newsletters 15
                  + maintainer pre-review 30  =  90 min
                                        total = 750 min
  750 / 28 days = 26.8 min/day. Peak single day 60 min.
```

Report #2 is due 09-01, so production starts about 08-24 and is reserved: the last two
Fridays plus the last Saturday of each month are report hours (3 x 60 = 180 min, being
recompute + draft + charts-and-publish on saved SQL). Long-form moves to the first two
Fridays. Nothing else takes those slots.

The report ships the first Tuesday of the month, 18:30 IST (09:00 ET). Long-form every
two to three weeks, never weekly: a piece with measured data and charts is 6 to 8 hours.
Submit one report or reference piece to Hacker News as a normal story on a **weekday at
18:30 IST (09:00 ET)**, blocking 18:30 to 20:30 for comments; the original Sunday 07:30
IST slot was Saturday 22:00 ET, 90 of your scarcest minutes spent while the audience
slept. Hold the Show HN slot, because Show HN'd token dashboards scored 1 to 7 points in
2026 while a cost-analysis article scored 480.

## 10. Measurement

**Week 1, before publishing anything:** the three shipped GA4 events marked key in the
UI (do not rename them and orphan the history), the new `consent_choice` event,
`install_page_view` on the docs install page, `utm_source` / `utm_medium` /
`utm_campaign` on every owned link, Search Console verified, Threads Insights on a
professional account. Confirm on Day 1 that Insights requires the switch before
spending the minutes; it does not expose outbound link clicks, so site clicks come
from UTM'd GA4 sessions.

One scorecard row a week in `scorecard.md`. Weekly totals, not daily: at 14 sessions a
day, daily granularity is noise. Every GA4 figure is a consented lower bound.

| Number | Source | Today | Target |
|---|---|---|---|
| `copy_install_command` by utm_source | GA4 (lower bound) | 0 | Non-zero in each of 3 consecutive weeks from 08-11, one with a `utm_source` attached |
| Impressions per install-page view | GA4 + Insights | ~450,000, **unmeasured, not comparable** | First post-instrumentation month is the real baseline. Month over month only, within identical instrumentation. |
| Site clicks per 1,000 Threads views | GA4 (lower bound) | 0.167 | Above 0.5 by 09-30 |
| Threads followers per 1,000 views | Threads Insights | Unknown | Set at the median of the first two original posts, then beat it |
| Report-page to install-page rate | GA4 (lower bound) | n/a (homepage 1.33%) | Above 10% by report #3 |
| Scroll depth past 75% on /report | Clarity | Site cliffs at 20% | Above 25% of readers |
| LinkedIn reach beyond the first degree | LinkedIn + GA4 | Untested | Any `utm_source=linkedin` sessions by 08-31, else drop |
| X | X analytics | 7 posts ever | One post above 5,000 impressions or 10 bookmarks by 08-31, else cancel Premium |
| Replies in others' threads | `marketing/replies.md` | 135/week | 5/week ceiling |
| Account actions | platforms | 2 bans | 0 |
| Named references to you | Alerts + Search Console + `site:` | 0 | 3 by report #3 |

Keep the tracks separate and do not average them. Install track:
`copy_install_command` by source, report-to-install rate, stars, impressions per
install-page view. Authority track: named references and spec-URL citations.

25,000 is a model, not a target: 1 / (0.002 x 0.02) from a 0.2% in-post clickthrough
landing on a page converting at 2%. Adding UTMs and key events improves the measured
ratio by an order of magnitude on Day 1 with no distribution change, so any
before-and-after against 450,000 is an instrumentation artifact. Say so in the
methodology block, because somebody will otherwise quote an 18x improvement back at
you.

## 11. Kill list

- All automated commenting, every platform, permanently. Capability removed, not tuned
  down: symlinks, `~/.claude.json` entries, credentials, cookies, browser profiles,
  `POSTING_DISABLED` hard exit.
- The no-disclosure instruction (`skills/tt-social-post/SKILL.md:234,:586`,
  `skills/tt-threads-post/SKILL.md:260,:464`, `AGENTS.md:43`).
- The daily five-platform draft factory in `marketing/drafts/`: 36 drafts in the
  measured window, zero published posts. It eats the publishing hour.
- Reddit until 2026-10-30, no new accounts. Discord, Medium, Hashnode, Instagram and
  Facebook permanently.
- Publishing the 31 finished videos, and any video channel or cadence. The one
  60-second dashboard recording is a crop asset, not a channel.
- `node scripts/post.js`. Exits 0, publishes nothing. Any publish that does not write a
  `postings` row did not happen.
- `carousel_pipeline.js` as an entry point (dies at step 1 on the discontinued Gemini
  CLI). The renderer under it generates the charts.
- Any dollar figure before Days 2, 3 and 6 land. The dashboard understates by 25.8%
  ($4,381.67 against a measured $5,907.96) and one `claude-opus-5` session with 1.15
  billion cache-read tokens displays as $0.05. That session sits inside the cache-read
  share, so the decomposition percentages move too.
- Any per-harness average-cost-per-session ranking, and any descending cache-share bar
  chart. See the ratio rule.
- The local-model power, energy and CO2 story as a data story. Three local sessions,
  `tok_per_sec` NULL in 1,264 of 1,264 rows, `power.json` hand-set at 22W. The code is
  correct; the data is not there. One methodology post at most.
- Views as a KPI. 789,522 Threads views bought 113 sessions.
- Links in LinkedIn post bodies, and the link-in-first-comment workaround.
- Renaming any shipped GA4 event, or the `tok_per_sec` column or API field.
- Aiming any content at the homepage.
- **Making the existing private posting repo public, ever.** `origin/master` holds
  `posted_comments.csv` plus 380 third-party Threads post IDs and 311 Reddit URLs in
  tracked source. A fresh-history public repo is the only publishable artifact.
- Submitting the postmortem to Hacker News or LinkedIn.
- `01-platform-strategy.md`, `02-weekly-content-calendar.md` and the four reference
  docs as operating plans. Archive them with a dated note pointing here.
- Citing `docs/wiki/` pages as fact until each source file is re-read.

## 12. What could make this fail

**The publish step fails again and nothing notices. That is three silent failures.**
`post.js` exits 0 while publishing nothing, the YouTube refresh token is dead, and
`com.tokentelemetry.weekly-digest` has produced nothing for three consecutive Mondays:
`logs/weekly-digest.err` holds three repetitions of `Operation not permitted` with the
exec bit set, so macOS TCC is denying launchd-spawned `/bin/bash` access to
`~/Documents`, and its only success signal was a notification, so it notified nobody.
Discipline is not the mitigation: relocate the script (section 13), have it notify on a
missing logbook file, and make the Monday scorecard's first line "did last week's
artifacts exist".

**The postmortem lands on your own name at the wrong time.** An appeal reviewer, an HN
commenter or your employer will surface it. Appeals week 1, before anything publishes;
the postmortem only after they resolve or after 2026-10-30, whichever is later; the HN
submission is always the report or a reference piece; never LinkedIn.

**Threads depreciates and you own no audience.** All 789,522 views came from
unconnected reach, which Threads is rebalancing away from, and Threads is 100% of your
reach, so if that account goes the install track goes with it. Followers per 1,000
views, not views, is therefore the KPI.

**The n=1 attack and a published number that later moves** are handled by the ratio
rule plus SQL and session count as hard template fields with maintainer pre-review
behind them, and by the Day 6 recompute plus the unpriced-model regression test.

## 13. One-time builds, outside the recurring budget

| Build | Cost | When |
|---|---|---|
| Kill the automation | 20 min | Day 1, first |
| Move `weekly-digest.sh` to `~/.local/bin`, re-point the plist, add the logbook-absence check | 20 min | first slack day |
| Unlist the 32 interview-prep Shorts, rewrite the channel description | 25 min | any slack day |
| Awesome-list PRs, four lists | 60 min | any slack day |
| Mobile CTA block: star the repo, copy the command, prefilled `mailto:?subject=...&body=<curl command>`, one line saying this is a desktop CLI. "Email it to yourself" is unbuildable: `next.config.ts` is `output: "export"` on GitHub Pages, so there is no server and no mail path. | 45 min | week 3 Friday |
| 60-second dashboard screen recording | 90 min | before the first carousel |
| Metric spec page + `tokentelemetry report --metric dpft` | 3 h | three Fridays after report #1 |

One-time total: 20 + 20 + 25 + 60 + 45 + 90 + 180 = **440 min = 7.3 hours**, spread
over eight weeks against declared slack and Friday deep-work hours.

## 14. Decisions made for you

Accept these and act.

1. **Automation dies by capability removal, not by policy** (the five bullets in
   section 7). A written ceiling existed on 2026-06-12 and had 0% compliance.
2. **Original Threads posts are typed by hand in the app.** No bridge, no MCP browser,
   ever, on the one account you cannot lose.
3. **Do not rename any shipped GA4 event or the `tok_per_sec` field.** Mark the three
   existing events key in the GA4 UI, add `consent_choice` and `install_page_view`,
   change the tok/s display string only.
4. **The thesis is that cost is a harness-design property, not a model-price
   property.** Dollars per finished task is the unit, not the headline, and no exact
   percentage is published until Day 6 clears it.
5. **Authority gets its own artifact and metric:** the enumerated log-paths table and
   the metric spec, measured by named references to you, with `/about` and `/writing`
   shipped so those references have somewhere to land.
6. **Reserve the last two Fridays and the last Saturday of each month for report
   production.** Report #2 is due 09-01 and previously had no hours.
7. **Enumerate the agents before publishing a count, then fix all four surfaces,**
   including `Hero.tsx` and `src/data/agents.ts`, which carry the 978-view page.
8. **Appeals week 1; postmortem only after they resolve or after 2026-10-30; never on
   HN or LinkedIn.**

These need your decision. Real forks, not preferences.

- **`feat/local-model-insights`: land it or park it before Day 1.** Twelve modified
  files, four untracked, and the fortnight assumes a clean tree. Section 11 kills
  the local-model power story as a data story while that branch is mid-build on
  exactly it. Landing it is fine; publishing from it is not.
- **The postmortem at all, under your real name, while you hold a day job.** The
  plan sequences it safely; whether to publish is yours.
- **A consent-independent visitor counter.** Cloudflare Web Analytics is ten
  minutes of work, but `dig` shows tokentelemetry.com pointing straight at GitHub
  Pages IPs, so it needs a DNS move onto a Cloudflare zone first.
- **Email capture on `/report`.** The only fix for owning no audience, and not
  free: a named provider, a `website/src/app/privacy/` edit, and Turnstile.
- **$8/month for X Premium.** The plan expects the 08-31 gate to fail. Paying to
  find out, or skipping X entirely, is your call.
