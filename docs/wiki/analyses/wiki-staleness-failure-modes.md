---
type: Analysis
status: adopted
title: Wiki staleness failure modes and the update-nudge design
description: Eleven-agent simulation of how a compiled wiki fails after code drift, what can go catastrophically wrong, and a harness-agnostic design for suggesting (never auto-running) ingest.
tags: [plugin, staleness, ingest, nudge, multi-harness, security, simulation]
timestamp: 2026-07-06
resource: docs/design/tokentelemetry-plugin.md
---

# Wiki staleness failure modes and the update-nudge design

Status 2026-07-06: adopted, with the maintainer's refinement that stale
pages FALL BACK to source (wiki-as-cache) instead of demanding updates.
Shipped as plugin v0.5.0 commit `060b674`: `wiki_manifest.py stamp`
(content-hash provenance) + self-contained `docs/wiki/status.py`
(FRESH/STALE/TAMPERED/UNVERIFIABLE, --note refresh queue), hardened by a
4-role agent review; rolled out to this wiki and education_video.

Saved from a maintainer chat, 2026-07-06. Trigger: a real incident — the
maintainer merged code changes, forgot `/brain ingest`, and later got a
confidently stale answer with no warning anywhere. The ask: design a dynamic
suggestion (never an auto-ingest) that works in any harness, and stress-test
the whole approach for what can go wrong and what can go crazy-high.

## Method

A workflow ran 6 persona simulations (forgetful maintainer, Codex-only user,
new collaborator on a 3-month-stale wiki, unattended cron bot following a
playbook, heavy trusting querier, and a counterfactual world where ingest IS
auto-run) followed by 5 adversarial critics (staleness/correctness, cost
runaway, nudge UX, security/injection, multi-harness reality). 11 agents,
~66 findings; agents verified claims against the real bundle.

## Verified today, in this repo's own wiki

- `docs/wiki` has **no manifest.json**, so the pointer block's only trust
  gate ("trust while manifest status: complete") evaluates to nothing.
- **Zero pages carry `compiled_from_sha`** (the adopted bundle predates it),
  so no sha-based staleness check has anything to key on.
- **6/6 playbooks and 3/5 conventions have no `resource:`** — the
  "confirm the page's resource file" rule is structurally inapplicable to
  exactly the pages agents execute.
- Three pages share `resource: backend/main.py` (~7k lines), so honest
  verification costs ~70k tokens and file-level staleness cries wolf.

## Top failure modes (converged across agents)

1. **Stale wiki is worse than no wiki: agents revert code to match it.**
   The pointer block makes the wiki primary evidence; a stale page outranks
   fresh code, so the agent "fixes" the port back, recreates a renamed
   module, or resurrects a moved config file at its old path (silent no-op
   edits on pricing). Phantom-debug loops cost ~100x the original question,
   sometimes across multiple harnesses chasing the same ghost.
2. **The trust gate never flips on drift.** `status: complete` means
   "compile finished", not "still true"; a 3-month-stale bundle passes every
   check the system defines. Staleness detection exists only in the
   dashboard, which nobody opens mid-session.
3. **Drift is created where the repair path doesn't exist.** Code changes
   happen in Codex/Cursor/OpenCode sessions; `/brain ingest` is a Claude
   Code skill. Detection in those harnesses dead-ends, so users hand-edit
   pages, which forges provenance and permanently masks the staleness.
4. **Executed pages are the blind spot.** Playbooks (followed verbatim,
   including by unattended bots) carry no provenance at all. Worst case
   simulated: a cron bot follows a stale playbook whose flag semantics
   changed and force-publishes unreviewed HEAD at 2am.
5. **The wiki is a cross-harness prompt-injection channel.** The pointer
   block grants pages instruction-level trust in every harness; one poisoned
   or hand-edited page becomes persistent, repo-committed injection.
   Provenance is self-asserted frontmatter, so a forged
   `compiled_from_sha` is undetectable without a content hash.
6. **Cost runaways.** Deferred catch-up ingest of a 30-merge backlog is a
   non-resumable token furnace; staleness nudges convert into reflexive
   full recompiles (2-8M tokens/month steady state); ingest bumps
   `timestamp` but never re-stamps `compiled_from_sha`, so a sha-keyed
   nudge would nag forever after a successful ingest.
