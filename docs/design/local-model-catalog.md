# Local model catalog and swap advisor

Status: proposal. Written 2026-08-18.

Companion to [local-model-insights.md](local-model-insights.md), which covers
the *post-hoc* question (what happened in the local sessions you already ran).
This doc covers the *pre-download* question: which models this machine can run
at all, and which of them are worth running given what the user currently pays
for cloud.

## Why

Magnitude's CLI profiles your hardware, estimates tok/s per model before you
download, and recommends a shortlist. It answers "can my machine run this?"

TokenTelemetry can answer that too, but it also knows something Magnitude
cannot: what the user is paying right now. The interesting question is not
"will qwen3-coder-14b run" but "would it have been cheaper than the 40 Sonnet
sessions you ran last month, and how much slower".

## Reality check before designing

Two constraints came out of the data, not from guessing:

1. **No measured throughput exists yet.** 0 of 1616 sessions in the author's
   `history.db` carry a non-null `tok_per_sec`. Any claim of the form "measured
   on your machine" is false today. This is downstream of the circular-tok/s bug
   documented in the companion doc (`output_tokens / wall_clock` stamped as
   `source: "measured"`), and it lands with LM-01, not here.
2. **Local usage is real but thin.** `nemotron-3-nano:4b` (10 sessions) and
   `gemma4:12b-mlx` (5) show up in history, so the audience exists; the sample
   is too small to fit a per-machine throughput curve from.

So the first slice ships with *estimated* throughput, labelled as such, and
sharpens later rather than overclaiming now.

## Scope

**A. Fit catalog.** A hardware probe plus a committed catalog of models
(parameter count, available quants, GGUF size and VRAM/unified-memory footprint
per quant). For each model, a verdict: fits in accelerator memory, fits with
offload, or will not run. Throughput is an estimate derived from the size and
the machine class, carried at low confidence.

**B. Swap advisor.** Join A against sessions TT already priced. For a cluster of
cloud sessions, show what the same output tokens would have cost in electricity
on a locally-runnable model that fits, at the user's configured wattage and
kWh rate, alongside the throughput the user would trade away.

**C (later). Calibrated throughput.** Once LM-01 gives real per-session decode
rates, replace the generic estimate with a curve fit from the user's own runs.
B is designed to degrade to A's estimate cleanly so it can ship first.

## Constraints

- **No runtime outbound calls.** The catalog ships as a committed data file
  refreshed at build time. No Hugging Face API calls from a user machine.
- **No sudo.** The probe reads what it can without privilege: `sysctl` and
  `system_profiler` on macOS, `/proc/meminfo` and `nvidia-smi` on Linux, `wmic`
  on Windows. Where a figure is unreadable it reports unknown, matching
  `power_meter.py`'s behaviour on Apple Silicon on AC rather than fabricating.
- **Agent coverage.** Fit and swap apply to any agent that can point at a local
  endpoint; `is_local_session` (endpoint, provider, billing mode) is the
  existing test, and the UI should say which agents qualify rather than implying
  all fourteen do.

## Open decisions

- Where the catalog lives and how it is refreshed at build time.
- Whether the swap advisor clusters by session shape (short/edit/long-context)
  or stays per-model, which decides how honest the comparison is.
- Whether to surface a download action at all, or stop at the recommendation
  and leave installation to the runtime the user already has.
