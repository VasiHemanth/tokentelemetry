---
type: Analysis
title: graphify vs the tokentelemetry plugin
description: "Comparison of the graphify knowledge-graph skill and the tokentelemetry second-brain plugin: cousins, not twins; a map vs a field guide, and how they compose."
resource: docs/design/tokentelemetry-plugin.md
tags: [analysis, knowledge-base, graphify, plugin, token-optimization]
timestamp: 2026-07-05
status: proposed
---

# graphify vs the tokentelemetry plugin

Question: is graphify (the `/graphify` skill installed on this machine) the
same thing as the tokentelemetry plugin's second-brain workflow, and should
they interact?

## What each builds

**graphify** extracts a knowledge graph automatically: thousands of small
nodes (functions, concepts, papers, images) and typed edges (calls, cites,
semantically-similar-to), via AST parsing for code plus parallel subagent
extraction for docs. It clusters the graph into communities, labels them, and
outputs an interactive HTML map, a report, and query commands (BFS/DFS
traversal, shortest path). Bottom-up: structure emerges from clustering. Its
special trick is surprise, connections between files nobody thought to ask
about.

**The tokentelemetry plugin** compiles a knowledge wiki: a few dozen curated
prose pages (subsystems, decisions, gotchas, playbooks) with typed OKF
frontmatter, an index, and a log. Top-down: a domain profile decides the page
types, and structural session mining decides which pages to write first (in
this repo, `backend/main.py` re-read 71 times across 9 sessions is the page
priority signal). On top, `/skillsmith` generates a per-project skill that
routes the agent to pages instead of re-exploring, and the TT dashboard
measures before/after token use.

## Real overlaps

Both are Karpathy-lineage (graphify cites the /raw folder workflow, ours the
llm-wiki pattern). Both fan out subagents to read the corpus. Both keep
resumable, incremental state on disk. Both carry honesty rules (graphify tags
every edge EXTRACTED/INFERRED/AMBIGUOUS; the wiki requires every fact grounded
in a named source). Both target token reduction. graphify even has a `--wiki`
flag, but it auto-generates one article per cluster rather than curated typed
pages.

## Key differences

| | graphify | tokentelemetry plugin |
|---|---|---|
| Knowledge shape | graph: 1000s of nodes and edges | wiki: ~40 curated typed pages |
| Structure decided by | clustering algorithm | domain profile + maintainer |
| Best at answering | "what connects to what?" | "what does this mean, what did we decide, what bit us before?" |
| Uses past chat sessions | no | yes (structural signals set page priorities) |
| Generates an optimization skill | no (a CLAUDE.md note at most) | yes: ladder, guardrails, staleness checks |
| Proves savings | one-shot benchmark estimate | dashboard before/after on real sessions |
| Dependencies | pip package (networkx, whisper, ...) | stdlib scripts + prompts |

## Conclusion

A map vs a field guide. The map shows every road and where they cross; the
field guide says which roads matter, why, and where the potholes are. They
compose rather than compete.

Proposed follow-ups (not implemented):

1. Run graphify on a new codebase for orientation, then `/brain-init` +
   `/brain-compile` for the durable second brain.
2. Feed graphify's god nodes into the `/brain-compile` queue as page
   candidates (a third seeding signal next to git history and session
   mining).
3. Optionally point graphify at `docs/wiki/` itself to visualize the wiki's
   link structure beyond what Obsidian shows.
