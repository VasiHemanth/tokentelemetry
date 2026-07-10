---
name: bug-audit
description: Weekly multi-agent audit for serious bugs (data integrity, silent caps, staleness, timestamp math, trust boundaries). Fans out Sonnet scanners + Opus deep auditors, adversarially verifies every finding, files GitHub issues for confirmed critical/high bugs. Trigger: /bug-audit
---

# bug-audit — weekly serious-bug sweep

Multi-agent audit of the TokenTelemetry backend/frontend for the bug class
that motivated it (PR #131: a silent 100-session cap plus stub rows crushing
real persisted data). Optimized for bugs that **corrupt data, lose data, or
silently report wrong numbers** — not style or hypotheticals.

## Scope selection (do this first)

1. Find the last audit marker: the most recent GitHub issue labeled
   `bug-audit` (`gh issue list --label bug-audit --state all --limit 1`),
   whose body records the commit it audited up to.
2. Primary scope = `git diff <last-audited-commit>..HEAD` plus any file those
   diffs touch. If no marker exists (first run), scope = `backend/*.py` and
   `frontend/src/lib` + `frontend/src/app`.
3. Always include the standing hot-spots regardless of diff:
   `backend/main.py` scan loops, `backend/history_store.py`,
   `backend/scan_cache.py` (if present), anything matching
   `backend/*cache*`/`backend/*store*`.

## Fan-out (Agent tool; run each wave's spawns in parallel)

**Wave 1 — breadth, `audit-scanner` (Sonnet), one per dimension:**
- silent caps & truncation (slices, LIMIT, early breaks, `[:N]`)
- persisted-state integrity (upserts that overwrite, absent-vs-zero
  confusion, stub/partial rows)
- cache & staleness (mtime keys, missing version fields, invalidation gaps)
- timestamp/timezone math (naive datetimes, mtime-as-date, day bucketing)
- trust boundaries (on-disk ids/paths/cwd used in paths, SQL, shell)
- token/cost arithmetic (double counting, high-water-mark vs sum, unit slips)

Give each scanner the scope file list and its dimension. Prompt them to
return the FINDING-block format their agent definition specifies.

**Wave 2 — depth, `audit-deep` (Opus), in the same parallel batch as wave 1:**
one per risky subsystem actually present in scope, typically 2-4 of:
- scan → cache → history-upsert pipeline (the PR #131 path)
- one agent-store parser that changed recently (Claude, Codex, Copilot…)
- any new persisted format introduced since the last audit
- the analytics aggregation path (`/analytics`, ecosystem rollups)

**Wave 3 — verification, `audit-verifier` (Opus), one per candidate:**
Dedupe wave 1+2 candidates by (file, defect) first. Send each survivor to a
verifier with the full finding block. Only `VERDICT: CONFIRMED` findings
survive; keep the verifier's own severity, not the scanner's.

## Output

1. Write the report to `docs/audits/<YYYY-MM-DD>-bug-audit.md`: audited
   range (`<from>..<to>` commits), confirmed findings (severity, file:line,
   scenario, verifier's reason), refuted-candidate count, dimensions that
   came back clean.
2. File one GitHub issue per confirmed **critical or high** finding:
   `gh issue create --label bug,bug-audit` — title is the one-sentence
   defect, body is the finding block + verifier reason + audited commit.
   Medium findings go only in the report.
3. Always file/update the audit-marker issue: a single issue titled
   `bug-audit marker` labeled `bug-audit` whose body's last line is
   `audited-through: <HEAD sha>` (edit it if it exists, create otherwise).
4. Commit the report on a branch `audit/<YYYY-MM-DD>` and open a draft PR
   (report only — never commit fixes from this skill; fixes are separate,
   human-initiated work).

## Weekly cadence

Run manually with `/bug-audit`, or schedule headless:

```bash
# launchd/cron, weekly:
cd /path/to/tokentelemetry && claude -p "/bug-audit" --permission-mode acceptEdits
```

Budget note: one run spawns roughly 6 Sonnet scanners + 2-4 Opus deep
auditors + one Opus verifier per candidate. If candidates exceed ~15, verify
only critical/high candidates and list the rest as unverified in the report.