7. **Auto-ingest (the rejected design) is confirmed bad.** Simulated week:
   vendored-diff token furnace, a briefly-committed secret laundered into
   permanent wiki prose, mid-refactor states distilled as truth with fresh
   stamps (undetectable staleness), commit spam re-triggering push gates,
   manifest races across harnesses, and a self-triggering ingest loop on
   its own docs(wiki) commits.

## Nudge anti-requirements (what the critics killed)

- **Not session-start wallpaper**: with 13 pages keyed to `main.py`, "N
  files changed" fires on every merge and becomes noise before the first
  real incident. Fire at point of use, per page.
- **Not model-rendered**: an instruction asking each agent to compute sha
  distance is skipped under exactly the economic pressure the wiki creates.
  The computation must be a script whose output lands in the transcript.
- **Not commit-sha-keyed**: squash-merges, rebases, 21 worktrees, and gc
  invalidate `compiled_from_sha` comparisons. Key on content hashes of
  resource blobs.
- **Not a writable ledger**: a pending-ingest file forks per branch and
  races across concurrent harness sessions. Recompute statelessly; the only
  committed marker is CI-written on main (single writer).
- **Not git hooks as the trigger**: merges happen on GitHub's servers;
  fetch has no hook. Local post-merge hooks fire approximately never in
  this workflow.
- **Silence must not certify freshness**: the check's output must always
  enumerate its blind spots ("9 pages have no provenance and cannot be
  checked").

## Recommended design (suggestion, never auto-run)

1. **Fix the data model first** (prerequisite, cheap): `resource:`
   mandatory on every page type including playbooks (multiple resources
   allowed; narrow anchors like `file#symbol` for giant files);
   `/brain lint` fails without it; manifest records per-page
   `sha256(resource blob)` and `sha256(page body)` written only by /brain
   workflows; ingest re-stamps provenance on every touched page.
2. **One committed, stateless, stdlib check script** (e.g.
   `docs/wiki/status.py`, installed by compile): recomputes per-page
   freshness from content hashes, flags hand-edits (page-hash mismatch =
   tamper), always prints blind spots, and ends with one copy-pasteable
   next step. Works identically in every harness that can run shell.
3. **Pointer block carries one stable indirection**: "before answering
   from or acting on a wiki page, run `python3 docs/wiki/status.py
   [page]`" — all volatile logic lives in the script, so the nudge itself
   cannot go stale.
4. **Point-of-use trust demotion**: a page listed as suspect flips the
   evidence hierarchy — code is authoritative, never edit code to match a
   suspect page; pages tagged `security` are always verified regardless of
   freshness; pages get reference trust, never instruction trust.
5. **A legal escape hatch for non-Claude harnesses**: never hand-edit;
   drop a one-line note into `docs/wiki/raw/` (the inbox that already
   exists and ingest already sweeps): "STALE: <page> contradicts
   <resource> at <sha>". Detection becomes durable without a new write
   channel.
6. **CI marker on main**: a GitHub Action on push-to-main runs the same
   script and commits a small STALENESS marker, catching the drift that
   arrives by remote merge, with exactly one writer.
7. **Ingest catch-up mode**: no-argument `/brain ingest` derives the
   backlog per page (resource hash mismatch), presents a ranked per-page
   repair list with token estimates, and processes it as a resumable
   queue — the anti-recompile.

## Follow-ups

- Implement 1-3 in the plugin (lint rules, status.py, template pointer
  line); 5 is a pointer-block text change; 6 is a workflow file the
  installer offers.
- TT's own wiki needs the data-model backfill (manifest + provenance) via
  a /brain maintenance pass before any of this can protect it.
- Skillsmith relation: the routing win (page map in pointer) stays; the
  status.py line becomes the second fixed line of the pointer block.

## Related

- [Multi-harness session mining for the plugin](multi-harness-session-mining.md):
  same multi-harness constraint, solved with adapters; the nudge reuses its
  "committed text + plain files are the only universal transports" lesson.
- [Prove the brain saves tokens](../ideas/prove-brain-token-savings.md):
  the measured 12/12 adherence is what makes staleness dangerous — agents
  now actually read the wiki.
