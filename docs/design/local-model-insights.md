# Local model insights

Status: proposal. Written 2026-08-13 from measurements against a live
`llama-server` on the author's machine, plus a research sweep over the telemetry
surfaces of eight local runtimes and the speculative-decoding / roofline
literature.

## Why

Local sessions get the thinnest insights in the product. A user ran a 28B model
and got 1,295 tokens in 7m14s (2.98 tok/s aggregate) and the dashboard had
nothing to say about it. The engines already publish the numbers that would
explain it; we don't read them.

## Measurement setup

Apple M5, 34 GB unified memory. `llama-server` build `b1-f65e568` serving
Muse Glimmer 28B (`Q4_K - Medium`, 16.76 GB GGUF, 52 blocks, GQA kv-heads 2,
sliding window 2048) with a DFlash draft (1.63 GB), `--spec-draft-n-max 15`,
`--ctx-size 8192`, `--cache-type-k/v q8_0`, `--flash-attn on`, `--parallel 1`.

15 generations total: 8 workload-varied, 6 repeated short prompts on an
otherwise-quiet machine, 1 paging probe. Raw data in the session scratchpad
(`bench_results.json`, `paging_corr.json`).

## What the measurements show

**Draft acceptance predicts decode speed, strongly.** On the quiet-machine set,
acceptance rate vs decode tok/s gives **r = 0.936** (n=6). Across the
workload-varied set acceptance ranged 19%–78% and decode tracked it:

| workload | acceptance | decode tok/s |
|---|---|---|
| summarize, short ctx | 78% | 14.32 |
| counting | 51% | 11.84 |
| code | 34% | 8.61 |
| factual | 29% | 6.52 |
| prose | 19% | 5.33 |
| long ctx | 19% | 4.18 |

At 19% acceptance the draft spends ~15 sequential forward passes to contribute
~3 tokens, while holding 1.63 GB. Whether that is a net win is measurable and
currently invisible.

**The machine sits at roughly 20% of its memory-bandwidth floor.** Computing MBU
over *verify steps* (target forward passes = `predicted_n - draft_n_accepted`)
rather than emitted tokens gives ~21–23%. The emitted-token version gives ~92%.
Those are opposite verdicts from identical data, and the emitted-token form is
the wrong one — speculative decoding emits several tokens per weight read, so it
can exceed 100% and read as a bug. Any roofline panel must divide by verify
steps.

**Memory pressure was not the explanation.** Swap sat at 15.7/16 GB with 5% free
memory, and a single 64-token generation showed 13.7 GB of compressor
decompressions — which looks damning. It doesn't hold up. On the quiet machine,
decompression volume vs decode speed gives **r = +0.52** (n=6): more
decompression went with *faster* decode. The first correlation batch was
confounded by five research subagents running concurrently (load average 6.4);
under that load decode fell to 1.82–3.48 tok/s versus 4.81–6.20 tok/s quiet.
Contention, not paging.

The lesson generalizes to the feature: if a slowdown can't be cleanly attributed
with full shell access, a panel asserting "you're thrashing" will misfire. The
memory-pressure feature (LM-10) must be worded correlationally and plot the two
series, never claim causation.

**Reasoning tokens are invisible and unbudgeted.** All 15 runs returned empty
`content`; 235–327 characters went to `reasoning_content` every time. At a
64-token budget this model never reaches an answer. Users pay full latency and
electricity for tokens they never see, and nothing in the product says so.

**Prompt cache reuse works and is measurable.** A repeated prompt reprocessed 5
of 72 tokens; a long-context turn reused 502 of 663.

## Bug in shipped code: local tok/s is circular

`backend/main.py:2283` computes SmallCode's throughput as
`tok_per_sec_from_duration(output_tokens, durationMs)` — output tokens over
whole-session wall clock. That value is stamped on the session, and
`backend/insights.py:141` passes it to `resolve_tok_per_sec()`, which labels any
positive number `"measured"`.

Two consequences:

1. The UI shows a wall-clock-derived rate with `tok_per_sec_source: "measured"`.
   It is not measured throughput; it is the session duration restated.
2. `gen_seconds = output_tokens / tok_per_sec` collapses to the session wall
   clock identically, so `energy_wh = wall_clock_seconds × loadWatts / 3600`.
   Tool calls, model think time, and idle gaps are all billed as if the GPU were
   generating throughout. Local energy, cost, CO2, and cloud-savings figures are
   over-estimates by whatever fraction of the session wasn't generation — on the
   measured session, about 64%.

The fallback path is worse: `default_tok_per_sec_for_model()` parses a size tag
out of the model name, so any "time not spent generating" arithmetic built on it
can go negative.

This lands before any new feature, because every per-session local insight
depends on it.

