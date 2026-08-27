# tokentelemetry engine

Local token and cost telemetry for AI coding agents. A single static binary that
reads logs already on your disk and makes **no network calls**.

```bash
npx tokentelemetry daily
bunx tokentelemetry monthly --model claude-opus-5 --breakdown
```

## Why this exists

This is a Go rewrite of the Python scanner and pricing table. An audit of the
Python implementation against real data (9,044 sessions, 317 Claude transcripts,
2,113 Codex rollouts) found the cost figures were wrong in five independent
ways. On that machine the reported total fell from **$19,204 to $8,497** once
they were fixed — and the new figure agrees with `ccusage` to within 2% per day
rather than diverging by up to 27x.

| Defect in the old implementation | Fix |
|---|---|
| Pricing picked the **alphabetically first** provider, so resellers beat vendors. `gpt-5.6-luna` billed at $1.00/$6.00 instead of OpenAI's $0.20/$1.20 — a 5x overcharge hiding an 80% price cut. 18% of models with a known first-party price were wrong, from 0.05x to 267x. | Providers are **ranked**; the vendor that makes the model always wins. |
| One flat price per model, no time dimension — a price cut silently repriced your entire backlog. | Rates are **effective-dated**. A call is priced at the rate in force when it happened. |
| Unknown models silently fell back to `$2/$10`, billing 965 sessions of a *free* model $380. | Unknown models are **unpriced** and reported as such. Never estimated. |
| A session was one model and one timestamp, so mid-thread model switches were mispriced and 25% of Codex cost landed on the wrong day. | The **turn** (one API call) is the atom. Per-call model, per-call clock. |
| Replayed history in resumed/forked transcripts was counted again — half of all Claude assistant messages were duplicates. | Global **dedup** on call identity, plus density-based replay detection for Codex forks. |

Also new: long-context tier pricing, per-provider cache-write rates, and the
batch service tier's 50% discount — all of which the old table dropped.

## Install

```bash
npx tokentelemetry <command>      # or bunx, or npm i -g tokentelemetry
go install github.com/VasiHemanth/tokentelemetry/engine/cmd/tokentelemetry@latest
```

The npm package is a launcher shim; the real binary ships as a per-platform
optional dependency, so you download one ~5MB binary, not six.

## Commands

```
daily | weekly | monthly     usage over time
session | model | project    usage by dimension
price <model>                a model's rate history
agents                       detected agents and their log paths
```

### Filters

Every report command accepts these. `ccusage` offers only `--since`/`--until`.

```
--since / --until DATE   local-day bounds, inclusive
--agent NAME             repeatable
--model NAME             repeatable
--project NAME           full path or just the folder name
--subagents MODE         include (default) | only | exclude
--group-by DIMS          nest rows (default: model). day, week, month, agent,
                         model, provider, project, session, or "none" for flat.
                         e.g. --group-by agent,model
--compact                abbreviate counts (1.2M) instead of full digits
--verbose                add scan diagnostics
--json                   machine-readable
--limit N
```

Rows break down per model and print full counts by default. Listing model names
beside a row's combined figures would say which models were involved but not how
much each one cost — a row per model costs no extra screen and makes every
number attributable.

```
  DATE         MODEL                 INPUT    OUTPUT     CACHE W       CACHE R         TOTAL     COST
  ───────────────────────────────────────────────────────────────────────────────────────────────────
  2026-08-26   All                 334,030   149,403     508,408    16,988,615    17,980,456   $17.77
               - claude-opus-5         210   121,660     508,408    14,080,711    14,710,989   $15.17
               - gpt-5.6-sol       211,219    18,211           —     2,268,160     2,497,590    $2.12
               - gpt-5.6-terra     122,601     9,532           —       639,744       771,877    $0.49
```

Nest further with `--group-by agent,model`, or drop back to one row per day with
`--group-by none`.

```bash
tokentelemetry daily --since 2026-08-01 --agent claude
tokentelemetry daily --group-by agent,model
tokentelemetry monthly --group-by provider
tokentelemetry session --limit 10 --json
```

## What you actually pay

List price is the comparable unit, but it is not a bill. Tell the tool what your
flat plans cost in `~/.tokentelemetry/plans.json` and it shows real spend beside
it, prorated per calendar day over exactly the window on screen:

```json
{
  "subscriptions": [
    { "agent": "codex",  "name": "ChatGPT",    "monthly_usd": 100 },
    { "agent": "claude", "name": "Claude Pro", "monthly_usd": 20 }
  ]
}
```

```
    Total cost                $1,959.15   at API list rates
      of which subscription   $1,959.15   covered by a flat plan
    You actually paid           $104.52   ChatGPT $87.10 + Claude Pro $17.42 · 27 days
      Leverage                      19x   list value per dollar paid
```

Without the file, no real-spend line is shown — never a guess.

## What the cost number means

**Every turn is priced at API list rates, always** — including traffic a flat
subscription already covered and models running on local hardware. One unit,
comparable across every agent.

The old implementation returned `0.0` for subscription-backed endpoints, which
made the headline meaningless: Hermes reported $0 while Codex reported $18,558
for traffic on the same ChatGPT subscription. Here the total is always list
price and the footer splits it by how it was actually paid:

```
    Total cost                $8,511.69   at API list rates
    Turns                       129,155   across 2,145 sessions
    Tokens                       13.84B   cache read 95% · input 4% · output <1%
      of which subscription   $8,511.69   covered by a flat plan

    !  230 turns unpriced and excluded — codex-auto-review
    ·  rates 2026-08-27 · 97% of cost predates our price history
```

A `!` means money is missing from the total and cannot be inferred from anything
else on screen. Nothing else earns one — diagnostics like dedup counts live
behind `--verbose`, because a caveat that fires on every run is one nobody reads.

That last line is the honest part. Price history is real but shallow: the
committed snapshots can date a rate backwards only where they agree with the
current first-party price, and they are rejected outright where they record the
reseller figure the old alphabetical sync mistakenly picked. So a backlog older
than the history is priced at the earliest rate on file **and told how much of
the total that covers**. Every sync appends a dated rate, so the caveat shrinks.

## Pricing data

`internal/pricing/data/pricing.json` is generated, committed, and embedded in
the binary. Regenerate it (maintainer/CI only — this is the only code in the
repo that touches the network):

```bash
go run ./cmd/pricing-sync              # append today's rates, reporting changes
go run ./cmd/pricing-sync -dry-run     # show what would change

# Date existing rates backwards from an old schema-1 snapshot. Only ever moves a
# date, never introduces a rate — a snapshot that records a reseller's price is
# rejected rather than written into history.
go run ./cmd/pricing-sync -backfill old/pricing_data.json -as-of 2026-07-14
```

Override a rate locally without waiting for a release by writing
`~/.tokentelemetry/pricing.json` in the same schema, or point `TT_PRICING_FILE`
at one.

## Development

```bash
go test ./...
go run ./cmd/tokentelemetry daily
node scripts/build-npm.mjs             # cross-compile all 6 targets + npm layout
```

Supported today: Claude Code, Codex CLI. The remaining agents from the Python
implementation (OpenCode, Hermes, Antigravity, Copilot, Cursor, Gemini, Qwen,
Grok, Cline, Pi) still need porting; `internal/ingest` is the only package that
has to grow — implement `Scanner` and add it to `All()`.
