# Design: the TokenTelemetry plugin (per-project second brains + generated optimization skills)

**Status:** PROPOSED · **Author:** analysis (3-agent debate, 2026-07-03/04) · **Date:** 2026-07-04
**Related:** `docs/wiki/` + `.claude/skills/brain/SKILL.md` (the proven seed, PR #121) ·
[[local-first-no-user-network]] · [[second-brain-wiki]] · the "master prompt v2"
resumable-compile design (Verizon/BQ project) · token-efficiency panel analysis
(session 2026-07-04)

---

## 1. Problem and thesis

Generic token optimizers (ponytail, caveman, headroom; see §2) all optimize *within*
a turn: less code out, terser prose out, smaller payloads in. None of them touch the
largest residual sink in agentic work: **cross-session re-derivation**. Every fresh
session rebuilds the agent's mental model with 10-20 exploratory tool calls, re-carries
that context on every later turn, and repeats wrong turns it has already taken. Prompt
caching does not cross sessions. For non-coding projects (data analysis, legal,
learning) the generic tools do nothing at all: there is no code for a decision ladder
or tree-sitter to act on.

Thesis: ship a **Claude Code plugin** ("tokentelemetry") that

1. compiles a per-project llm-wiki / Google OKF v0.1 knowledge bundle ("second brain")
   from project files and git history, with domain-aware profiles, and
2. generates a per-project optimization skill on top of the wiki, applying
   ponytail/caveman/headroom principles instantiated with project nouns, and
3. closes the loop with the TT dashboard, which detects the wiki and shows honest
   before/after token metrics per project.

The dashboard stays read-only. Everything that writes into a user's repo is a plugin
command the user invokes in their own agent. This split is load-bearing: TT's brand is
the trustworthy local meter, and the plugin must not spend that trust.

The moat is (3). Every optimizer in this space asserts its savings; headroom, with
full request interception, can still only estimate counterfactuals with confidence
intervals. TT observes real longitudinal per-project data on both sides of wiki
adoption. We can prove or falsify the savings claim, including showing zero.

## 2. Prior art (source: maintainer-supplied research, 2026-07)

- **ponytail** (DietrichGebert): prompt-injected "lazy senior dev" persona with a
  7-rung decision ladder (YAGNI → reuse codebase → stdlib → platform-native →
  installed deps → one-liner → minimal code). ~54% less generated code. Two lessons we
  inherit as hard requirements: naive "prefer less" prompts strip validation, so
  explicit negative constraints are mandatory; and deliberate shortcuts get annotated
  with an upgrade path.
- **caveman** (JuliusBrussee): telegraphic output style, ~65-75% output prose cut,
  code byte-exact, no invented abbreviations (BPE-aware). Lesson we inherit:
  **auto-clarity**, full prose is forced for security warnings, irreversible actions,
  and deliverables. Also `caveman-compress`: permanent telegraphic rewrite of memory
  files (~46% baseline input cut).
- **headroom** (headroomlabs-ai): input-side compression middleware with type-routed
  compressors and lossless cache-and-retrieve pointers. Lessons we inherit: the
  `learn` module (mine past sessions for waste loops, write guardrails to memory) and
  the CacheAligner warning (rewriting history breaks provider KV-cache discounts;
  keep stable prefixes stable).

The wiki composes with all three rather than competing: it removes turns, they
compress the turns that remain.

## 3. Decisions (summary)

| # | Decision | Why |
|---|----------|-----|
| D1 | Generation lives in a plugin, not the dashboard | TT stays read-only; blast radius and trust |
| D2 | Session mining extracts **structural signals only**, never transcript content | Content mining is a laundering pipeline from gitignored logs into committed pages; semantic leaks are unredactable at solo-maintainer confidence |
| D3 | Ship 2 proven domain profiles (fullstack-app, research-data) + a generic fallback + a profile-authoring guide | Legal/learning profiles would ship untested by construction; confident garbage pages are structurally privileged over ground truth |
| D4 | The resumable compile machinery (disk-backed queue, batches, checkpoints) is v1 scope | The BQ compile proved the job does not fit one session; a one-shot skill dies mid-compile |
| D5 | Generated skills carry lint-enforced anti-compounding invariants (§7) | Stale wiki + wiki-first routing + laziness + terseness each suppress the correction mechanism the previous layer needed |
| D6 | Dashboard "import" = detection + registration in `~/.tokentelemetry`; conversion/adoption is a plugin command | Read-only rule; see scenario matrix §8 |
| D7 | Loose coupling via `docs/wiki/manifest.json` | Either product works without the other |

## 4. Plugin anatomy

Marketplace repo `tokentelemetry-plugin`. Four skills, four subagents, four
stdlib-Python scripts, no hooks in v1 (nothing may tax every session of every
project; all opt-in).

```
tokentelemetry-plugin/
├── .claude-plugin/plugin.json
├── skills/
│   ├── brain/SKILL.md            # ingest | query | lint | adopt (reads project BRAIN.md)
│   ├── brain-init/
│   │   ├── SKILL.md              # Phase 0: census → profile proposal → scaffold
│   │   └── templates/            # BRAIN.md.tmpl, project-profile.md.tmpl, wiki skeleton
│   ├── brain-compile/SKILL.md    # resumable compile loop (master prompt v2, generalized)
│   └── skillsmith/
│       ├── SKILL.md              # drafts the per-project optimization skill
│       └── seeds/                # ponytail-ladder.md, caveman-style.md, headroom-guardrails.md
├── agents/
│   ├── source-reader.md          # files → condensed facts (fixed schema, word cap)
│   ├── session-miner.md          # one session's slim event stream → structural signals
│   ├── git-historian.md          # decision-shaped commits, per-file churn → topics
│   └── wiki-auditor.md           # semantic lint (contradictions, staleness)
├── profiles/
│   ├── fullstack-app.yaml
│   ├── research-data.yaml
│   ├── generic.yaml
│   └── AUTHORING.md              # third parties own the risk of their own domains
└── scripts/
    ├── okf_lint.py               # deterministic OKF checks (port of the existing lint)
    ├── profile_census.py         # extension histogram, framework markers → JSON
    ├── session_scan.py           # harness log locator + slim parsers (structural only)
    └── wiki_manifest.py          # writes/updates docs/wiki/manifest.json
```

Project-side state (written by the plugin, committed in the user's repo):
`docs/wiki/{BRAIN.md, project-profile.md, manifest.json, index.md, log.md, <pages>}`
plus working state in `docs/wiki/.compile/{compile-queue.md, mining/}`.

Key generalization: the current `.claude/skills/brain/SKILL.md` hardcodes TT's schema.
In the plugin, per-project schema (page types, extraction rules, conventions) moves to
a generated `docs/wiki/BRAIN.md` in each project; the plugin skills read it. Step 1 of
the build is porting `/brain` to this form and verifying it reproduces today's
behavior on the TT repo exactly.

## 5. Domain profiles (data, not prompts)

One compile skill consumes `profiles/*.yaml`. Each profile defines:

- `detect`: census signals (`package.json + backend/*.py` → fullstack-app;
  high `.sql`/`.ipynb` density → research-data; `.md`/`.pdf` dominant, no build
  files → generic).
- `page_types`: `{type, directory, one_page_per}` rows; becomes the generated
  BRAIN.md schema table.
- `extraction`: per-filetype rules (`{glob, extract, ignore}`).
- `source_priority`: which sources seed the queue first (ADRs > CLAUDE.md > code
  for apps; docs > SQL > notebooks for research).
- `escalation`: the ladder (too big → subagent; ambiguous → queue-mark
  `needs-human`, never guess; contradiction → Finding in log.md).
- `redaction`: hard rules. research-data carries "knowledge never data" verbatim:
  schemas, meanings, aggregate conclusions yes; row values, PII, anything
  subscriber- or site-identifying never.

Reference instantiations: **TokenTelemetry** → fullstack-app (page types
harness/subsystem/feature/decision/playbook/convention, i.e. exactly today's wiki).
**BQ research project** → research-data (dataset-table/metric/analysis/query-pattern/
decision/gotcha; `.sql` → intent + lineage + joins, BQ metadata → schema +
partitioning, `.csv` → column semantics only, `.ipynb` → conclusions not cell
outputs).

Phase 0 (`/brain-init`) always proposes and the user confirms; detection is a
proposal, not a verdict. The confirmed result is saved to `project-profile.md` so it
never re-asks.

## 6. The compile loop and session mining

`/brain-compile` adapts the proven master-prompt-v2 design:

1. **Seed** `compile-queue.md` from profile source-priority census, git-historian
   topics, session-mining aggregation, and (optionally) the TT dashboard's top
   re-read files. Items: `- [ ] path|topic | kind | gist | priority`.
2. **Per batch** (3-6 pages by topic): fan out source-readers per extraction rules;
   write/update pages against BRAIN.md; regenerate index.md; append log.md; run
   `okf_lint.py`; commit (`docs:` prefix); check off queue items with the commit hash.
3. **Wiki-as-context after batch 1**: later batches read index.md + adjacent pages
   first; update rather than duplicate.
4. **Checkpoint rule**: on context pressure, stop cleanly at a batch boundary and
   tell the user to rerun `/brain-compile`. Resume = read queue, continue at first
   unchecked batch. Survives context exhaustion, session death, multi-day gaps.
5. The manifest records `status: compiling|complete` and batch progress. Generated
   skills refuse wiki-first routing while status is `compiling` (a half wiki must
   never be silently trusted as complete).

**Session mining (structural signals only, D2).** Past sessions are mined for:
file-read frequencies (page priority signals), repeated error-loop signatures and
retry patterns (guardrail candidates), file co-occurrence (topic clustering), tool
call mix. `session_scan.py` locates this project's logs (Claude Code JSONLs
first-class; other harnesses later and behind a flag), emits slim event streams;
session-miner subagents return fixed-schema notes, hard-capped, extract-and-discard.
**Never extracted:** transcript prose, user messages, tool outputs, data values.
If content-shaped mining ever ships, output goes to a gitignored scratch file the
user promotes by hand; nothing content-derived flows directly into committed pages.

## 7. Generated optimization skills (/skillsmith)

A generated skill is one SKILL.md derived deterministically from wiki + profile +
mined waste evidence. Its value is entirely in project-noun specificity; every rule
names a real artifact (a page path, a helper module, a validated query). Sections:

1. Frontmatter + trigger, modes lite/full/ultra.
2. **Knowledge routing (wiki-first)**: question class → page path, plus the negative
   form ("never re-derive what a page answers; stale page → flag for `/brain
   ingest`, do not silently re-explore").
3. **Decision ladder**, 5-9 rungs, domain-adapted; the unit of reuse differs
   (helper functions vs validated queries vs templates).
4. **Cost model**: what is being optimized, in priority order. For research-data,
   BigQuery bytes billed can dominate LLM tokens, so the ladder reorders around
   dry-run gating. The framework generalizes to any metered resource.
5. **Output style + auto-clarity boundaries**: telegraphic defaults with an
   enumerated, project-specific full-prose list (TT: auth changes, UPDATE.json copy;
   BQ: analysis writeups, statistical claims, cost-incurring confirmations).
6. **Learned guardrails** (headroom-learn style, behavior only, never data values).
7. **Cache hygiene**: stable prefixes, no mid-session CLAUDE.md churn.
8. **Hard negative constraints + escape hatch**.

Abbreviated reference sketches (full versions in the analysis session):

```markdown
# tt-optimize (fullstack-app)
Routing: orientation → docs/wiki/index.md; harness formats → harnesses/<x>.md
(never re-open ~/.claude fixtures); internals → subsystems/; process → playbooks/.
Ladder: needed at all? → existing scanner helper? → stdlib/framework? → installed
dep (NO new deps without asking; issue #91)? → minimal code, honest n/a over
estimates. Full prose required: RemoteAuthMiddleware/CORS changes, UPDATE.json copy,
error-hint text. Guardrails: day buckets are LOCAL days; confirm fresh .next before
validating. Never optimize away: trust-boundary validation, middleware ordering,
the 3-layer error-category rule.
```

```markdown
# bq-research-optimize (research-data)
Cost model: BigQuery bytes billed FIRST, LLM tokens second.
Routing: table questions → wiki/tables/<t>.md (never run a discovery query a page
answers); prior computations → wiki/queries/ validated snippets; definitions →
wiki/metrics/.
Ladder: validated snippet exists? → INFORMATION_SCHEMA/table page instead of
scanning? → dry-run FIRST, report est. bytes, stop over cap (default 10 GB) →
always partition filter, never SELECT *, LIMIT does not cut cost → shape in Python,
not re-queries.
Redaction: pages and this skill state shapes/schemas/distributions, NEVER row
values, PII, sample records, or query results.
Full prose required: analysis writeups, caveats, significance claims.
```

**Anti-compounding invariants (lint-enforced; generation fails without them):**

- The wiki is a **map, not testimony**: use it to find sources; cite only sources
  for anything user-visible.
- Every page carries the git SHA it was compiled from; pages whose `resource:`
  sources changed since compile are untrusted (cheap `git diff --stat <sha>` check).
- Distrust triggers: wiki-vs-file contradiction, user correction, failing check →
  raw-source mode for that topic.
- Domain verify-floors that laziness cannot override: numbers get recomputed
  (the repo's "verify before reporting done" rule, exported); nothing ships on wiki
  authority alone.
- ponytail's negative-constraint section and caveman's auto-clarity floor are fixed
  template blocks, never removable.
- Diff-before-install: a skill is prompt injection into every future session;
  silent install is unacceptable.
- Regenerable, never hand-tuned: generated-by header with wiki SHA + profile
  version; the fix path is edit wiki/profile → regenerate.
- "When this skill is wrong" escape note, always present.
- Size budget ~1.5k tokens (lite): the skill is overhead paid every session.

## 8. Wiki lifecycle in the TT dashboard: detection, import, scenarios

The dashboard's per-project section gains a **Knowledge** card. TT never writes into
the user's repo: "import" means *detect + validate + register*, with registration
state in `~/.tokentelemetry` (config/history.db), like an Obsidian vault registry.
Anything that converts or writes is a plugin command the card only tells you to run.

Detection (scanner-side, reusing the existing project-dir walk that already powers
skills scanning): `docs/wiki/manifest.json` (first-class), OKF-ish signals
(index.md + log.md + frontmatter `type:` fields), Obsidian markers (`.obsidian/`),
generic markdown-wiki shapes. Docs *sites* (mkdocs/docusaurus/API docs) are
recognized and excluded: a rendered docs site is not a second brain.

Validation tiers:

| Tier | Signals | What it unlocks |
|------|---------|-----------------|
| Full OKF | manifest + frontmatter + index | Health card, staleness checks, before/after measurement, /skillsmith |
| Partial | markdown wiki, links resolve, no/partial frontmatter | Registration + measurement only; card suggests `/brain adopt` to unlock routing skills |
| Not a wiki | docs site, auto-generated API docs | Not offered |

Scenario matrix:

| # | Scenario | Dashboard behavior | Plugin action offered |
|---|----------|--------------------|-----------------------|
| S1 | No wiki exists | Knowledge card shows the project's waste metrics (top re-read files, exploration share) + "Build a second brain" CTA | `/brain-init` (the waste metrics seed the compile queue) |
| S2 | Plugin-built wiki (manifest present) | Auto-registered. Health card: page count by type, last updated, staleness badge, before/after token trend split at `manifest.created` | `/brain ingest` on staleness |
| S3 | Hand-built OKF-ish wiki, no manifest (e.g. TT's own docs/wiki today) | "Detected knowledge base at docs/wiki. Register it?" → user confirms → registered (Partial or Full tier) | `/brain adopt`: generate manifest, fill frontmatter gaps, rebuild index; shown as a diff |
| S4 | Obsidian vault inside the repo (`.obsidian/` present) | Same as S3, plus link-style caveat: `[[wikilinks]]` don't resolve for plain-markdown agents | `/brain adopt` converts wikilinks → relative links (or emits an alias map); suggests gitignoring `.obsidian/` |
| S5 | External wiki/vault outside the repo | User supplies the path; registered as external; measurement works | Generated skill routes via absolute path; card recommends moving/symlinking into the repo for portability. TT never copies content |
| S6 | Multiple candidates (docs/wiki + a vault) | Picker; exactly one primary per project | Others can be registered as secondary (measured, not routed to) |
| S7 | Compile in progress (queue has unchecked items / manifest `status: compiling`) | Progress: "4 of 9 batches, last commit <sha>", resume command shown | `/brain-compile` to continue; generated skills refuse wiki-first mode until complete |
| S8 | Stale wiki (manifest SHA far behind HEAD; resource files changed) | Staleness badge with the count of affected pages | `/brain ingest` (or recompile if drift is large) |
| S9 | Registered path disappeared (moved/deleted) | Marked unlinked; historical before/after boundary retained; asks user to re-point or forget | Re-register or `/brain-init` fresh |
| S10 | User declines ("this project doesn't need one") | Choice recorded; card collapses to metrics only, never re-prompts | n/a |

Monorepos: registration is per TT-project (per scanned cwd); a shared root wiki may
be registered by several projects, and per-package wikis win over a root wiki when
both exist (closest-ancestor rule, mirroring the profile confirmation step).

## 9. Measurement loop (the honest part)

With a registration date (S2/S3) or manifest.created, TT splits per-project metrics
into before/after: input tokens/session, cache-hit ratio, exploration-tool share,
top re-read files (once the scanner extracts file paths), cost/week. Framing is
**observational trend, never causal claim**, with a visible confound disclosure
(model switches, segment by `models_used`; harness updates; task-mix change; pricing
changes; excluded estimated-input harnesses). Showing a zero or negative delta is a
feature: it is the honesty that differentiates this loop from every optimizer's
self-reported savings.

## 10. Build order

| Step | What | Notes |
|------|------|-------|
| 1 | Port `/brain` to plugin form; TT-specifics → generated BRAIN.md | Must reproduce today's behavior on this repo exactly |
| 2 | `okf_lint.py`, `profile_census.py`, profiles, `/brain-init` | Test detection on TT and the BQ repo |
| 3 | `/brain-compile` (files + git only) | Dogfood: full compile of a third, wiki-less project |
| 4 | Structural session mining (Claude Code JSONLs first) | TT's scanner code is the parsing reference |
| 5 | `wiki_manifest.py` + TT-side detection + Knowledge card (S1-S10) | Separate TT PR; enables before/after |
| 6 | `/skillsmith` | Last: needs a mature wiki + mining evidence to beat generic advice |

## 11. Explicitly cut (the never list)

- TT-the-dashboard writing wikis or skills into user repos, ever.
- Transcript-content mining into committed pages (D2).
- Untested domain profiles shipped as first-class (D3).
- One-shot in-session compilation without the queue (D4).
- Runtime LLM calls or any new outbound network from the dashboard
  ([[local-first-no-user-network]]).
- Causal "the wiki saved you X tokens" claims (§9).

## 12. Addendum (2026-07-05, shipped in plugin v0.2.0): discovery, reuse, intake

Three gaps found after the pcr-divergence dogfood, closed in the plugin repo:

1. **Agent discovery.** A compiled wiki nobody's agents know about saves no
   tokens. `scripts/agent_context.py` writes a stable pointer block (markers
   `tokentelemetry-brain:start/end`) into `AGENTS.md` (created if missing) and
   any existing `CLAUDE.md`; brain-compile's completion step offers it once the
   manifest reaches `complete`. The block carries no counts or SHAs, so it
   never churns between compiles (cache hygiene), and rewrites idempotently
   between its markers only.
2. **Prior-knowledge reuse.** `profile_census.py` now reports a
   `prior_knowledge` list: graphify graphs (`graphify-out/graph.json`),
   Obsidian vaults, ADR dirs, design docs, wiki-shaped trees. `/brain-init`
   asks seed-or-ignore per source and records the choice in
   `project-profile.md`; `/brain-compile` reads recorded seeds first (graph
   clusters become queue topics and per-topic reader assignments). Seeds are a
   map, not testimony: pages are still grounded by reading files. Honest
   framing: seeding cuts discovery cost, it does not make compilation free.
3. **Intake tray.** `docs/wiki/raw/` is the committed inbox for knowledge with
   no repo home (external notes, pasted docs), completing the llm-wiki raw
   layer for non-repo sources. `/brain ingest` sweeps it: distill into pages,
   then move the file to `raw/processed/` (content immutable, moved not
   edited). `okf_lint.py` exempts `raw/**` from page checks but warns on
   unprocessed items; queries never read raw/ (pages stay the only query
   surface, or the token savings leak).
