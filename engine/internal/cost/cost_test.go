package cost

import (
	"math"
	"testing"
	"time"

	"github.com/VasiHemanth/tokentelemetry/engine/internal/model"
	"github.com/VasiHemanth/tokentelemetry/engine/internal/pricing"
)

func at(s string) time.Time {
	t, err := time.ParseInLocation("2006-01-02", s, time.Local)
	if err != nil {
		panic(err)
	}
	return t.Add(12 * time.Hour)
}

func table() *pricing.Table {
	return &pricing.Table{
		Updated: pricing.MustParseDate("2026-08-27"),
		Models: map[string]*pricing.Model{
			"m1": {ID: "m1", Rates: []pricing.Rate{{
				From: pricing.MustParseDate("2026-01-01"),
				In:   10, Out: 100, CacheRead: 1, CacheWrite: 12.5, CacheWrite1h: 20,
			}}},
		},
		ByProvider: map[string]*pricing.Model{},
		Aliases:    map[string]string{},
	}
}

func near(t *testing.T, got, want float64) {
	t.Helper()
	if math.Abs(got-want) > 1e-9 {
		t.Errorf("cost = %v, want %v", got, want)
	}
}

func TestPricesEachBucketAtItsOwnRate(t *testing.T) {
	c := Of(model.Turn{
		Model:     "m1",
		Timestamp: at("2026-06-01"),
		Usage: model.Usage{
			Input: 1_000_000, Output: 1_000_000,
			CacheRead: 1_000_000, CacheWrite: 1_000_000,
		},
	}, table())
	// 10 + 100 + 1 + 12.5
	near(t, c.USD, 123.5)
}

// The 1-hour cache TTL bills at a different rate from the 5-minute one, and the
// 1h tokens are a SUBSET of the cache-write total, not an extra bucket.
func TestCacheWrite1hIsASubsetPricedSeparately(t *testing.T) {
	c := Of(model.Turn{
		Model:     "m1",
		Timestamp: at("2026-06-01"),
		Usage:     model.Usage{CacheWrite: 1_000_000, CacheWrite1h: 400_000},
	}, table())
	// 600k at 12.5 + 400k at 20
	near(t, c.USD, 0.6*12.5+0.4*20)
}

// Batch traffic bills at half rate everywhere it is offered.
func TestBatchTierHalvesCost(t *testing.T) {
	base := model.Turn{Model: "m1", Timestamp: at("2026-06-01"), Usage: model.Usage{Output: 1_000_000}}
	std := Of(base, table())
	base.ServiceTier = "batch"
	batch := Of(base, table())
	near(t, std.USD, 100)
	near(t, batch.USD, 50)
}

// Subscription-backed traffic is still priced at list. Zeroing it is what made
// the old headline total incomparable across agents.
func TestSubscriptionIsLabelledNotZeroed(t *testing.T) {
	c := Of(model.Turn{
		Model:     "m1",
		Agent:     model.AgentCodex,
		Endpoint:  "https://chatgpt.com/backend-api/codex",
		Timestamp: at("2026-06-01"),
		Usage:     model.Usage{Output: 1_000_000},
	}, table())
	if c.Billing != BillingSubscription {
		t.Errorf("billing = %v, want subscription", c.Billing)
	}
	near(t, c.USD, 100)
}

func TestLocalIsLabelledNotZeroed(t *testing.T) {
	c := Of(model.Turn{
		Model:     "m1",
		Provider:  "ollama",
		Timestamp: at("2026-06-01"),
		Usage:     model.Usage{Output: 1_000_000},
	}, table())
	if c.Billing != BillingLocal {
		t.Errorf("billing = %v, want local", c.Billing)
	}
	near(t, c.USD, 100)
}

// An unpriced turn contributes nothing and says so. It must never look free.
func TestUnpricedTurnIsFlagged(t *testing.T) {
	c := Of(model.Turn{
		Model:     "no-such-model",
		Timestamp: at("2026-06-01"),
		Usage:     model.Usage{Output: 5_000_000},
	}, table())
	if c.Priced() {
		t.Fatal("unknown model reported as priced")
	}
	near(t, c.USD, 0)
}

// Pricing a call with a rate that post-dates it is allowed but must be
// reported, so a backlog repriced by a later cut is visible.
func TestRateNewerThanCallIsFlagged(t *testing.T) {
	tbl := table()
	tbl.Models["m1"].Rates[0].From = pricing.MustParseDate("2026-08-01")

	older := Of(model.Turn{Model: "m1", Timestamp: at("2026-07-01"), Usage: model.Usage{Output: 1}}, tbl)
	if !older.RateNewerThanCall {
		t.Error("call predating every known rate was not flagged")
	}
	newer := Of(model.Turn{Model: "m1", Timestamp: at("2026-08-15"), Usage: model.Usage{Output: 1}}, tbl)
	if newer.RateNewerThanCall {
		t.Error("call after the rate took effect was wrongly flagged")
	}
}

// An agent can mix billing routes within one binary: OpenCode serves its own
// free models, bring-your-own-key API traffic, and a GitHub Copilot
// subscription. Calling all of it "metered API" misreports which dollars are
// real money.
func TestProviderDecidesBillingForMixedAgents(t *testing.T) {
	base := model.Turn{
		Model: "m1", Agent: model.AgentOpenCode,
		Timestamp: at("2026-06-01"), Usage: model.Usage{Output: 1_000_000},
	}
	for provider, want := range map[string]Billing{
		"openai":         BillingAPI,
		"anthropic":      BillingAPI,
		"moonshotai":     BillingAPI,
		"github-copilot": BillingSubscription,
		"ollama":         BillingLocal,
	} {
		base.Provider = provider
		if got := Of(base, table()).Billing; got != want {
			t.Errorf("provider %q billed as %v, want %v", provider, got, want)
		}
	}
}
