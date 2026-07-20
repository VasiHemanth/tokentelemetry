---
type: Overview
title: TokenTelemetry
description: Local-first observability dashboard for AI coding agents and autonomous agents; reads session logs from disk, no SDK or cloud.
resource: /README.md
tags: [overview]
timestamp: 2026-07-02
---

# TokenTelemetry

Free, MIT-licensed dashboard that tracks token usage, LLM costs, tool calls,
session traces, reasoning steps, subagent delegations, cron health, and
gateway health across 12 coding agents and Hermes Agent (Nous Research). It
reads each agent's session logs and SQLite state straight from the filesystem
(no SDK, no instrumentation) and serves a local web UI at
`http://localhost:3000`.

- Stack: Next.js 16 frontend (`frontend/`), FastAPI backend (`backend/`),
  Node launcher (`bin/cli.js`), marketing + docs site (`website/`, static
  export to tokentelemetry.com).
- Privacy: logs never leave the machine ([local-first](conventions/local-first.md)).
  Anonymous content-free usage stats are on by default, opt-out in Settings or
  `DO_NOT_TRACK=1`.
- Solo-maintained by Hemanth Vasi; tracked on GitHub Projects board #1 with
  ADRs and design docs in-repo ([recording decisions](decisions/adr-0001-record-decisions.md)).

Start here:

- [Supported harnesses](index.md) under `harnesses/`
- [Scanner](subsystems/scanner.md), the core pipeline
- [Ship a feature](playbooks/ship-a-feature.md), the maintainer loop
