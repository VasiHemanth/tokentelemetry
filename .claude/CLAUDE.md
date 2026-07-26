# TokenTelemetry — Claude Code project rules

## ⚠️ Pre-push policy (enforced by hook)

**Every push to a branch destined for `main` that contains at least one
`feat:` commit must update `UPDATE.json` at the repo root.**

This is enforced by `.claude/hooks/enforce-update-json.py`, wired up via
`.claude/settings.json` as a `PreToolUse` hook on the `Bash` tool. The hook:

1. Detects `git push` / `gh pr create` invocations (via proper shell
   tokenisation — not substring matching, so `echo "git push"` is fine).
2. Skips enforcement if we're on `main` itself.
3. Scans `git log origin/main..HEAD` for Conventional Commit subjects
   matching `feat:` / `feat(scope):` / `feat!:` etc.
4. If no `feat:` commits are present (only `fix:`, `chore:`, `docs:`,
   `refactor:`, `style:`, `test:`, `ci:`) — **allows the push silently**,
   because the change isn't user-facing in a way the banner should announce.
5. If at least one `feat:` commit IS present, requires `UPDATE.json` to
   appear in the branch's diff vs `origin/main`. Otherwise: deny.

**Why this rule, not "block every push":** UPDATE.json is a CURATED feed.
Forcing every fix/chore/docs push to add a fake entry would pollute it with
noise users learn to ignore. The banner is only valuable when it announces
something users actually want to know about — i.e., features.

**Why this rule, not "trust the maintainer":** for actual `feat:` work it's
easy to forget the file, and a stale banner is worse than no banner
(eroded trust, users on prior versions miss the update prompt entirely).

## UPDATE.json schema

```json
{
  "releases": [
    {
      "tag": "YYYY-MM-DD",
      "title": "Short release headline (≤50 chars)",
      "highlights": [
        {
          "title": "One-line feature name",
          "description": "1–2 sentences: what changed and why a user should care. No marketing fluff; concrete benefits.",
          "href": "/settings"
        },
        {
          "title": "Another feature",
          "description": "..."
        }
      ]
    },
    {
      "tag": "(prior releases stay below — drawer shows up to 6 newest)"
    }
  ],
  "release_url": "https://github.com/VasiHemanth/tokentelemetry/commits/main"
}
```

### Field rules
- **`tag`**: ISO date (`YYYY-MM-DD`). Used as a fallback heading when `title` is absent.
- **`title`**: short headline. Shows as the section heading in the drawer.
- **`highlights`**: 1–5 bullets per release. Anything past 5 is truncated.
- **`href`** (optional): internal route (`/settings`) renders as `<Link>` keeping nav in-app; external URL (`https://…`) opens a new tab.

### Each release entry should
- Go to the **top** of `releases[]` (newest first — drawer renders top-down)
- Have a description that helps a non-technical user understand *why* this matters, not just *what* changed
- Use an `href` when a single page is the natural landing spot for the change (e.g. a new feature page, a redesigned section)
- Credit external contributors for major community-raised bugs/fixes: end the
  relevant highlight's description with "Thanks to <github-username> for
  reporting and fixing this (PR #N)." Reserve credit for significant external
  contributions so it stays meaningful; maintainer changes carry no credit line.

## When the hook gets in your way

The hook is intentionally narrow. Cases:

1. **Pure `fix:`/`chore:`/`docs:`/etc. branch**: hook allows silently. You don't need to touch UPDATE.json.
2. **Mixed branch with one `feat:` + several `fix:` commits**: hook still requires UPDATE.json — write an entry for the feature, fixes get a free ride.
3. **`feat:` branch where the feature genuinely isn't user-visible** (e.g. internal refactor mis-labeled `feat:`): re-label the commit to `refactor:` / `chore:` and amend, OR add a UPDATE.json note explaining what you shipped to users.
4. **Pushing main itself** (rebase, force-push for cleanup): hook skips automatically.
5. **Repo without `origin/main`**: hook allows through (assumes you know your setup).
6. **Last resort**: `claude --no-hooks` for that session — but if you find yourself reaching for this often, the rule is mis-tuned and worth revisiting.

## Pre-push merge validation (two gates)

After issue #91 (vulnerable + unused deps merged un-reviewed during the
fast remote-access ship), every change destined for `main` passes two gates:

1. **`.claude/hooks/prepush-claude-review.py`** (local, PreToolUse on `Bash`).
   On a `git push` / `gh pr create` from a non-main branch, it diffs
   `origin/main..HEAD`, sends the diff to your local `claude` CLI for a focused
   review (dependency hygiene, remote-exposure / auth-bypass regressions,
   committed secrets, injection-class bugs), and **denies the push only on an
   explicit high-confidence `block` verdict**. It **fails open**: missing
   `claude` CLI, empty/huge diff, timeout, or unparseable output all ALLOW the
   push — a flaky reviewer never blocks legit work. Reuses the push-detection
   helpers from `enforce-update-json.py` (imported, not duplicated). Skips
   docs/asset-only pushes. Bypass with `--no-hooks`.
