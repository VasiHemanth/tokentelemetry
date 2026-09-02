# Analytics Findings — Conversion Audit (browsed live 2026-06-23)

Sources: Microsoft Clarity (30d), Google Analytics 4 (28d), Hostinger hPanel. Cloudflare dashboard wouldn't finish loading — check it manually for bot %/edge cache, but Clarity + GA already cover traffic.

## The one-sentence problem

**~978 homepage views → 13 installation-page views (~1.3%).** Traffic is healthy and growing; the homepage is leaking nearly everyone before they reach the install step. Fixing the homepage is the single highest-leverage move.

## Traffic (what's working)

- **Clarity 30d:** 436 sessions, 385 unique users, 4 bots excluded. Growing.
- **GA4 28d:** 755 active users, 752 new. 154 GitHub stars.
- **Top referrers (Clarity):** l.threads.com **113**, reddit.com **45**, com.reddit.frontpage (Reddit mobile app) **37**, google.com 26, github.com 10, Teams 10, linkedin. → **Threads + Reddit are your engine.** Keep feeding them (matches the social strategy).
- **Channels (GA):** Referral > Direct > Organic Social.
- **Performance is NOT the problem:** Clarity score 86/100, LCP 1.7s, INP 140ms, CLS 0, 0 JS errors. Don't waste time on speed.

## The leaks (what's broken)

1. **Mobile/desktop mismatch — the biggest structural issue.** ~61% of sessions are mobile (ChromeMobile 33% + MobileSafari 27.75%), largely from Threads/Reddit apps. But TokenTelemetry is a **desktop CLI tool** (`curl … | bash`). A phone visitor literally cannot install it where they are. There is no "send install command to my laptop / email it to me / save for later" path — so the majority of traffic has no possible conversion action.
2. **Wrong primary CTA.** The hero's main button is **"Star on GitHub"** (vanity metric) with the install command sitting below it / near the fold. The page optimizes for stars, not installs.
3. **Scroll cliff at 20%.** Clarity AI: scroll depth drops sharply after 20%; only ~21% of mobile users reach the bottom. Avg scroll 49%. Anything below the first screen (features, supported agents, install for some viewports) is mostly unseen.
4. **Dead clicks 16.74% (73 sessions), concentrated on the FAQ.** Clarity AI: "Desktop users frequently clicked FAQ section, with high dead and rage clicks, indicating confusion or unresponsiveness." Users are tapping FAQ items that don't expand/respond. Rage clicks 0.92% (4). Quick-backs 2.52%.
5. **Low engagement:** 1.22 pages/session, avg engagement 25s (GA), 1.0 min active of 3.5 (Clarity). You have ~20 seconds and one screen to land the value prop.
6. **No conversion tracking.** GA4 **Key events = 0** ("No data available"). You're measuring installs blind. Events that DO fire: page_view 1.1K, session_start 983, first_visit 752, user_engagement 250, scroll 231, click 146, **faq_open 58**. Clarity Smart events show only **Download 5 sessions, Outbound click 9** in 30d.

## Page-level funnel (GA + Clarity, 30d)

| Page | Views |
|------|-------|
| Homepage | 978 (GA) / 398 (Clarity sessions) |
| /docs (Introduction) | 18–34 |
| /#install (anchor) | 17 |
| /docs/installation | 10–13 |
| /docs/supported-agents | 6–9 |
| /#features | 5 |
| /docs/quick-start | 6–11 |

Mobile users' first clicks (Clarity AI): the **Dashboard link** and **feature images** — they want to *see* the product, not read. That's a strong signal to lead with a visual/demo.

## What this means for the rebuild (priorities)

1. **Make "Install" the hero CTA, not "Star on GitHub."** One-click copy of the `curl` command above the fold, OS auto-detected. Move the star to secondary.
2. **Add a mobile conversion path.** For phone visitors who can't install now: a "📋 Copy install command" + "✉️ Email me the command" or "Save for desktop" button, and/or a prominent "Watch 30-sec demo" so the visit isn't wasted. This alone could rescue ~60% of traffic that currently dead-ends.
3. **Put the proof above the 20% line.** Dashboard screenshot/GIF + the one-line value prop + install must all live in the first screen. Features/agents/FAQ come after.
4. **Fix the FAQ.** It's the #1 dead-click magnet. Make items obviously expandable (chevrons, hover states) or convert to plain visible text. `faq_open` fires 58×, so people want it — it's just broken/confusing.
5. **Instrument conversions.** Define GA4 key events: `install_copy` (copy button), `download_click`, `outbound_github`, `demo_play`. Without these you can't tell if any redesign worked.
6. **Lead with the demo for mobile.** Mobile users click images first — a looping dashboard GIF/video at the top serves them.

## Hostinger services available (for feedback + marketing goals)

- **Hostinger Reach (Email Marketing)** — free plan offered for 1 year on your account. Campaigns, automations, welcome series, subscriber tracking. Use for: an optional "notify me about updates" capture on the site + a desktop-install follow-up email (the mobile rescue path above). Keep it optional to respect the "no signup" positioning.
- **Business email** (e.g. hemanth@tokentelemetry.com) — available. Improves sender trust/deliverability for Reach campaigns and outreach; better than gmail for partner/press emails.
- **Horizons** — Hostinger's AI site builder (optional; you already have a custom site, so probably skip).
- **Hermes Agent** app is listed in your hPanel — worth noting since TT already supports Hermes; possible cross-promo angle.

### Feedback strategy (beyond the in-app Google Form)
- In-app Google Form is fine for deep feedback, but add **one-tap signals** too: a micro "Was this helpful? 👍/👎" on docs pages and a single NPS-style question, because long forms get few responses.
- Pipe the **dead-click/FAQ confusion** finding straight into a docs/FAQ fix — that's feedback Clarity already gave you for free.
- Use **Clarity Smart Events + GA key events** as passive feedback (where people rage/dead-click) and recordings to watch real install attempts.
- A lightweight **"what agent do you want supported next?"** poll (Google Form or Discord) doubles as feedback + community engagement (ties to the Discord plan).
