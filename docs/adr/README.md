# Architecture Decision Records (ADRs)

This folder holds the **why** behind TokenTelemetry's architecture — one short file
per significant decision, written *when the decision is made* and committed in the
same PR as the code that implements it.

An ADR is not a spec and not a design doc. It captures a single choice: the
context that forced it, the decision taken, the alternatives rejected, and the
consequences you'll live with. Months later it answers "why is it built this
way, and what breaks if I change it?" without anyone reconstructing it from memory.

## Where this fits

- **Board** ([TokenTelemetry Roadmap](https://github.com/users/VasiHemanth/projects/1)) — the *index* of work. Each card's `ADR` field links here.
- **ADRs** (this folder) — the *why*.
- **Design docs** (`../design/`) — the *what & how* of a feature.
- **PRs** — the *change itself* + validation (diff, tests, review).
- **CHANGELOG.md / UPDATE.json** — what *users* get.

The board is the index; the repo is the truth. An ADR can never drift out of
sync with the code because it ships in the same commit.

## How to add one

1. Copy [`0000-template.md`](0000-template.md) to `NNNN-short-title.md` (next number).
2. Fill in Context / Decision / Consequences. Keep it to ~1 page.
3. Set **Status** to `Accepted` (or `Proposed` if still under discussion).
4. Commit it **in the feature's PR**, and paste its URL into the board card's `ADR` field.
5. If a later decision overturns this one, set this ADR's Status to
   `Superseded by ADR-XXXX` rather than editing history — the trail is the point.

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions in the repo | Accepted |
| [0002](0002-durable-history-rollup.md) | Durable SQLite rollup for analytics history | Accepted |
| [0003](0003-docs-site-fumadocs.md) | Docs + resources site with Fumadocs in the marketing app | Proposed |
