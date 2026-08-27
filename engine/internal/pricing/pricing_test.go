package pricing

import (
	"os"
	"testing"
	"time"
)

func day(s string) time.Time {
	t, err := time.ParseInLocation("2006-01-02", s, time.Local)
	if err != nil {
		panic(err)
	}
	return t.Add(12 * time.Hour)
}

func testTable() *Table {
	return &Table{
		Updated: MustParseDate("2026-08-27"),
		Models: map[string]*Model{
			// A model that took an 80% cut mid-window — the gpt-5.6-luna case.
			"luna": {ID: "luna", FirstParty: true, Rates: []Rate{
				{From: MustParseDate("2026-01-01"), In: 1.00, Out: 6.00, CacheRead: 0.10},
				{From: MustParseDate("2026-08-15"), In: 0.20, Out: 1.20, CacheRead: 0.02},
			}},
			"tiered": {ID: "tiered", Rates: []Rate{{
				From: MustParseDate("2026-01-01"), In: 2, Out: 12, CacheRead: 0.2,
				TierThreshold: 272000, TierIn: 4, TierOut: 18, TierCacheRead: 0.4,
			}}},
		},
		ByProvider: map[string]*Model{
			"together\x00luna": {ID: "luna", Rates: []Rate{
				{From: MustParseDate("2026-01-01"), In: 1.40, Out: 4.40},
			}},
		},
		Aliases: map[string]string{"luna-v2": "luna"},
	}
}

// A price cut must not retroactively reprice earlier usage. This is the whole
// reason the schema carries dates.
func TestRateIsEffectiveDated(t *testing.T) {
	tbl := testTable()
	for _, tc := range []struct {
		when   string
		wantIn float64
	}{
		{"2026-06-01", 1.00}, // before the cut
		{"2026-08-14", 1.00}, // day before
		{"2026-08-15", 0.20}, // day of
		{"2026-08-27", 0.20}, // after
	} {
		r, conf, ok := tbl.Lookup("luna", "", day(tc.when))
		if !ok || conf != ConfidenceExact {
			t.Fatalf("%s: lookup failed (conf=%v)", tc.when, conf)
		}
		if r.In != tc.wantIn {
			t.Errorf("%s: input rate = %v, want %v", tc.when, r.In, tc.wantIn)
		}
	}
}

// Usage older than any rate we hold is priced at the earliest known rate rather
// than refused, but callers are told via RateNewerThanCall (see package cost).
func TestPreHistoryUsesEarliestRate(t *testing.T) {
	tbl := testTable()
	r, _, ok := tbl.Lookup("luna", "", day("2025-03-01"))
	if !ok || r.In != 1.00 {
		t.Fatalf("pre-history rate = %v (ok=%v), want 1.00", r.In, ok)
	}
}

// A recorded provider wins, because it says who actually billed the call.
func TestProviderOverridesFlatTable(t *testing.T) {
	tbl := testTable()
	r, conf, ok := tbl.Lookup("luna", "together", day("2026-08-27"))
	if !ok || conf != ConfidenceProvider {
		t.Fatalf("conf = %v, want provider", conf)
	}
	if r.In != 1.40 {
		t.Errorf("input rate = %v, want 1.40 (Together's markup)", r.In)
	}
}

// The long-context surcharge must apply above the threshold and not below.
func TestContextTierApplies(t *testing.T) {
	tbl := testTable()
	r, _, _ := tbl.Lookup("tiered", "", day("2026-08-27"))

	in, out, cr, _ := r.ForContext(100_000)
	if in != 2 || out != 12 || cr != 0.2 {
		t.Errorf("under threshold = %v/%v/%v, want 2/12/0.2", in, out, cr)
	}
	in, out, cr, _ = r.ForContext(300_000)
	if in != 4 || out != 18 || cr != 0.4 {
		t.Errorf("over threshold = %v/%v/%v, want 4/18/0.4", in, out, cr)
	}
}

// An unknown model must resolve to nothing. The old table fell back to a
// substring scan and then a $2/$10 default, which billed a free model $380.
func TestUnknownModelIsUnpricedNotGuessed(t *testing.T) {
	tbl := testTable()
	for _, id := range []string{"totally-made-up", "luna-turbo-9000", "codex-auto-review"} {
		if _, conf, ok := tbl.Lookup(id, "", day("2026-08-27")); ok || conf != ConfidenceUnpriced {
			t.Errorf("%s: resolved to %v, want unpriced", id, conf)
		}
	}
}

// Aliases are explicit equivalences, never substring guesses.
func TestAliasResolves(t *testing.T) {
	tbl := testTable()
	r, conf, ok := tbl.Lookup("luna-v2", "", day("2026-08-27"))
	if !ok || conf != ConfidenceAlias || r.In != 0.20 {
		t.Errorf("alias lookup = %v/%v/%v, want alias@0.20", r.In, conf, ok)
	}
}

func TestNormalize(t *testing.T) {
	for in, want := range map[string]string{
		"claude-opus-5":                      "claude-opus-5",
		"CLAUDE-OPUS-5":                      "claude-opus-5",
		"  claude-opus-5  ":                  "claude-opus-5",
		"openrouter/anthropic/claude-opus-5": "claude-opus-5",
		"moonshotai/kimi-k2":                 "kimi-k2",
		"claude-opus-5-v1:0":                 "claude-opus-5-v1",
		"grok-4.3-latest":                    "grok-4.3",
	} {
		if got := Normalize(in); got != want {
			t.Errorf("Normalize(%q) = %q, want %q", in, got, want)
		}
	}
}

// The shipped dataset must load, be current-schema, and carry the first-party
// rates rather than a reseller's. This is the regression guard for the
// alphabetical-provider bug.
func TestEmbeddedDatasetIsFirstParty(t *testing.T) {
	tbl, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if len(tbl.Models) < 100 {
		t.Fatalf("dataset has only %d models, expected the full table", len(tbl.Models))
	}
	for _, id := range []string{"gpt-5.6-luna", "gpt-5.6-terra", "claude-opus-5"} {
		m, ok := tbl.Models[id]
		if !ok {
			t.Errorf("%s missing from the shipped dataset", id)
			continue
		}
		if !m.FirstParty {
			t.Errorf("%s priced from %q, expected a first-party vendor", id, m.Rates[0].Source)
		}
	}
}

// A user override must win outright. Provider-keyed rates are consulted before
// the flat table, so a shipped one would silently beat the override for any
// agent that records its provider — making the override look broken.
func TestUserOverrideBeatsProviderKeyedRate(t *testing.T) {
	dir := t.TempDir()
	path := dir + "/pricing.json"
	body := `{"schema":2,"models":{"m1":{"id":"m1","rates":[{"from":"2026-01-01","in":9,"out":99}]}}}`
	if err := os.WriteFile(path, []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
	t.Setenv("TT_PRICING_FILE", path)

	tbl := &Table{
		Models:     map[string]*Model{"m1": {ID: "m1", Rates: []Rate{{From: MustParseDate("2026-01-01"), In: 1, Out: 1}}}},
		ByProvider: map[string]*Model{"anthropic\x00m1": {ID: "m1", Rates: []Rate{{From: MustParseDate("2026-01-01"), In: 2, Out: 2}}}},
		Aliases:    map[string]string{},
	}
	applyOverride(tbl)

	r, _, ok := tbl.Lookup("m1", "anthropic", day("2026-06-01"))
	if !ok || r.Out != 99 {
		t.Errorf("output rate = %v (ok=%v), want 99 from the override, not the provider table", r.Out, ok)
	}
}
