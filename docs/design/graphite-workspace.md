# Graphite session workspace

## Scope

Apply the approved blue/Graphite visual direction to the real local application and public website. The session workspace shares one trace model between Conversation, Execution, and Event log, retains the legacy step view, and loads child recordings only on request. No generated narrative substitutes for recorded evidence.

## Implementation slices

1. Correct Pi/Prime usage preservation and OpenCode/ZCode usage ownership, with regression tests and independent recording comparisons.
2. Apply readable semantic surfaces/text, restrained blue actions, and typography to the app and website. Retain light mode.
3. Add a continuous conversation projection over the existing spans. Preserve selection between views and in the URL; expose available reasoning and tool evidence through the inspector.
4. Bound execution/event rendering for large recordings, without dropping source data. Keep prompt/model/tool/notification distinctions explicit and label unknown usage.
5. Verify populated pages, representative large Claude/Codex recordings, child expansion, filters, light mode, narrow screens, and source links. Run TypeScript, relevant lint/tests, and real-source numeric reconciliation.

## Acceptance

- Project and task labels come from real recordings; no preview sample data enters the product.
- View switches preserve the selected span; reloading a link to a main-trace span restores selection.
- Routine metadata does not crowd the default conversation; the event log exposes API records in their returned order, with raw Codex records requested before frontend normalization.
- Long recordings do not mount every content payload or every table row at once.
- Missing usage remains distinguishable from a recorded zero.
- New local app and backend ports point at this worktree, leaving existing servers untouched.

## Limits

This change does not promise permanent source retention or source-stable cross-parser identifiers. Existing archive coverage and unsupported harness capabilities remain visible limitations. Public hosting is not part of local implementation.

## Validation evidence

- A 124.6 MB Claude recording contained 6,364 source records and 791 unique model calls. Independent source totals matched the tree: 1,598 input, 900,263 output, 346,839,424 cache read, and 4,693,443 cache write tokens.
- On a 1600 × 1100 viewport, its expanded execution list had 1,725 rows while mounting about 18–19 tree items during top/bottom scrolling. A 68.2 MB Codex recording also retained selection across Conversation, Execution, and Event log with about 20–21 mounted tree items.
- Development workspace readiness was approximately 10 seconds for the 124.6 MB recording and 2.6 seconds for the 68.2 MB recording in this local run. These are observations, not a production performance guarantee; fetching/parsing still reads the full recording.
- Event log rendering is paginated at 80 records. Conversation entries use measured heights and a bounded render window, and selected context is revealed when entering a view.
- Frontend trace/usage regression run: 100 passing tests. Production frontend build completed successfully in an isolated output directory. App and website TypeScript checks passed; modified frontend files passed ESLint.
- The expanded backend regression run exposed an existing stale delegation assertion on untouched HEAD: it expected cache high-water usage while the helper already returned cumulative reads. The assertion now checks cumulative reads across distinct calls and preserves the duplicate-message guard.
- Website home, docs, resources, and privacy were inspected locally. Existing marketing screenshots remain unchanged; no private live-session capture was added to public assets.
- Backend parser/delegation regression suite: 90 tests passed with background telemetry disabled for the test process. Child expansion and reload of a linked child turn were checked in a real session; keyboard selection, event paging, and light mode completed without browser errors.

## Unified reading workspace

The default Session view places execution navigation on the left and a continuous conversation on the right. Tree selection reveals the matching entry; user scrolling follows the active entry in the tree. Model calls, routine tools, reports, and expanded child recordings retain their trace order. Child work remains attached to its handoff, rather than being interleaved by wall-clock time.

The reader uses measured heights and a bounded render window instead of conversation pagination. Long text previews are capped at 6,000 characters, with full recorded content available in an evidence drawer. Reasoning remains an explicit disclosure. The drawer uses native modal focus handling and Escape dismissal. Execution focus preserves the full-width tree and timeline; Event log and the legacy step view remain available.

On narrow windows, the conversation opens first and a button switches to execution navigation. Existing links using `view=conversation` still open the unified Session view. Selection identifiers retain their existing within-recording stability limits.

Unified-view browser checks passed on both large recordings: late-entry link reloads, switching into execution focus, and jumping to the end. The reader mounted approximately 7–14 entries in the sampled checks. A linked child task restored its recording and aligned in the reader; native drawer focus and Escape dismissal passed. At 320, 375, 768, and 1024 px, the document had no horizontal overflow and the reader/navigation remained usable. Dark and light themes were inspected. The current frontend regression suite has 100 passing tests after replacing the prior paginated projection tests with continuous-reader tests.

## Resizing, inline evidence, and agent coverage

The Session split can be dragged or adjusted using the divider's arrow keys, Home, and End; double-click restores 34%. Pane limits preserve 240 px for execution and 320 px for reading. The divider is hidden when the narrow-screen navigation switch is used.

Input and result expand together inside their conversation entry. Only expanded entries format payloads, and expansion state survives row virtualization. Empty results remain distinct from unavailable results. Reasoning and complete span metadata remain accessible through the evidence drawer.

Every registered agent has a workspace adapter. Existing rich adapters remain in use, including ZCode/Z.ai. Grok Build, Cursor, Copilot, Antigravity, Vibe, Cline, Muse, SmallCode, Kimi, Oh My Pi, and the OpenAI-compatible registration have a conservative recording-order adapter. It preserves source evidence without claiming verified model-call boundaries, clock durations, parallelism, or per-call usage. Unmatched results remain independent records. SmallCode's immediately adjacent same-name call/result contract is the only pairing fallback without IDs. Delegation metadata without a join key is explicitly unplaced, with child recordings linked only through their recorded identifiers.

Independent comparisons across 29 additional local recordings from eight newly adapted reader types retained all 1,580 tool calls and 93 result records exposed by the APIs. These comparisons validate reader output, not completeness against every native harness artifact. Copilot and several other current readers omit results or usage; the workspace discloses those gaps. Kimi and Oh My Pi have schema-level coverage but no local recordings were available for this validation. OpenAI-compatible availability still depends on a reader supplying session records.

The frontend regression suite now has 109 passing tests, including registry coverage, conservative pairing, structured input, missing/empty results, delegation links, and divider bounds. Browser checks cover the eight additional populated reader types, empty-recording controls, and inline disclosure without opening the drawer.

## Overview first and default inspector

The trace summary and its existing Ask once / Chat controls now precede delegated work and the session reader. A Read session shortcut moves directly to the workspace. Delegation entries remain fully available in a bounded scrolling list so large agent rosters do not expand the overview indefinitely.

The session inspector opens by default. At widths of 1440 px and above it docks beside the reader; below that it remains open beneath the reader to preserve conversation width. Inspector body values use 14 px text with readable line spacing, labels use 12 px, and technical identifiers/paths retain monospace styling. Context, agents, tools, artifacts, and raw records use the revised typography.

Browser checks verified overview-before-workspace ordering, the shortcut, default inspector state, close/reopen behavior, and no document horizontal overflow at 1600, 1440, 1024, 768, 375, and 320 px. The 1440 px view retains both execution and conversation beside the inspector. No summary generation or question submission was triggered during validation.