## Candidate features

Sixteen candidates were designed and adversarially reviewed on feasibility and
correctness. Ranked by value over effort, with review verdicts folded in.

| id | feature | value | effort | notes from review |
|---|---|---|---|---|
| LM-15 | Local runtime attribution (stop billing local at cloud rates) | high | M | prerequisite; only 4 of ~14 scanners stamp `provider`/`billing_mode`, and the Settings billing-mode override is never written onto session dicts |
| LM-14 | Runtime config audit from one `/props` GET | high | S | verified findings on this server: `endpoint_metrics=false`, `n_ctx` 8192 vs GGUF `context_length` 131072 |
| LM-09 | Partial GPU offload detector | high | S | reads Ollama's `offloaded X/Y layers` line; gate the `size_vram` cross-check to discrete GPUs |
| LM-08 | Context overflow / silent truncation | high | S | Ollama logs `truncated` verbatim; llama.cpp needs inference from token counts |
| LM-07 | Context-length RAM budget | medium | S | verified 27.6 KiB/token here → 8k KV is 0.232 GB, so context is *not* this user's memory problem |
| LM-05 | Reasoning-token overhead | high | M | re-express energy per *visible* token; also flag `reasoning_format` mismatches |
| LM-06 | KV cache reuse / re-prefill per turn | high | M | `cache_n`, `n_prompt_tokens_cache` |
| LM-03 | Is speculative decoding earning its keep | high | M | one reviewer voted kill: Leviathan Thm 3.8's `γ·c` assumes one draft forward per drafted token, which is wrong for block drafters like DFlash and yields a bogus 0.62× |
| LM-10 | Memory pressure correlation | high | M | correlational wording only, per the finding above; use deltas over the session window, not macOS's sticky `used` |
| LM-04 | Percent of memory-bandwidth roofline | high | L | must divide by verify steps; hide when the chip's peak bandwidth is unknown rather than defaulting |
| LM-01 | Session time accounting | high | M | **revise** — as designed it's circular against the bug above; compute in-model time from summed per-call latency (Hermes `agent.log` carries `latency_s` *and* a session id) and clamp ≥ 0 |
| LM-02 | Prefill vs decode split | high | M | **revise** — use `predicted_n - 1`, matching llama.cpp's own `n_gen_steps()`; not recoverable post-hoc for llama.cpp without a log or tap |
| LM-13 | Throughput baseline / regression tracking | medium | M | value is the confounder diff (build, n_ctx, spec on/off), not the number |
| LM-12 | Quant advisor | medium | M | scale off the measured baseline via the roofline |
| LM-11 | Model reload churn | medium | S | subtract `load_duration` from `total_duration` or cold starts read as slow inference |
| LM-16 | Opt-in loopback telemetry tap | high | L | the only route to exact per-request, per-session data; puts TT in the request path, so off by default |

## Capture routes

Ranked by what they cost the user.

1. **Live probe** (extends the existing `/local-runtime` Ollama probe to
   llama.cpp): `/props`, `/slots`, `/health`. Free, read-only, no history.
   Enough for LM-14, LM-07, and the on/off half of LM-03.
2. **Log scan.** `llama-server` already prints per-request `prompt eval time`,
   `eval time`, and `draft acceptance = 0.xxxxx (N accepted / M generated), mean
   len = X` (`tools/server/server-context.cpp:599-633`) and accepts
   `--log-file`. Ollama writes `~/.ollama/logs/server*.log`. This is the pattern
   TT already uses for every other harness, and it needs no request-path
   involvement.
3. **`--metrics`.** Adds `spec_decode_num_drafts_total` (verification steps —
   the denominator LM-04 needs), `n_decode_total`, and throughput gauges.
   Requires a server restart, so surface it as advice, not a dependency.
4. **Loopback tap** (LM-16). Exact per-request data; in the request path.

## Open decisions

- **Which tier to build first.** The prerequisite (LM-15) plus the four S-effort
  features is a coherent first slice and needs no new capture mechanism beyond
  the live probe.
- **Whether to ship the tap at all.** It's the only source of per-request
  ground truth, and it's also the only option that can break someone's
  inference.
- **`--spec-draft-n-max` tuning is untested.** There is no per-request override,
  so comparing draft depths needs a server restart. Worth measuring: at 19%
  acceptance on prose, a lower depth is likely faster.

## Caveats

Single machine, single model, small n. The acceptance↔throughput correlation
(r = 0.936, n = 6) is strong but was measured on one model with one drafter on
one chip; it should be re-measured elsewhere before any UI states a threshold.
The peak-bandwidth figure for Apple M5 was not independently verified here, which
is why LM-04 is L-effort and gated on a per-chip table.
