# Feature Friday — 2026-08-14

> Based on: `git log origin/main` (Aug 6–13) + `origin/main:UPDATE.json`.
> Shipped to `origin/main` this window: **45 commits, 11 of them `feat:`** (the rest fixes/docs/chores). Headline is **two new coding agents tracked — Muse and Prime** — plus a **new Hermes session explorer** (load-more list, URL-filtered, filters that survive a sidebar round-trip), **honest Hermes telemetry** (latency/cost-provenance/outcomes), and **truer cache-read billing**.
> This is a **feature** post (not a progress post) — real user-facing work landed.

**⚠️ Notes for maintainer — read before posting:**
- **Date:** this ran Thursday 2026-08-13 for the next Feature Friday, **2026-08-14**. Every prior draft is dated on its posting Friday; rename if you post on a different day.
- **This is a REWRITE of the earlier 08-14 draft.** The previous version (drafted Sun Aug 9) described the Hermes explorer as **"paginated / page through Y pages."** That was **superseded on Aug 10**: `feat(hermes): replace explorer pagination with a load-more list` (618c0d0) removed pagination on purpose — "Page X of Y" was dead UI and a page number in the URL could outlive its result set. A companion commit, `feat(hermes): keep explorer filters across a trip through the sidebar` (286bc8d), makes filters persist. **Do not post the old pagination language** — it advertises a UI that no longer exists.
- **`origin/main` HEAD is Aug 11.** The session-trace column-alignment fix (d14894a, Aug 12) is **still on a working branch, NOT merged to main** — so it is deliberately **not** announced here. Move it into next week's post once it lands.
- **UPDATE.json is STALE.** Its newest entry is **2026-07-12**, but **11 `feat:` commits** have landed on `origin/main` since (Muse/Prime, Hermes explorer, Hermes telemetry, cache-read billing…). This draft is built from **raw commit subjects/bodies, not curated UPDATE.json entries** — please add a UPDATE.json entry for this week (the pre-push `feat:`→UPDATE.json rule should have caught these; the merges apparently slipped through) and sanity-check the descriptions below against the live UI before posting.
- **Contributor credit:** the security hardening (Antigravity summarizer no longer runs `agy --dangerously-skip-permissions`) was contributed by **tomaioo** (PR #243, verified: merge b955ea1) — credit kept in the Discord "fixes" bullet. **Removed an unverifiable credit from the earlier draft:** it thanked "Yagnasena1999 for bug audit #224" on the cache-read fixes, but there is **no #224** in history and Yagnasena1999's only co-authored commits are from May (#29/#32/#33), unrelated to this week's cache-read work. Don't reinstate that credit without a real issue/PR to back it.
- **No invented numbers.** I deliberately did **not** state a total agent count ("now N agents"). If you want to headline a number, confirm the current total yourself and drop it in. Everything else comes straight from commits.
- **Verify the Muse/Prime story is public.** Make sure their names/branding are OK to announce publicly before posting.

---

## X / Twitter Thread

**Tweet 1 — Hook**

Two more coding agents just showed up on your TokenTelemetry dashboard: **Muse and Prime.**

If you're running them, their sessions — model, tokens, cost, working directory, full trace — now sit right alongside Claude Code, Codex, Cursor and the rest. One local dashboard for everything.

Shipped this week 🧵

*[Suggested visual: dashboard screenshot with the Muse + Prime agent cards/marquee icons visible next to the existing agents]*

---

**Tweet 2 — Muse & Prime**

TokenTelemetry now ingests Muse and Prime sessions end to end:

- recorded working directories map into project/worktree navigation, so sessions land under the right repo
- Muse subagent attribution is preserved (delegated work stays traceable)
- Prime uses its active session branch + reported cost

No config — if the sessions are on disk, they get picked up.

---

**Tweet 3 — New Hermes session explorer**

If you run Hermes: the overview page was getting crowded. Full history now lives in a dedicated **URL-filtered session explorer** (backed by a new Hermes sessions API).

No more "Page 7 of 12" — it's a **load-more list** that always returns the whole visible set in one request, so a stale page number can never strand you on an empty screen. Filter it, wander off through the sidebar, come back — your filters are still there.

*[Suggested visual: short GIF filtering the explorer, hitting "Load more," then navigating away and back with filters intact + a filtered URL in the address bar]*

---

**Tweet 4 — Honest Hermes telemetry**

Also for Hermes: we stopped rendering numbers we hadn't earned.

Latency now reads **rotated** log files too (once `agent.log` rolled over, timings used to just vanish). And every session now carries an explicit **cost-provenance** state — a `$0` that means "unpriced" no longer looks like a `$0` that means "free."

---

**Tweet 5 — Truer cost on cache reads**

Billing got more accurate where it quietly undercounted: **cache-read tokens are now priced cumulatively** for Claude, Qwen and Cursor (per-turn totals feed cost, high-water values still drive the session display). And Analytics now **discloses** Claude activity it can only count but can't price locally, instead of silently dropping it from totals.

---

**Tweet 6 — Close + install**

Free, open source, 100% local — your logs never leave your machine.

```
curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash
```

→ https://github.com/VasiHemanth/tokentelemetry

---

## Discord #announcements Post

**TokenTelemetry — Feature Friday (2026-08-14)**

Big week for agent coverage and for telling the truth about costs. Highlights:

- **🆕 Two new agents: Muse & Prime.** TokenTelemetry now ingests Muse and Prime coding-agent sessions — model, tokens, cost, and full trace — alongside every agent you already track. Recorded working directories map into project/worktree navigation, Muse subagent attribution is preserved, and Prime uses its active session branch with its reported cost. Zero config: if the sessions are on disk, they show up.
- **🔎 New Hermes session explorer.** The Hermes overview stays concise; full-history navigation moved into a dedicated, **URL-filtered** explorer backed by a new Hermes sessions API. It's a **load-more list, not pagination** — one request returns the whole visible set, so there's no page number to fall out of sync and land you on an empty screen. Filters now also **survive a trip through the sidebar and back**, and shared/bookmarked filtered links still win.
- **📉 Honest Hermes telemetry (latency · cost provenance · outcomes).** Latency now parses **rotated** log files (`agent.log.1`, `.2`…), oldest-first, so timings survive a log rotation instead of disappearing. And each session carries an explicit **cost-provenance state**, so a `$0` that means "we couldn't price this" is no longer indistinguishable from a genuine zero.
- **💵 Truer cache-read billing.** Cache-read tokens are now priced **cumulatively** for **Claude, Qwen and Cursor** (per-turn totals feed cost; high-water values still drive session display), and duplicate assistant usage records are de-duplicated. Analytics also now **discloses** Claude activity it can count but can't price locally, rather than silently excluding it from cost totals.
- **🔒 Security hardening:** the Antigravity summarizer no longer invokes `agy` with `--dangerously-skip-permissions`, closing an RCE-class path if the summarizer is fed manipulated input. Thanks to **tomaioo** for reporting and fixing this (PR #243).

Install or update:
```
curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash
```

Full changelog: https://github.com/VasiHemanth/tokentelemetry/commits/main

---

## LinkedIn Post

**Your AI coding agents keep multiplying. The bill for them shouldn't be a mystery — and this week TokenTelemetry got better at both.**

TokenTelemetry is a free, open-source, 100%-local dashboard for what your AI coding agents actually do and what they cost. Everything is read on your own machine; nothing leaves it. Two themes shipped this week: **wider agent coverage** and **more honest cost reporting.**

**Wider coverage: Muse and Prime are now tracked.** If your team is running these agents, their sessions — model, tokens, cost, working directory, and full trace — now appear alongside Claude Code, Codex, Cursor and the rest, in one place, with no extra configuration. Recorded working directories map into the right project and worktree, subagent attribution is preserved so delegated work stays traceable, and there's nothing to wire up: if the sessions are on disk, they show up. For anyone trying to answer "what are we spending across *all* our coding agents," fewer blind spots is the whole game.

**More honest costs: we stopped showing numbers we hadn't earned.** Cache-read tokens — an easy thing to undercount — are now priced cumulatively across Claude, Qwen and Cursor, so the cost figure reflects what actually happened rather than a stale snapshot. Where TokenTelemetry can count Claude activity but can't price it locally, the dashboard now says so explicitly instead of quietly dropping it from totals. And for teams on Hermes, every session now carries an explicit cost-provenance state, so a "$0" that means "we couldn't price this" is never confused with a real zero. A cost dashboard is only useful if you can trust the number — and trust comes from it being honest about what it doesn't know.

**Plus:** a redesigned Hermes session explorer for navigating long histories — a load-more list rather than page numbers, URL-filterable, with filters that persist as you move around the app; latency that survives log rotation; and a community-contributed security fix that removes a permission-skipping flag from the Antigravity summarizer (thanks to tomaioo, PR #243).

Everything stays local and inspectable. Free and open source — install or update with one line:

```
curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash
```

→ https://github.com/VasiHemanth/tokentelemetry
