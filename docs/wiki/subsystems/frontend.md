---
type: Subsystem
title: Frontend dashboard
description: Next.js 16 App Router app in frontend/; routes for dashboard, analytics, sessions, projects, hermes, local-models, settings.
resource: /frontend/src/app
tags: [subsystem, frontend, nextjs]
timestamp: 2026-07-02
---

# Frontend dashboard

`frontend/` (Next.js 16, App Router, served at `localhost:3000`).

- **Routes** (`frontend/src/app/`): `/` dashboard, `/analytics`,
  `/sessions` + `/sessions/[id]`, `/projects`, `/hermes`, `/local-models`,
  `/settings`.
- **Key lib files:** `src/lib/api.ts` (API base derivation + bearer token),
  `src/lib/agents.ts` (agent registry/branding), `src/lib/summarizer.ts`
  (error category union). `TokenGate.tsx` handles the
  [remote auth](remote-auth.md) token prompt.
- Error rendering rule: summarizer failures go through `SummaryErrorCard` in
  `SummaryPanel.tsx`, never raw ([error handling](../conventions/error-handling.md)).
- Honest-signal rule: missing per-harness data renders as
  "not recorded by <agent>", never zero
  ([count-once](../conventions/count-once-invariant.md)).
- This is the product UI; the separate `website/` app is marketing + docs
  ([docs site decision](../decisions/adr-0003-docs-site-fumadocs.md)).
