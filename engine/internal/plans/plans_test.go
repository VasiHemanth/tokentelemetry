package plans

import (
	"math"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func day(s string) time.Time {
	t, err := time.ParseInLocation("2006-01-02", s, time.Local)
	if err != nil {
		panic(err)
	}
	return t
}

func cfg() Config {
	return Config{Subscriptions: []Subscription{
		{Agent: "codex", Name: "ChatGPT", MonthlyUSD: 100},
		{Agent: "claude", Name: "Claude Pro", MonthlyUSD: 20},
	}}
}

func near(t *testing.T, got, want float64) {
	t.Helper()
	if math.Abs(got-want) > 0.005 {
		t.Errorf("got %.4f, want %.4f", got, want)
	}
}

// A full calendar month costs exactly the monthly fee, with no averaging error.
func TestFullMonthIsExactlyTheFee(t *testing.T) {
	c := cfg().ChargesFor(day("2026-08-01"), day("2026-08-31"), nil)
	near(t, Total(c), 120)
}

// Partial windows prorate against that month's own length, not an average, so
// the same 27 days cost differently in February and August.
func TestProrationUsesTheRealMonthLength(t *testing.T) {
	aug := cfg().ChargesFor(day("2026-08-01"), day("2026-08-27"), nil)
	near(t, Total(aug), 120*27/31.0)

	feb := cfg().ChargesFor(day("2026-02-01"), day("2026-02-27"), nil)
	near(t, Total(feb), 120*27/28.0)

	if Total(aug) >= Total(feb) {
		t.Error("27 days of August should cost less than 27 days of February")
	}
}

// A window spanning a month boundary charges each part at its own month length.
func TestWindowAcrossMonths(t *testing.T) {
	c := cfg().ChargesFor(day("2026-07-30"), day("2026-08-02"), nil)
	// 2 days of July (31) + 2 days of August (31)
	near(t, Total(c), 120*2/31.0+120*2/31.0)
}

// Filtering to one agent must not bill the other agent's plan.
func TestAgentFilterRestrictsPlans(t *testing.T) {
	c := cfg().ChargesFor(day("2026-08-01"), day("2026-08-31"), []string{"claude"})
	if len(c) != 1 || c[0].Agent != "claude" {
		t.Fatalf("charges = %+v, want only claude", c)
	}
	near(t, Total(c), 20)
}

// A plan is only charged for the period it was actually held.
func TestSubscriptionDateBounds(t *testing.T) {
	c := Config{Subscriptions: []Subscription{
		{Agent: "codex", Name: "ChatGPT", MonthlyUSD: 100, From: "2026-08-15"},
	}}
	charges := c.ChargesFor(day("2026-08-01"), day("2026-08-31"), nil)
	near(t, Total(charges), 100*17/31.0) // 15th..31st inclusive

	before := c.ChargesFor(day("2026-07-01"), day("2026-07-31"), nil)
	if len(before) != 0 {
		t.Errorf("charged %+v for a window before the plan started", before)
	}
}

// Absent or malformed config yields no real-spend line — never a guess.
func TestMissingConfigIsEmpty(t *testing.T) {
	t.Setenv("TT_PLANS_FILE", filepath.Join(t.TempDir(), "nope.json"))
	if !Load().Empty() {
		t.Error("missing plans file produced subscriptions")
	}

	bad := filepath.Join(t.TempDir(), "plans.json")
	if err := os.WriteFile(bad, []byte("{not json"), 0o644); err != nil {
		t.Fatal(err)
	}
	t.Setenv("TT_PLANS_FILE", bad)
	if !Load().Empty() {
		t.Error("malformed plans file produced subscriptions")
	}
}

// Entries with no usable fee are dropped rather than treated as free.
func TestZeroFeeEntriesDropped(t *testing.T) {
	path := filepath.Join(t.TempDir(), "plans.json")
	body := `{"subscriptions":[{"agent":"codex","monthly_usd":0},{"agent":"","monthly_usd":9},{"agent":"claude","monthly_usd":20}]}`
	if err := os.WriteFile(path, []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
	t.Setenv("TT_PLANS_FILE", path)
	c := Load()
	if len(c.Subscriptions) != 1 || c.Subscriptions[0].Agent != "claude" {
		t.Errorf("subscriptions = %+v, want only the claude entry", c.Subscriptions)
	}
}
