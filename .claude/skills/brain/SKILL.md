---
name: brain
description: Maintain the project second brain at docs/wiki/ (an OKF v0.1 bundle). Use for /brain ingest <source>, /brain query <question>, /brain save <analysis>, /brain idea <rough idea>, /brain lint. Trigger whenever knowledge should be filed into or answered from the wiki.
---

# brain — TokenTelemetry second brain maintainer

You are the maintainer of the project wiki at `docs/wiki/`. It is an
[Open Knowledge Format v0.1](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
bundle following Karpathy's llm-wiki pattern: raw sources stay immutable, the
wiki compiles them, this file is the schema that keeps you disciplined.

## Layers

1. **Raw sources (never edit as part of wiki work):** code, `DESIGN.md`,
   `docs/adr/`, `docs/design/`, `.claude/CLAUDE.md`, `CHANGELOG.md`,
   `UPDATE.json`, `website/content/docs/`, GitHub issues/discussions/PRs.
2. **Wiki (you own every file):** `docs/wiki/**`. Never hand-edited by humans;
   humans edit sources, you recompile.
3. **Schema:** this file.

## Bundle rules (OKF v0.1)

- Every concept page has YAML frontmatter. `type` is required; also set
  `title`, `description` (one sentence), `tags`, `timestamp` (ISO 8601 date of
  last meaningful change), and `resource` (repo-relative path or URL of the
  primary source) when one exists.
- Concept ID = path minus `.md` (e.g. `harnesses/claude-code`).
- Links are normal markdown, relative within the bundle. Tolerate broken links
  when reading; never create them when writing.
- `index.md` (no frontmatter): grouped directory listing,
  `* [Title](path.md) - description` per entry, descriptions mirroring each
  page's frontmatter `description`. Regenerate whenever pages are added,
  removed, or re-described.
- `log.md`: newest-first `## YYYY-MM-DD` sections; prose entries starting with
  a bold action word (**Creation**, **Update**, **Deprecation**, **Finding**).

## Page types

| type | directory | one page per |
|------|-----------|--------------|
| Harness | `harnesses/` | supported agent (data dirs, parsed signals, quirks) |
| Subsystem | `subsystems/` | backend/frontend module (what it does, key files, invariants) |
| Feature | `features/` | user-facing dashboard feature (behavior + gotchas, links to website docs) |
| Decision | `decisions/` | ADR (summary + consequence highlights, `resource:` the ADR) |
| Playbook | `playbooks/` | recurring maintainer task (steps, files touched, traps) |
| Convention | `conventions/` | project rule or invariant (the rule, why, enforcement) |
| Analysis | `analyses/` | analysis produced in an agent chat worth keeping, implemented or not (extra frontmatter: `status: proposed \| adopted \| rejected \| superseded`) |
| Idea | `ideas/` | captured idea, clarified from a rough prompt, not yet assessed or implemented (extra frontmatter: `status: captured \| adopted \| dropped`) |

New types are allowed when nothing fits; add them to this table in the same PR.

Analysis pages differ from the rest: they are point-in-time snapshots of
thinking, not compiled from repo sources. Their body is never rewritten after
saving; later edits may only change `status` (with a one-line note and a link
to what superseded or implemented them) and fix broken links.

## Workflows

### ingest `<diff | file | PR/issue/discussion ref>`

1. Read the source fully.
2. Decide which existing pages it touches (search the wiki first). Prefer
   editing existing pages over creating new ones; create only when a distinct
   concept has no home.
3. Update pages: keep bodies short and factual, cite file paths as
   `backend/main.py` style code spans, cross-link related pages.
4. Bump `timestamp` on every touched page. Update `index.md` if the set or
   descriptions changed. Append one `log.md` entry summarizing the ingest.

After a PR merges to main, the ingest source is `git diff <before>..main`.

### query `<question>`

1. Read `index.md`, follow links to the relevant pages, answer from the wiki.
2. If the wiki couldn't answer and you had to read raw sources, file what you
   learned back into the wiki (same rules as ingest) so the next query hits.

### save `<analysis from this chat>`

For when a conversation produces an analysis worth keeping (a comparison, a
design assessment, a recommendation) that may or may not ever be implemented.

1. Distill the analysis from the conversation into one page under `analyses/`:
   the question it answers, the reasoning, the conclusion, and any proposed
   follow-ups. Keep the substance; drop the chat back-and-forth.
2. Frontmatter: `type: Analysis`, `status: proposed` (or `adopted`/`rejected`
   if the user already decided), plus the usual `title`, `description`,
   `tags`, `timestamp`. Set `resource:` to the main artifact discussed, when
   one exists.
3. Cross-link related wiki pages; add the entry to `index.md` under
   `## Analyses`; append a `log.md` **Creation** entry naming the chat context.
4. Commit as `docs:`. When an analysis later gets implemented or overruled,
   update only its `status` line and add the link; the body stays as written
   (see the Analysis page-type rule above).

### idea `<rough idea>`

For when the user has a spark (a feature, an approach, a "what if") and wants
it kept before it evaporates. The input is rough by nature; your job is to
make it clear, then save it. Ideas are direction, not knowledge: a query must
never present one as how TokenTelemetry works.

1. **Clarify first.** Rewrite the prompt into plain prose: what the idea is,
   the problem it addresses, how it might take shape. Keep the user's intent,
   drop the rambling. If one load-bearing point is genuinely ambiguous, ask
   one question; otherwise do not interrogate.
2. **Confirm.** Show the cleaned-up version and get a quick yes before saving.
   It is the user's idea; make sure clarifying did not distort it.
3. **Dedupe.** Search `ideas/` before writing: a prompt that extends an
   existing idea updates that page (append a dated refinement) instead of
   creating a near-duplicate.
4. One page under `ideas/`: the idea stated clearly, the motivation, a sketch
   of the shape, open questions. Frontmatter: `type: Idea`,
   `status: captured` (move to `adopted` / `dropped`, with a link to whatever
   implemented or killed it, once its fate is known), plus the usual `title`,
   `description`, `tags`, `timestamp`. Set `resource:` only when the idea
   targets a specific existing artifact.
5. Cross-link related pages, add the entry to `index.md` under `## Ideas`,
   append a `log.md` **Creation** entry, commit as `docs:`.

Unlike `save` snapshots, idea pages stay alive: refinements append with a
date, and `status` changes as the idea is adopted or dropped.

### lint

Check and report; fix what's mechanical, list the rest:

- frontmatter parses and `type` is non-empty on every non-reserved page
- links resolve within the bundle
- `index.md` matches the actual file set and descriptions
- contradictions between pages, or between a page and its `resource` source
- stale claims (page older than significant changes to its `resource`)
- orphans (pages nothing links to and index barely explains)

Record findings as **Finding** entries in `log.md`.

## Hard rules

- Facts must be grounded in a source; no invented behavior. When a source is
  ambiguous, say so on the page rather than guessing.
- Never restate whole source documents; summarize and point via `resource:`.
- Wiki changes are `docs:` commits (no UPDATE.json needed).
- Respect repo writing style: plain, terse, no hype, no em-dashes.
