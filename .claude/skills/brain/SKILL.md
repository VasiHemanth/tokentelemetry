---
name: brain
description: Maintain the project second brain at docs/wiki/ (an OKF v0.1 bundle). Use for /brain ingest <source>, /brain query <question>, /brain lint. Trigger whenever knowledge should be filed into or answered from the wiki.
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

New types are allowed when nothing fits; add them to this table in the same PR.

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
