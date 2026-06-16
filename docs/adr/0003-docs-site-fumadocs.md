# ADR-0003: Build the docs + resources site with Fumadocs in the existing marketing app

- **Status:** Proposed
- **Date:** 2026-06-16
- **Deciders:** @VasiHemanth
- **Related:** [design doc](../design/documentation-site.md)

## Context

`website/` is a Next.js 16 marketing site exported statically (`output: "export"`)
to GitHub Pages on `tokentelemetry.com`. It markets the product but doesn't teach
it: there is no per-feature documentation and no place to surface community-built
blocks (skills, hooks, MCP servers, workflows). The product itself runs locally
(`frontend/` on `localhost`), so the audience that most needs feature docs —
installed users — has no reason to revisit the marketing site.

Constraints: solo-maintainer (low ongoing cost, one toolchain), local-first/own-
your-stack ethos (no hosted SaaS lock-in), free hosting (GitHub Pages, static
export only — no server routes), and an existing Tailwind v4 + Next.js App Router
investment we'd rather extend than duplicate. Docs are also typically a project's
strongest long-tail SEO asset, so where they live affects discoverability.

## Decision

We will build documentation with **Fumadocs**, added as a route group inside the
existing `website/` app, served from **GitHub Pages at `tokentelemetry.com/docs`
and `/resources`** (a subdirectory, not a subdomain). Content is **MDX, one file
per feature**; search is a **prebuilt Orama static index**; feature videos are
**YouTube/Loom embeds**, not committed files. The locally-running `frontend/`
gets a **Docs** nav link and per-page help icons that **deep-link out** to the
matching hosted page — the app never bundles a copy of the docs.

## Alternatives considered

- **Subdomain `docs.tokentelemetry.com`** — rejected: search engines treat a
  subdomain as a largely separate site, so it starts SEO from zero instead of
  inheriting the main domain's authority; also adds DNS/CNAME work, splits
  analytics, and risks visual drift from the marketing site. Only worth it if docs
  become a separate product with their own team.
- **Nextra** — Next.js-native and stable, but its theme isn't Tailwind-v4-native,
  so matching the marketing site's exact look is harder.
- **Docusaurus / Astro Starlight** — excellent docs DX but a *second* framework
  and build toolchain alongside Next.js; more for a solo maintainer to carry.
- **Hosted SaaS (Mintlify / GitBook)** — gorgeous, but moves hosting off our
  domain/control and conflicts with the local-first/self-hosted ethos.
- **Committing video to the repo** — bloats the repo and every contributor clone;
  GitHub Pages also dislikes large binaries. External embeds keep both lean.
- **Bundling offline docs into the installed app** — would go stale on every doc
  fix and add download weight; deferred in favour of link-out.

## Consequences

- ✅ One repo, one toolchain, one deploy (`deploy-website.yml` already rebuilds on
  `website/**`); shared theme, domain, and components.
- ✅ Docs inherit the main domain's SEO authority and serve both discovery and
  installed-user audiences from a single source of truth.
- ✅ Adding a feature doc = adding one MDX file; sidebar auto-generates.
- ⚠️ Static export has no server search route, so search depends on a correctly
  built Orama static index — a deliberate config step, and a build that can break
  if misconfigured.
- ⚠️ Videos depend on third-party hosts (YouTube/Loom); a deleted video 404s the
  embed. Mitigated by keeping recordings re-creatable.
- ⚠️ In-app help requires the user to be online (link-out, not offline docs).
- 🔁 To undo: docs and resources are isolated route groups + a `content/` tree;
  removing them and the `SiteHeader`/`frontend` links reverts to today's site.
  Moving to a subdomain later means a separate Pages target + redirects.