2. **`.github/workflows/security-audit.yml`** (CI, deterministic). Runs
   `npm audit --omit=dev --audit-level=high` across root / `frontend` / `website`
   on every PR touching a `package.json`, failing on high/critical *runtime*
   vulns (dev-only advisories are reported but non-blocking). This catches
   contributor PRs (which the local hook can't see) and is the exact gate that
   would have stopped #91. Lockfiles are gitignored, so CI uses
   `npm install --package-lock-only` — fixes ride on the committed `package.json`
   pins + `overrides`, not a lockfile.

## Other project conventions

- **Schedules page is read-only.** The CRUD UI was built but is commented out under `# DISABLED-MUTATIONS:` markers in `backend/main.py`. Re-enable by uncommenting; don't reimplement.
- **Backend default port: 8000** (matches `bin/cli.js`). The frontend derives its API base from `window.location` + `NEXT_PUBLIC_API_PORT` at runtime (set by `bin/cli.js` from `--api-port`), so a non-default port works automatically. `NEXT_PUBLIC_API_BASE` still works as an explicit override (pin a fixed host) but is no longer required just to change the port. For remote/tailnet access use `--host` / `--allowed-origins` (envs `TT_HOST` / `TT_ALLOWED_ORIGINS`); default stays loopback-only. **Remote access is token-gated:** a non-loopback `--host` auto-generates `TT_AUTH_TOKEN` (printed once at startup) and `backend/main.py`'s `RemoteAuthMiddleware` then requires it on every *remote* request — loopback is always exempt, so the default local experience is unchanged. CORS is **not** the security boundary (it only restrains browsers); the token is. Frontend carries it via `Authorization: Bearer` (and `?token=` for artifact `<img>`/`<a>` loads) — see `frontend/src/lib/api.ts` + `TokenGate.tsx`. Override with `--auth-token`, or disable on a trusted tailnet with `--insecure-no-auth`. The middleware is registered **before** CORS so CORS stays outermost (answers OPTIONS preflight, decorates the 401).
- **`UPDATE.json` is committed.** It's not generated, not gitignored. Treat it as source code.
- **Test pollution: clear `~/.tokentelemetry/.update-check.json`** if you manually seed it for testing; the SHA validator added in PR #34 catches obvious garbage but doesn't catch all dev mistakes.

## Summarizer error handling (never dump raw errors in the UI)

Any failure from a summarizer backend (CLI non-zero exit, HTTP 4xx/5xx, timeout,
empty output) **must be classified, not surfaced raw**. A user should never see a
bare stack trace, `HTTP 4xx …`, or a provider's JSON blob as the error message.

The pipeline is:

1. **Adapters raise `SummarizerError`** with the underlying detail kept in the
   message (status code + provider body), so the classifier has something to
   match on. HTTP adapters keep the numeric status in the string (e.g.
   `HTTP 413 from …: {…}`).
2. **`backend/summarizers/errors.py::classify()`** buckets it into a `category`
   and returns `{category, title, message, hint, raw}` — a short human title, a
   plain-English message, an actionable hint, and the truncated raw text (shown
   only behind a "Show raw error" disclosure). Patterns are ordered, first match
   wins; order matters (e.g. `too_large` before `quota` because token-budget
   413s also carry rate-limit wording).
3. **The endpoint returns `error_info`**, and the frontend renders it via
   `SummaryErrorCard` (`SummaryPanel.tsx`) / the Test-connection result.

**When you add a new error category** you must touch all three layers or it
won't compile / won't render:
- add the pattern + `title`/`message`/`hint` branch in `errors.py`;
- add it to the `SummaryErrorInfo["category"]` union in `frontend/src/lib/summarizer.ts`;
- add an icon to `ERROR_ICONS` in `SummaryPanel.tsx` (it's a total `Record`, so
  TS fails the build if a category is missing).

Hints should tell the user what to *do* (switch model, check `ollama serve`,
set an env var), not just restate the error. Prefer graceful degradation over a
hard error where possible — e.g. the `openai_compat` adapter retries once with a
clean OpenAI-only payload when a strict gateway 400s on a non-standard field.

## Verify before reporting done (data & numeric features)

For any change that produces a number, date, aggregate, or anything the user
reads off the UI, **verify it yourself before saying "done." Do not make the
user be the test harness** — the round-trip of "ship → user finds the bug →
validate after the fact" is exactly what this rule exists to kill.

1. **Independent recompute.** Re-derive the value a *different* way than the
   feature does (e.g. hit `/sessions` and re-bucket in a throwaway script) and
   show the comparison: UI/endpoint value vs your recompute. They must match; if
   they don't, that's a bug — surface it, don't gloss it.
2. **Timezone is local-day.** The user is IST (+05:30); day buckets are LOCAL
   days. `toISOString()` on a local-midnight `Date` silently rolls back to the
   previous UTC day — never key/label a day bucket that way (this is what put the
   activity heatmap off by one). Build day keys from local Y/M/D components.
3. **Confirm the app runs the NEW code** before validating in the browser: right
   branch/HEAD, expected ports (frontend 3000 / backend 8000), and a *fresh*
   `.next` (a stale build or the wrong port means you're testing old code — a 404
   on a new endpoint or unchanged UI is the tell).
4. **Static checks pass:** `tsc --noEmit` in `frontend/` for FE changes; parse/
   import the touched backend modules. Don't call a build healthy on faith.

Put the evidence (the diff, the numbers, the passing checks) in the done
message, not just the word "done". `/ship` runs this loop as a command.
