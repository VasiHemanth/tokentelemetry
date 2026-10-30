# Graphite session workspace

## Scope

Apply the approved blue/Graphite visual direction to the real local application and public website. The session workspace shares one trace model between Conversation, Execution, and Event log, retains the legacy step view, and loads child recordings only on request. No generated narrative substitutes for recorded evidence.

## Implementation slices

1. Correct Pi/Prime usage preservation and OpenCode/ZCode usage ownership, with regression tests and independent recording comparisons.
2. Apply readable semantic surfaces/text, restrained blue actions, and typography to the app and website. Retain light mode.
3. Add a paginated conversation projection over the existing spans. Preserve selection between views and in the URL; expose available reasoning and tool evidence through the inspector.
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
- Event log rendering is paginated at 80 records. Conversation groups and long response sequences are paginated separately, and selected context is revealed when entering a view.
- Frontend trace/usage regression run: 101 passing tests. Production frontend build completed successfully in an isolated output directory. App and website TypeScript checks passed; modified frontend files passed ESLint.
- The expanded backend regression run exposed an existing stale delegation assertion on untouched HEAD: it expected cache high-water usage while the helper already returned cumulative reads. The assertion now checks cumulative reads across distinct calls and preserves the duplicate-message guard.
- Website home, docs, resources, and privacy were inspected locally. Existing marketing screenshots remain unchanged; no private live-session capture was added to public assets.
- Backend parser/delegation regression suite: 90 tests passed with background telemetry disabled for the test process. Child expansion and reload of a linked child turn were checked in a real session; keyboard selection, event paging, and light mode completed without browser errors.
