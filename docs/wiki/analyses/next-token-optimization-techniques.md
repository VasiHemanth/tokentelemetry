---
type: Analysis
status: proposed
title: Four token-optimization techniques beyond the current seeds
description: Data-mined candidates attacking conversation shape (turn batching, tool-result diet, scout delegation, checkpoint-restart), the waste pools ponytail, caveman, headroom and the wiki do not touch.
tags: [plugin, token-savings, skillsmith, batching, delegation, methodology]
timestamp: 2026-07-06
resource: docs/wiki/analyses/brain-savings-approaches.md
---

# Four token-optimization techniques beyond the current seeds

Saved from the 2026-07-06 research session. The existing techniques attack
output volume (ponytail ladder), prose (caveman style), input slices, cache
hygiene and learned guardrails (headroom), and orientation knowledge
(llm-wiki/OKF). None attack conversation shape: turn count, context growth,
delegation topology, session lifecycle. This session's experiments showed
that is where the money is (cost tracked turns times context size, not file
bytes). Three independent sources fed this list: architectural reasoning, a
105-transcript waste-pool measurement, and an independent Codex session
whose proposals converged on the same shapes.

## Measured waste pools (105 transcripts, this repo + experiment copies)

- Parallel tool batching is nearly absent: 1.5% of tool-using turns issue
  more than one call; 278 consecutive read-only turns were collapsible,
  carrying ~26M replayed cache-read tokens (upper bound; cached replays
  bill at ~0.1x).
- Tool-result bloat is concentrated: 1.7% of tool results carry 24.8% of
  all result bytes; whole-file Reads are the top offender (44% of Reads
  pass no window).
- Context grows ~1.5-2k tokens per turn; the final third of a long
  session's turns costs 37% of its cache-read spend (33% would be flat).
  Real but modest in this corpus.
- Delegation is rare (16% of sessions) and shallow: even delegating
  sessions keep 13x more input-side tokens in the parent than in children.

## T1. Turn batching (bundle-and-fence)

Mechanism: every assistant turn replays the whole context; K independent
read-only calls issued as one message pay one replay instead of K. The
adherence experiment's 11-to-4 turn drop halving cost is the same lever.
Rule form: plan reads upfront; issue independent Read/Grep/Glob in a single
message; never alternate think-read-think-read for enumerable reads.
Evidence: 1.5% batching rate today; largest measured pool.
Experiment: fixed task set, arm with a batching rule in CLAUDE.md vs
without; primary metric turns and cache-read volume, correctness gate.
Risk: over-batching fetches wrong files (loses adaptivity); ceiling where
the next read genuinely depends on the previous result.

## T2. Tool-result diet (windowed reads, fat-tail caps)

Mechanism: a large tool result is paid once when produced, then re-paid in
every later turn. The waste is in the tail: cap the 1.7% of results that
carry a quarter of the bytes. Extends headroom's grep-before-read from
advice to enforcement (a PreToolUse hook can warn on whole-file reads of
large files; slim output flags on Bash).
Evidence: result sizes p50 328 chars vs p99 13k; Read is the top offender.
Experiment: tasks over large files with and without a windowed-read rule;
measure context size at end, re-read rate (windowing that misses context
forces re-reads, the failure mode to watch), correctness.
Risk: missing imports/distant definitions causes wrong edits or re-reads
that erase the saving.

## T3. Scout delegation (thin parent, disposable children)

Mechanism: exploration noise kept in the parent is re-paid every subsequent
turn; a subagent's context is paid once and discarded, returning
conclusions only. Moves the quadratic term to a throwaway.
Rule form: exploration expected to exceed ~N tool calls or produce dumps
goes to a scout subagent; the parent receives verdict plus evidence
pointers, never raw output.
Evidence: delegation used in 16% of sessions, parent spend still dominates
13:1, so the pattern exists but barely offloads; TT's delegation telemetry
already measures the split, so this is cheap to evaluate on real usage.
Experiment: search-heavy tasks inline vs scouted; measure parent context at
end, total tokens (parent plus child), correctness. Model tiering (haiku
scouts) is a follow-on multiplier, not part of the base test.
Risk: lossy summaries force the parent to reopen the search; child
cold-start overhead exceeds the saving on small explorations.

## T4. Checkpoint-restart (capped context, cheap re-entry)

Mechanism: the only technique that caps growth instead of slowing it: at a
milestone, write a small state capsule (decisions, open files, next steps)
and restart the session from it. Compounds with the second brain: the
index-in-pointer experiment showed re-orientation costs ~2-4 turns when a
wiki exists, which is what makes restarts cheap enough to consider.
Evidence: the corpus long-session tax is modest (37% vs 33%), so this ranks
last here despite an independent reviewer ranking it first structurally;
it should pay mainly on very long sessions and harnesses without good
compaction.
Experiment: multi-milestone tasks, one continuous session vs
restart-at-milestone with capsule plus wiki; total tokens and rework rate.
Find the break-even context size from the growth curve before promoting it.
Risk: the capsule omits a latent constraint and causes silent rework;
built-in compaction already approximates this, so the marginal win may be
small.

## Rejected or deferred

- Delta-only output (diffs over whole files): already mostly enforced by
  the Edit tool and covered by ponytail/caveman's volume rules.
- Model tiering: a multiplier on T3, not independent; test after T3 stands.
- Windowed subtask fanout (parallel candidate solutions): coordination
  overhead likely exceeds savings at this project's scale.

## Adoption path

Each surviving technique becomes a skillsmith seed (like ponytail, caveman,
headroom) only after its experiment shows a real effect; the adherence
lesson applies to these too: a rule agents do not follow saves nothing, so
each experiment must measure adherence to the rule, not just the outcome.

## Related

- [How to prove the brain saves tokens, ranked approaches](brain-savings-approaches.md):
  the measurement methodology these experiments should follow.
- [Prove the brain saves tokens](../ideas/prove-brain-token-savings.md):
  the idea thread this extends.
