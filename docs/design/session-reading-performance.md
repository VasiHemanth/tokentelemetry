# Smooth session reading and recorded reasoning

## Problem and approach

Long recordings were repeatedly formatting mounted Markdown while scrolling. Scroll-driven selection also rebuilt ancestor expansion sets even when nothing changed, invalidating derived rows. A window based on three rows above and five below gave inconsistent preparation distances for short versus tall entries.

The reader now prepares two viewport heights (at least 1,000px) in each direction. Ordinary scroll updates remain local; a jump beyond the mounted range commits its replacement window synchronously so the empty height spacer is not the next frame's content. Existing measured-height anchoring and bounded rendering remain in place. The layout reference updates before measurement callbacks run.

Unchanged conversation entries and Markdown are memoized, callbacks are stable, and expansion updates return the original set when every ancestor is already open. Scroll-driven execution/URL selection follows after a 120ms pause. Explicit selection, inspecting evidence, expanding child recordings, and Latest remain immediate. Pending selection reads the current measured layout and is ignored after an explicit navigation action.

## Reasoning presentation and provenance

The conversation shows a four-line Markdown preview of readable reasoning before the associated assistant response. Expand opens the existing large reading modal with formatted/raw controls. Preview formatting is bounded at 1,200 characters; larger content is processed only while the modal is open, with its existing one-million-character cap and 50,000-character Markdown limit.

This is recorded reasoning text or a saved summary, not a guarantee that a harness records full internal reasoning. The shared component works wherever an adapter provides `content.reasoning`. Missing, empty, redacted, and opaque encrypted records produce no preview. Only known text-bearing fields are walked; encrypted fields are never serialized as a substitute for text.

Codex native summary blocks are preferred over mirrored desktop reasoning items within the same model response, matching the existing treatment of mirrored assistant messages. Desktop summaries remain a fallback. Both buffers reset at response boundaries, and encrypted content is not read.

## Validation

- Browser profiling used the same local Codex recording and scripted forward/backward wheel pattern before and after. Development-browser measurements are indicative, not a frame-rate guarantee. Maximum frame gap decreased from 267ms to 67ms with reasoning enabled. Long tasks decreased from 29 to 1 in those runs. Under a 4× CPU slowdown, maximum gap decreased from 1,317ms to 517ms. Frame probes found no fully empty conversation viewport in either run; the main-thread stalls, rather than stylesheet loading, were the observable failure.
- Unit coverage checks pixel overscan over 100,000 compact rows, bounded reasoning extraction, empty/redacted/encrypted cases, and Codex summary mirror precedence and reset behavior. All 144 frontend library tests pass.
- Synthetic Claude and Grok recordings verify inline Markdown, absent redacted previews, full modal content, raw/formatted switching, Escape and viewport widths from 320 to 1600px at 150% text size.
- Large Claude and Codex recordings at 150% retain Latest, selected-entry reload, execution/conversation switching and responsive navigation, with only nearby entries mounted. No recording identifiers, text or screenshots are included in the repository.

- Rapid scrollbar jumps kept the viewport populated and synchronized selection after settling. Deep links to already-expanded turns reveal the selected row in both panes without forcing expansion updates.
- An independent before/after adapter comparison on a real Codex recording retained all 151 readable reasoning-bearing model spans exactly. Native-summary support does not add mirrored copies.
- TypeScript, scoped ESLint, the production build and whitespace checks passed.
