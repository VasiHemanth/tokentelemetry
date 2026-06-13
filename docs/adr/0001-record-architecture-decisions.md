# ADR-0001: Record architecture decisions in the repo

- **Status:** Accepted
- **Date:** 2026-06-13
- **Deciders:** VasiHemanth
- **Related:** [TokenTelemetry Roadmap board](https://github.com/users/VasiHemanth/projects/1)

## Context

TokenTelemetry is a solo-maintained, local-first project with a growing community
on GitHub Issues/Discussions. There is no Jira/Linear and a strong preference to
stay on free, GitHub-native tooling. The recurring pain: months after a feature
ships, it's hard to reconstruct *why* it was built a certain way, and therefore
risky to change or revert it. We need a durable record of decisions that cannot
drift out of sync with the code.

## Decision

We will keep **Architecture Decision Records** as markdown files under `docs/adr/`,
one per significant decision, each committed **in the same PR as the code it
describes**. A GitHub Projects board tracks *work*; the repo holds the *decisions
and designs*; each board card links to its ADR. Discord is for community/support
only, never as a decision record.

## Alternatives considered

- **Google Sheets / external doc** — drifts from the code, no link to commits,
  manual upkeep. Rejected.
- **Linear / Jira** — another silo to keep in sync; overkill and not free for a
  solo maintainer. Rejected for now.
- **Only the board / draft-issue bodies** — not versioned with the code, invisible
  to `git blame`, can't be reverted alongside a PR. Rejected as the system of record.
- **GitHub Wiki** — separate git history from the code; a doc and its
  implementing commit can't travel together. Rejected in favour of in-tree docs.

## Consequences

- ✅ Every decision is versioned with the code and discoverable via `git blame`,
  the PR, and the board card — so backtracking is "revert the PR, read the ADR".
- ✅ Zero new tools or cost; works offline, matches the local-first ethos.
- ⚠️ Requires discipline: an ADR (and design doc, where relevant) must be written
  as part of each feature PR. This is mirrored by the existing UPDATE.json hook habit.
- 🔁 To undo: stop writing ADRs and delete `docs/adr/` — but the existing records
  remain useful history regardless.
