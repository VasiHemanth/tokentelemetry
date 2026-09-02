# Claude Code Prompt — Conversion-Focused Website Rebuild

How to use: open Claude Code in the `tokentelemetry` repo (or your `website/` directory) and paste the prompt below. It already contains the real analytics findings from the live audit (2026-06-23) so Claude Code doesn't have to guess. Refresh the numbers from `marketing/06-analytics-findings.md` before re-running later.

---

## PROMPT (copy everything in this block)

```
You are working on the marketing website for TokenTelemetry (tokentelemetry.com), a free,
open-source, 100% local observability dashboard for AI coding & autonomous agents (Claude Code,
Cursor, Codex, Gemini CLI, Hermes + 35 more). It reads logs agents already write — no SDK, no
cloud, no signup. Install is a desktop CLI one-liner (curl … | bash for macOS/Linux, irm … | iex
for Windows). 154 GitHub stars. The website lives in this repo (find the site directory — likely
`website/` (Next.js) — confirm before editing).

GOAL: redesign the site to maximize two conversions — (1) installing the tool, (2) GitHub star —
with INSTALL as the primary action. Do not break the existing build, styling system, or the
UPDATE.json release banner. Follow the repo's CLAUDE.md rules. IMPORTANT: make changes on a new
branch, never commit straight to main, and write an UPDATE.json entry if any commit is a feat:.

=== REAL ANALYTICS (live audit, 30 days, do not re-collect — act on these) ===
- ~978 homepage views but only ~13 installation-page views (~1.3% reach install). This is THE problem.
- ~61% of sessions are MOBILE (ChromeMobile 33% + MobileSafari 28%), mostly from Threads (113 refs)
  and Reddit (45 + 37 from the Reddit app). But the tool installs on a DESKTOP. Mobile visitors
  currently have no possible conversion action.
- Hero's primary CTA is "Star on GitHub" (vanity); the install command sits lower. Wrong priority.
- Scroll depth drops sharply after 20%; only ~21% of mobile users reach the bottom. Avg scroll 49%.
- Dead clicks 16.74% (73 sessions) concentrated on the FAQ section — users tap FAQ items that don't
  respond. Rage clicks 0.92%. faq_open event fires 58x, so intent is real but the UI is confusing.
- Avg engagement 25s; 1.22 pages/session. ~20 seconds + one screen to land the value prop.
- Mobile users' first clicks are the dashboard link and feature images — they want to SEE the product.
- Performance is already excellent (Clarity 86/100, LCP 1.7s, INP 140ms, CLS 0, 0 JS errors).
  DO NOT spend effort on speed; spend it on conversion structure.
- GA4 has ZERO key events configured — installs are currently unmeasurable.

=== WHAT TO DO ===
1. Audit the current site code first. Map the homepage component structure, the hero, the FAQ
   component, and how the install command is rendered. Report what you find before changing anything.

2. Restructure the homepage above-the-fold (first screen / first 20% of scroll) to contain, in order:
   - one-line value prop (keep the existing "See what your AI agents cost, think, and do — locally" voice)
   - a looping dashboard demo GIF/video or screenshot (mobile users click images first — lead with proof)
   - PRIMARY CTA = install: an OS-auto-detected, one-click "Copy install command" block
   - SECONDARY CTA = "Star on GitHub" (demote it from primary)

3. Add a MOBILE conversion path (this is the highest-value change). For viewports that can't run a
   desktop CLI, show: a "📋 Copy command for later", a "✉️ Email me the install command" capture, and
   a prominent "▶ Watch 30-sec demo". Goal: a phone visitor leaves with intent captured, not bounced.
   Wire the email capture to a simple endpoint/stub and leave a clear TODO for connecting Hostinger
   Reach (email marketing) — do not hardcode secrets.

4. Fix the FAQ. Make items unmistakably interactive (visible chevron, hover/focus states, cursor
   pointer, proper <button>/aria-expanded) or render answers as always-visible text. Eliminate the
   dead-click trap. Keep the faq_open analytics event firing.

5. Instrument conversions. Add analytics events (match the existing GA4/Clarity setup; reuse whatever
   event-dispatch helper the site already has — search for gtag/dataLayer/clarity calls): `install_copy`,
   `download_click`, `outbound_github`, `demo_play`, `email_capture`. List which to mark as GA4 Key
   Events (I'll flag them in the GA UI).

6. Keep it accessible and responsive. Test the mobile layout specifically (most traffic).

=== CONSTRAINTS ===
- New branch. Don't touch main. Respect CLAUDE.md (UPDATE.json rule, pre-push hooks, security gates).
- Don't redesign the whole site or swap frameworks — surgical, conversion-driven edits.
- Don't add heavy dependencies; performance is already good.
- Show me a diff and a short rationale per change before finalizing. Take screenshots of the new
  hero on desktop AND mobile widths and show them to me.

Start by exploring the site directory and reporting the current homepage + FAQ structure. Then
propose the specific edits before writing them.
```

---

## Optional follow-up prompts (after the first run)

- "Now generate the 30-sec dashboard demo plan: what to record, in what order, target <2MB GIF."
- "Wire the email-capture endpoint to Hostinger Reach — here are the API docs: <paste>. Keep the token in an env var, never commit it."
- "Add a docs-page 'Was this helpful? 👍/👎' micro-feedback widget that fires a `doc_feedback` event."

## Why this prompt works
It front-loads the real numbers (so Claude Code acts instead of re-investigating), names the single
biggest problem (mobile dead-end + wrong CTA), constrains scope (no framework swaps, respect hooks),
and demands a diff + screenshots before finalizing — matching your "don't edit code, I'll review"
preference for this repo.
