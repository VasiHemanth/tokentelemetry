---
type: Decision
title: ADR-0003 Docs and resources site with Fumadocs
description: Docs built with Fumadocs inside the existing website/ Next.js app, statically exported to tokentelemetry.com/docs on GitHub Pages.
resource: /docs/adr/0003-docs-site-fumadocs.md
tags: [decision, docs, website]
timestamp: 2026-07-02
---

# ADR-0003: Docs site with Fumadocs

Docs and community resources live as a Fumadocs route group inside the
existing `website/` Next.js app (Tailwind v4, App Router), served from
GitHub Pages at `tokentelemetry.com/docs` and `/resources` (subdirectory,
not subdomain, for SEO and one toolchain). Content is MDX, one file per
feature under `website/content/docs/`; search is a prebuilt Orama static
index; videos are embeds, not committed files. The local app links out to
the docs (Docs nav link + per-page help icons).

Constraints that drove it: solo maintainer, static-export-only hosting,
local-first ethos (no hosted SaaS), existing Next.js investment. Design doc:
`docs/design/documentation-site.md`.
