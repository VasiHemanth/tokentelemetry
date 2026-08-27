// Package cost turns a turn's token counts into dollars.
//
// Every turn is priced at API list rates, always — including traffic that a
// flat subscription actually covered and models running on local hardware.
// That is a deliberate change from the Python implementation, which returned
// 0.0 for subscription-backed endpoints and re-priced local models by
// electricity. Mixing real-bill zeros with list-price estimates made the
// headline total meaningless: Hermes reported $0 while Codex reported $18,558
// for traffic on the same ChatGPT subscription.
//
// One unit, comparable across every agent. Billing reports *how* the tokens
// were paid for so the UI can caveat the number, but it never changes the
// number.
package cost

import (
	"github.com/VasiHemanth/tokentelemetry/engine/internal/model"
	"github.com/VasiHemanth/tokentelemetry/engine/internal/pricing"
)

// Billing describes how a turn was actually paid for. It annotates the cost,
// it does not alter it.
type Billing uint8

const (
	// BillingAPI is metered pay-per-token against an API key. The list-price
	// figure approximates the real bill.
	BillingAPI Billing = iota
	// BillingSubscription is covered by a flat monthly fee (ChatGPT plans,
	// Claude Pro/Max, Copilot). The figure is what the same tokens would have
	// cost on the API — useful for comparison, not a bill.
	BillingSubscription
	// BillingLocal ran on the user's own hardware. The figure is the cloud
	// equivalent, which doubles as the saving versus renting it.
	BillingLocal
)

func (b Billing) String() string {
	switch b {
	case BillingSubscription:
		return "subscription"
	case BillingLocal:
		return "local"
	default:
		return "api"
	}
}

// Cost is a priced turn.
type Cost struct {
	USD        float64
	Confidence pricing.Confidence
	Billing    Billing
	// Model is the normalised id the rate was found under, which can differ
	// from what the agent recorded when an alias resolved it.
	Model string
	// RateNewerThanCall is set when the only rate we hold took effect AFTER
	// this call happened, so the call is priced at a rate that was not in force
	// at the time. It is reported rather than hidden: price history only starts
	// accumulating from the first sync, and pretending otherwise is how a
	// backlog silently gets repriced by a later cut.
	RateNewerThanCall bool
}

// Priced reports whether a rate was actually found. An unpriced turn has a zero
// USD that means "unknown", not "free", and callers must not add it to a total
// without also counting it as unpriced.
func (c Cost) Priced() bool { return c.Confidence != pricing.ConfidenceUnpriced }

// Of prices a single turn at the rates in force when the turn happened.
func Of(t model.Turn, tbl *pricing.Table) Cost {
	id := pricing.Normalize(t.Model)
	c := Cost{Model: id, Billing: classify(t)}

	rate, conf, ok := tbl.Lookup(t.Model, t.Provider, t.Timestamp)
	c.Confidence = conf
	if !ok {
		return c
	}
	if !t.Timestamp.IsZero() && rate.From.After(pricing.DateOf(t.Timestamp)) {
		c.RateNewerThanCall = true
	}

	u := t.Usage
	// The long-context tier keys off the prompt actually sent, which is the
	// whole prompt: fresh input plus everything served from cache.
	ctx := u.ContextTokens
	if ctx == 0 {
		ctx = u.Input + u.CacheRead + u.CacheWrite
	}
	in, out, cacheRead, cacheWrite := rate.ForContext(ctx)

	write1h := min64(u.CacheWrite1h, u.CacheWrite)
	write5m := u.CacheWrite - write1h
	rate1h := rate.CacheWrite1h
	if rate1h == 0 {
		rate1h = cacheWrite
	}

	c.USD = perMillion(u.Input, in) +
		perMillion(u.Output, out) +
		perMillion(u.CacheRead, cacheRead) +
		perMillion(write5m, cacheWrite) +
		perMillion(write1h, rate1h)
	c.USD *= tierMultiplier(t.ServiceTier)
	return c
}

// tierMultiplier applies the provider's service-tier discount.
//
// Batch is the only tier with a rate published uniformly enough to apply
// blind: OpenAI, Anthropic and Google all bill asynchronous batch traffic at
// half the synchronous rate. Priority/scale tiers carry negotiated premiums
// that vary per account, so they are left at list rather than guessed at.
func tierMultiplier(tier string) float64 {
	switch tier {
	case "batch":
		return 0.5
	default:
		return 1.0
	}
}

func perMillion(tokens int64, rate float64) float64 {
	if tokens <= 0 || rate == 0 {
		return 0
	}
	return float64(tokens) / 1_000_000 * rate
}

func min64(a, b int64) int64 {
	if a < b {
		return a
	}
	return b
}
