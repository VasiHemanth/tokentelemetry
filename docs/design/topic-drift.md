# Topic drift and carried-context cost

Builds on recall v3 ([cross-harness-recall-v3.md](cross-harness-recall-v3.md)).

A long session often wanders: the user starts on the render pipeline, then
asks about thumbnails, then a deploy error. Every model call after a switch
still re-sends the earlier, unrelated context. This feature answers, per
session and per project:

- How many times did the session change topic, and did it come back?
- Roughly how many prompt tokens (and dollars) went to re-reading context
  from other topics?
- At which turn would starting a fresh session have saved the most?

It reports estimates, labelled as such. It never claims a dollar figure is
"waste": some carried context is useful.

## Inputs

1. **User-turn vectors from the recall index.** No new embedding calls. A
   user turn's vector is the mean of the stored vectors of its `user` chunks
   (from `doc_chunks` of the session document), re-normalized. Only sessions
   whose index entry is current (content fingerprint matches, lock `ready`)
   are measured; others report `available: false` with the reason ("Index
   this project in Recall to measure topic drift", "Session changed since it
   was indexed: re-index", "Model changed: re-index").
2. **Per-call prompt sizes from the session trace**
   (`get_session_detail`). One entry per model call:
   `{turn, prompt_tokens, cached_tokens, output_tokens, model}`.
   - `prompt_tokens` follows `waste.py`'s `prompt_size` rules on the
     `worktree-waste-detection-tier1` branch: Anthropic-style usage is
     `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`;
     OpenAI-style `input_tokens` already includes cached tokens.
     `cached_tokens` is the cache-read part. Claude repeats one message's usage
     on continuation records: dedupe by message id. Codex usage comes from
     `event_msg` `token_count` (`info.last_token_usage`).
   - `turn` uses exactly the same user-turn numbering as
     `summaries.build_chunks` (and `recall.codex_to_message_events` for
     Codex), so calls line up with turn vectors. A test asserts the alignment
     on Claude and Codex fixtures.
   - Agents without per-call usage get `capability.usage = false`: segments
     and diversions are still reported, cost is `null` ("not recorded by this
     agent"), never 0.
   - Code duplicating `waste.py` carries a comment to consolidate when that
     branch merges.

## Segmentation

Online, turn by turn:

- Turns with fewer than 4 words of user text, or no vector, are
  **follow-ons**: they stay in the current segment ("ok", "continue", "yes do
  it").
- For a turn vector `v`: compute cosine with the current segment centroid.
  If `>= T_SAME`, stay. Otherwise, if it is `>= T_SAME` with an earlier
  segment's centroid, it is a **return** to that topic. Otherwise it starts a
  **new topic**.
- Centroids are running means of member turn vectors, re-normalized.
- A **diversion** is any change of segment (new topic or return).
- `T_SAME` is calibrated (below) and returned in every response.

Output segments: `{id, topic_index, start_turn, end_turn, turns, label}`,
where `label` is the first 80 characters of the first user turn of that
topic, redacted. `topics` = distinct topics, `diversions` = segment changes,
`returns` = changes back to an earlier topic.

## Carried-context estimate

For each model call `c` in turn `t`, segment `s` (topic `k`):

- `base_s` = prompt size of the last call before segment `s` started (the
  context the switch inherited); 0 for the first segment.
- `f_s` = share of user turns before segment `s` that belong to topics other
  than `k`, a proxy for how much of `base_s` is unrelated.
- **Compaction or clear:** when a call's prompt size drops below 50% of the
  previous call's, everything before it is treated as gone: `base` for the
  rest of that segment becomes 0, and later segments use the post-drop
  context.
- `carried_c = min(prompt_c, base_s * f_s)`.
- Cost: split `carried_c` by the call's cache share
  (`cached_c / prompt_c`) and price both parts with
  `pricing.calculate_cost(model, uncached, 0, cached)`, using the session's
  model and provider. Unknown pricing gives cost `null`, tokens still
  reported.

Session totals: `carried_tokens`, `carried_cost`, `prompt_tokens` (all
calls), `carried_share = carried_tokens / prompt_tokens`.

**Best restart:** for each segment start turn `t_s` (s > 0), the saving of
starting a fresh session there is the carried tokens of all calls from `t_s`
on (if the session had restarted, the inherited unrelated context is gone).
Report the boundary with the largest saving: `{turn, saved_tokens,
saved_cost}`. This is an upper-bound estimate and labelled so.

## API

- `GET /drift/session/{agent}/{session_id}?project=`
- `GET /drift/project?project=&limit=` (default 50): sessions of an indexed
  project ranked by `carried_cost` (then tokens), plus totals, `by_agent`,
  coverage `{sessions, measured, not_indexed, stale, no_usage}`.

Session response:

```json
{
  "available": true, "reason": null,
  "agent": "claude", "id": "…", "title": "…", "model": "…",
  "capability": {"vectors": true, "usage": true},
  "threshold": 0.0,
  "turns": 42, "topics": 4, "diversions": 6, "returns": 2,
  "segments": [{"id": 0, "topic": 0, "start_turn": 1, "end_turn": 9, "turns": 9, "label": "…"}],
  "turn_topics": [0, 0, 0, 1, 1, 0],
  "prompt_tokens": 1830000, "carried_tokens": 412000, "carried_share": 0.225,
  "carried_cost": 0.61, "currency": "USD",
  "best_restart": {"turn": 17, "saved_tokens": 300000, "saved_cost": 0.44},
  "estimate": true
}
```

Results are cached in memory keyed by (session content fingerprint, lock id,
threshold); the project route computes lazily and reports coverage. Nothing
new is written to disk.

## UI

- **Session trace page:** a "Topic drift" card: a turn strip colored by
  topic with return markers, the numbers above, and "Starting fresh at turn
  17 would have saved about 300k tokens ($0.44)". When unavailable, the
  reason and the fix (link to Recall indexing).
- **Recall, project knowledge area:** "Topic drift in this project": totals
  and the top sessions by carried cost, each linking to its session.
- Copy says "estimate" wherever a cost appears.

## Calibration

`T_SAME` is chosen from labelled real sessions: reviewers mark, for each user
turn of a sample of sessions, whether it continues the current topic, starts
a new one, or returns to an earlier one. The threshold maximizing F1 on
"topic changed" is the default; precision and recall at that threshold are
recorded here after calibration.

## Tests

Turn/usage alignment (Claude, Codex), dedupe of repeated Claude usage,
follow-on handling, new vs return detection on synthetic vectors, compaction
reset, carried math on a hand-computed example, best restart choice,
unavailable reasons (not indexed, stale, model changed, no usage), project
ranking and coverage, route scope (only the requested project's sessions).
