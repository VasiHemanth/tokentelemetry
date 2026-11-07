# Application typography preference

## Objective and contract

Provide one application-wide font-size setting so the same user can choose smaller text on a laptop and larger text on a monitor. Keep the established Geist interface font, with monospace reserved for code, technical identifiers, and numeric metrics. This is text scaling, not browser zoom or a layout-density setting. The existing per-role hierarchy remains intentional: a heading, body paragraph, and timestamp are not the same size.

The preference is 85–150%, in 5% steps, default 100%. It is stored locally in this browser, applies before paint, survives route changes/reloads, and synchronizes across tabs of this app. The provider owns `--tt-text-scale` and `data-text-size` on the document root. CSS and chart rendering consume that same factor. No backend configuration or recorded session data changes.

The existing hover-card correction is independent: only chart segments expose the popup, with keyboard focus on chart segments retained. The metric cards below remain static.

## Ordered implementation slices

1. Preference foundation: pure normalization tests, provider, pre-paint initialization, storage failure handling and cross-tab updates. Acceptance: invalid values fall back safely, state and root scale agree, default rendering/hydration remains stable. Verify with unit tests, TypeScript, reload and blocked-storage checks.
2. Settings control: General → Font size with smaller/larger controls, range, presets, reset, saved-state explanation and a live preview. Acceptance: every control applies immediately, stays within bounds, and is keyboard accessible. Verify actual computed sizes and preference persistence through the UI.
3. Global typography: connect standard/rem text utilities, fixed pixel utilities, Markdown, charts/SVG and intentional custom font sizes to the same scale. Acceptance: computed font ratios match the selected percentage while root font size and layout dimensions remain unchanged. Verify representative pages and audit exceptional font declarations.
4. Integration/reflow: inspect navigation, fixed-height trace rows, payload headers, expanded content, evidence drawers and chart tooltips at large text sizes. Acceptance: controls remain usable, reading content does not overlap or disappear, and hover cards fit the viewport. Verify desktop and narrow widths, including large recordings.
5. Independent validation and review: inspect Dashboard, Projects, Analytics, Settings, session reading/execution, inspector, Markdown/code and modals. Check 85%, 100%, 150%, storage/reset/cross-tab behavior, dark/light themes and browser errors. Run scoped lint, type checks, relevant regression tests and the production build after integration.

## Parallel ownership and checkpoints

One agent owns the provider and Settings controls, one owns CSS/chart typography, and one independently audits and validates. The parent owns chart-only hover behavior, overlay reflow, integration review and release documentation. Shared contracts are agreed before edits; agents do not commit independently.

Checkpoint A: preference and CSS integration typecheck and pure tests pass. Checkpoint B: independent browser tests confirm actual computed ratios, persistence, layout and interaction behavior. Checkpoint C: production build and review pass; only then commit the complete preference. Fixes exposed by validation are retested on their affected paths.

## Risks to verify

- Arbitrary pixel text and inline chart fonts can bypass a rem-only solution.
- Global UI zoom would resize layout geometry and break the user's text-only intent.
- Large text can outgrow fixed-height headers, virtualized rows and popups.
- Storage can be unavailable or contain invalid values; first-paint code and React state must use the same normalization.
- Cross-tab updates must apply without write loops; open overlays should dismiss stale positioning.
- Monospace used for prose can look inconsistent, while removing it from code and identifiers would harm readability.

## Validation evidence

Completed browser validation in Chrome against the running application:

- Dashboard, Projects, Analytics, Settings, Local Models, Hermes overview and an agent page: 21 route/scale checks at 85%, 100% and 150%. At these settings, 14px text measured 11.9/14/21px, arbitrary 13px labels measured 11.05/13/19.5px, and Analytics SVG ticks measured 8.5/10/15px. Root font stayed 16px, CSS zoom stayed 1, and desktop navigation stayed 256px wide.
- All five project tabs, nine Hermes subpages and the tray view received an additional 150% route check. Project index redirects to Activity and inherits the same root preference. Light-theme Settings and Analytics were visually reviewed; dark-theme session evidence was also inspected.
- Settings controls, bounds, presets, reset, reload, client navigation and cross-tab changes passed. Denied preference storage retained the live current-tab setting and displayed its persistence limitation. Four unit tests cover normalization, corrupt values, initializer agreement and denied storage.
- A synthetic recording verified Markdown headings, prose, code and tables. At 150%, conversation headings measured 27px, paragraphs 22.5px, code 18px and tables 19.5px. Geist remains the interface/prose family; Geist Mono remains the code family. Expanded content fits viewport widths 320, 375, 768, 1024, 1440 and 1600px.
- Chart-only hover, keyboard focus, segment changes and Escape passed at 150%. All four metric cards remain static and absent from the tab sequence. The popup measures its rendered dimensions before paint and stays within desktop and 320px viewport bounds; text-size changes dismiss it.
- Two large recorded Claude and Codex sessions passed latest-entry navigation, selected-entry reload, view switching and responsive reader checks at 150%, with four conversation entries mounted at the sampled end positions. No recording content or identifiers are included in fixtures or this document.
- All 141 frontend library tests passed, including the four new preference tests. TypeScript, scoped ESLint, production build and whitespace checks passed.

The implementation changes shared typography rather than duplicating preferences in individual pages. Standard size tokens, existing arbitrary absolute lengths, Markdown and inline chart fonts all consume the same multiplier. Keep future relative `em` sizes inherited so they are scaled only once. Dense tables and code retain their existing local scrolling behavior.
