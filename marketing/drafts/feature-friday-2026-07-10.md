# Feature Friday — 2026-07-10

> Based on: `git log origin/main --since="7 days ago"` | UPDATE.json (no new entry this week — correct, nothing feat: shipped)
> Shipped this week: 0 feat: commits. 2 fix: commits (cache-hit accuracy, PR #127 + follow-up), 1 chore (weekly models.dev pricing refresh, PR #125).

**Reviewer note:** No user-facing features merged to main this week, so per the never-fabricate rule this is a **progress post**, not a feature announcement. The story that carries it is a good one though: a community contributor (Tom Swift, PR #127) found that the analytics cache-hit rate was significantly *underreported* — his corpus actually hit ~99.9% but displayed ~70% — and the fix plus your follow-up (persisting `cache_reads` in the durable store, issue #126) shipped Tuesday. The numbers below come straight from the commit messages, nothing invented.
**Check before posting:** the "coming next" teasers reference the unmerged `feat/multi-agent-metrics` branch (live process monitor, concurrency timeline, workflow grouping). If that's not landing soon or you'd rather not pre-announce, cut those lines — everything else stands alone.

---

## X / Twitter Thread

**Tweet 1 — Hook**

Quieter week for TokenTelemetry — no new features, but one fix worth knowing about:

Your prompt-cache hit rate was being underreported. Possibly badly. A corpus that actually hits ~99.9% was displaying as ~70%.

Fixed this week, thanks to a community PR. Here's what was wrong 🧵

*[Suggested visual: before/after of the Analytics cache-hit figure — same data, ~70% → ~99.9%]*

---

**Tweet 2 — The bug**

TokenTelemetry stores cached tokens as a high-water mark of the cached prefix — deliberately, so totals and cost don't recount the same prefix every turn.

But the analytics hit-rate divided that HWM by *cumulative* input. So the longer your sessions ran, the worse your hit rate looked. Long sessions = most unfair to.

---

**Tweet 3 — The fix (and the fix's fix)**

PR #127 (thanks @tom-swift-tech 🙏) switched the math to true cumulative cache reads — verified by recomputing straight from the session JSONLs.

Follow-up: stored sessions (the ones that outlive agent transcript pruning) now persist cache reads too, so the corrected rate survives cleanup instead of silently degrading over time.

---

**Tweet 4 — Also this week + what's next**

Also: the weekly models.dev pricing refresh landed, so cost estimates stay current across 2000+ models.

In the works: live resource monitoring for agent processes, a concurrency timeline for parallel sessions, and grouping sessions into named workflows with rolled-up cost. Soon.

---

**Tweet 5 — Close + install**

If your dashboard told you your cache hit rate was mediocre — it probably lied. Update and see the real number:

```
curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash
```

GitHub → https://github.com/VasiHemanth/tokentelemetry

---

## Discord #announcements Post

**TokenTelemetry — weekly update (2026-07-10)**

No new features this week — but an accuracy fix you'll actually notice:

- **📈 Cache-hit rate was underreported — now fixed.** The Claude-style scanners store cached tokens as a high-water mark (so totals/cost don't double-count the prefix), but analytics divided that HWM by cumulative input — so the displayed hit rate shrank as sessions grew. A corpus with a real ~99.9% hit rate showed ~70%. PR #127 (community contribution from Tom Swift — thank you! 🙏) recomputes it from true cumulative cache reads. Token totals and costs were always correct; only the percentage was wrong.
- **💾 …and it survives transcript pruning.** Follow-up fix: the durable session store now persists cache reads (schema v2, auto-migrated), so sessions that outlive your agent's own transcript cleanup keep the corrected rate instead of quietly falling back to the old math (issue #126).
- **💰 Pricing data refreshed** from models.dev — routine weekly sync keeping cost estimates current.

**Coming up:** live CPU/memory/disk-IO monitoring for agent processes, a concurrency timeline for overlapping sessions, and workflow grouping (tag sessions from any agent into a named task, see total cost). In progress now.

Update:
```
curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash
```

Full changelog: https://github.com/VasiHemanth/tokentelemetry/commits/main

---

## LinkedIn Post

**When your metrics dashboard is wrong in the pessimistic direction**

Quiet week for TokenTelemetry — no new features — but it shipped a fix that's a useful lesson in metrics design.

TokenTelemetry tracks what AI coding agents cost, including how effectively they use prompt caching (cached tokens are billed at a fraction of fresh ones, so cache-hit rate is a real cost lever). This week a community contributor discovered our reported cache-hit rate was substantially understated: a session corpus with a true ~99.9% hit rate displayed as ~70%.

The cause was two internally-consistent decisions colliding. Cached tokens were stored as a high-water mark of the cached prefix — correct for cost math, since you shouldn't recount the same prefix every turn. But the hit-rate calculation divided that high-water mark by *cumulative* input. Each number was right for its own purpose; the ratio between them meant the longer an agent session ran, the worse its cache efficiency appeared. The metric punished exactly the sessions doing caching best.

The fix computes the rate from true cumulative cache reads (verified by recomputing directly from raw session logs), and a follow-up ensures the corrected figure persists in long-term storage — so it survives even after agents prune their own transcripts.

Two takeaways for anyone building cost or observability tooling: a metric can be built from individually-correct numbers and still be wrong, and the way to catch it is a user recomputing from source data — which is only possible because everything TokenTelemetry reads is local and inspectable. Open source paying for itself: the report and the fix came from the community within the same PR.

TokenTelemetry is free, open source, and 100% local — one line to install:

```
curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash
```

→ https://github.com/VasiHemanth/tokentelemetry
