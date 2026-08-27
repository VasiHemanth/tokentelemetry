package report

import (
	"testing"
	"time"

	"github.com/VasiHemanth/tokentelemetry/engine/internal/model"
	"github.com/VasiHemanth/tokentelemetry/engine/internal/pricing"
)

func tbl() *pricing.Table {
	return &pricing.Table{
		Updated: pricing.MustParseDate("2026-08-27"),
		Models: map[string]*pricing.Model{
			"cheap": {ID: "cheap", Rates: []pricing.Rate{{From: pricing.MustParseDate("2026-01-01"), Out: 1}}},
			"dear":  {ID: "dear", Rates: []pricing.Rate{{From: pricing.MustParseDate("2026-01-01"), Out: 100}}},
		},
		ByProvider: map[string]*pricing.Model{},
		Aliases:    map[string]string{},
	}
}

func turn(id, m, project string, ts time.Time, out int64) model.Turn {
	return model.Turn{
		Key: id, SessionID: "sess", Agent: model.AgentClaude,
		Timestamp: ts, Model: m, Project: project,
		Usage: model.Usage{Output: out},
	}
}

func local(y int, mo time.Month, d, h, mi int) time.Time {
	return time.Date(y, mo, d, h, mi, 0, 0, time.Local)
}

func find(rows []Bucket, key string) (Bucket, bool) {
	for _, r := range rows {
		if r.Key == key {
			return r, true
		}
	}
	return Bucket{}, false
}

// A session running across midnight must contribute to both local days. The
// old session-level rollup charged the whole thing to the last day, which put
// 25% of Codex cost on the wrong date.
func TestSessionSpanningMidnightSplitsAcrossDays(t *testing.T) {
	turns := []model.Turn{
		turn("a", "cheap", "/p", local(2026, 8, 1, 23, 50), 1_000_000),
		turn("b", "cheap", "/p", local(2026, 8, 2, 0, 10), 3_000_000),
	}
	rep := Build(turns, tbl(), Filter{}, Daily, 0, nil)

	d1, ok1 := find(rep.Series, "2026-08-01")
	d2, ok2 := find(rep.Series, "2026-08-02")
	if !ok1 || !ok2 {
		t.Fatalf("expected both days, got %v", rep.Series)
	}
	if d1.Usage.Output != 1_000_000 || d2.Usage.Output != 3_000_000 {
		t.Errorf("split = %d/%d, want 1000000/3000000", d1.Usage.Output, d2.Usage.Output)
	}
}

// Day keys are LOCAL days. Formatting a local midnight through UTC rolls it
// back a day for anyone east of Greenwich.
func TestDayBucketsAreLocal(t *testing.T) {
	ts := local(2026, 8, 2, 0, 30)
	rep := Build([]model.Turn{turn("a", "cheap", "/p", ts, 1)}, tbl(), Filter{}, Daily, 0, nil)
	if got := rep.Series[0].Key; got != "2026-08-02" {
		t.Errorf("bucket = %q, want 2026-08-02 (local)", got)
	}
}

// Each turn is priced with the model that actually served it, so a thread that
// switches models is attributed correctly.
func TestPerTurnModelAttribution(t *testing.T) {
	turns := []model.Turn{
		turn("a", "cheap", "/p", local(2026, 8, 1, 10, 0), 1_000_000),
		turn("b", "dear", "/p", local(2026, 8, 1, 11, 0), 1_000_000),
	}
	rep := Build(turns, tbl(), Filter{}, Daily, 0, nil)
	if rep.Totals.Cost != 101 {
		t.Errorf("cost = %v, want 101 (1 + 100, not 2 or 200)", rep.Totals.Cost)
	}
	cheap, _ := find(rep.ByModel, "cheap")
	dear, _ := find(rep.ByModel, "dear")
	if cheap.Cost != 1 || dear.Cost != 100 {
		t.Errorf("per-model = %v/%v, want 1/100", cheap.Cost, dear.Cost)
	}
}

// Model filtering is the capability ccusage does not offer at all.
func TestModelFilter(t *testing.T) {
	turns := []model.Turn{
		turn("a", "cheap", "/p", local(2026, 8, 1, 10, 0), 1_000_000),
		turn("b", "dear", "/p", local(2026, 8, 1, 11, 0), 1_000_000),
	}
	rep := Build(turns, tbl(), Filter{Models: []string{"dear"}}, Daily, 0, nil)
	if rep.MatchedTurns != 1 || rep.Totals.Cost != 100 {
		t.Errorf("matched=%d cost=%v, want 1/100", rep.MatchedTurns, rep.Totals.Cost)
	}
}

// Projects match on a full path or just the folder name, because nobody wants
// to type an absolute path.
func TestProjectFilterMatchesBasename(t *testing.T) {
	turns := []model.Turn{
		turn("a", "cheap", "/home/u/code/alpha", local(2026, 8, 1, 10, 0), 1_000_000),
		turn("b", "cheap", "/home/u/code/beta", local(2026, 8, 1, 11, 0), 2_000_000),
	}
	for _, q := range []string{"alpha", "/home/u/code/alpha"} {
		rep := Build(turns, tbl(), Filter{Projects: []string{q}}, Daily, 0, nil)
		if rep.MatchedTurns != 1 {
			t.Errorf("query %q matched %d turns, want 1", q, rep.MatchedTurns)
		}
	}
}

func TestDateRangeFilterIsInclusive(t *testing.T) {
	turns := []model.Turn{
		turn("a", "cheap", "/p", local(2026, 8, 1, 10, 0), 1),
		turn("b", "cheap", "/p", local(2026, 8, 2, 10, 0), 1),
		turn("c", "cheap", "/p", local(2026, 8, 3, 10, 0), 1),
	}
	rep := Build(turns, tbl(), Filter{From: "2026-08-02", To: "2026-08-03"}, Daily, 0, nil)
	if rep.MatchedTurns != 2 {
		t.Errorf("matched %d turns, want 2 (bounds inclusive)", rep.MatchedTurns)
	}
}

func TestSubagentFilter(t *testing.T) {
	a := turn("a", "cheap", "/p", local(2026, 8, 1, 10, 0), 1_000_000)
	b := turn("b", "cheap", "/p", local(2026, 8, 1, 11, 0), 2_000_000)
	b.Subagent = true
	turns := []model.Turn{a, b}

	for mode, want := range map[string]int{"include": 2, "only": 1, "exclude": 1} {
		rep := Build(turns, tbl(), Filter{Subagents: mode}, Daily, 0, nil)
		if rep.MatchedTurns != want {
			t.Errorf("--subagents %s matched %d, want %d", mode, rep.MatchedTurns, want)
		}
	}
}

// Unpriced usage is excluded from the total and surfaced, never estimated.
func TestUnpricedUsageIsExcludedAndReported(t *testing.T) {
	turns := []model.Turn{
		turn("a", "cheap", "/p", local(2026, 8, 1, 10, 0), 1_000_000),
		turn("b", "mystery-model", "/p", local(2026, 8, 1, 11, 0), 50_000_000),
	}
	rep := Build(turns, tbl(), Filter{}, Daily, 0, nil)
	if rep.Totals.Cost != 1 {
		t.Errorf("cost = %v, want 1 (unpriced usage must not be estimated)", rep.Totals.Cost)
	}
	if rep.Totals.UnpricedTurns != 1 {
		t.Errorf("unpriced turns = %d, want 1", rep.Totals.UnpricedTurns)
	}
	if len(rep.Totals.UnpricedModels) != 1 || rep.Totals.UnpricedModels[0] != "mystery-model" {
		t.Errorf("unpriced models = %v, want [mystery-model]", rep.Totals.UnpricedModels)
	}
}

func TestMonthlyAndWeeklyBuckets(t *testing.T) {
	turns := []model.Turn{
		turn("a", "cheap", "/p", local(2026, 8, 3, 10, 0), 1), // Monday
		turn("b", "cheap", "/p", local(2026, 8, 6, 10, 0), 1), // Thursday, same week
		turn("c", "cheap", "/p", local(2026, 9, 1, 10, 0), 1),
	}
	monthly := Build(turns, tbl(), Filter{}, Monthly, 0, nil)
	if len(monthly.Series) != 2 {
		t.Errorf("monthly buckets = %d, want 2", len(monthly.Series))
	}
	weekly := Build(turns, tbl(), Filter{}, Weekly, 0, nil)
	if _, ok := find(weekly.Series, "2026-08-03"); !ok {
		t.Errorf("weekly buckets %v missing the Monday anchor 2026-08-03", weekly.Series)
	}
}

// End-to-end proof that an effective-dated rate change is actually applied
// during aggregation: identical usage on either side of the change date must
// produce different cost.
func TestRateChangeAppliesAcrossTheBoundary(t *testing.T) {
	table := tbl()
	table.Models["swings"] = &pricing.Model{ID: "swings", Rates: []pricing.Rate{
		{From: pricing.MustParseDate("2026-01-01"), Out: 100},
		{From: pricing.MustParseDate("2026-08-15"), Out: 20}, // 80% cut
	}}

	turns := []model.Turn{
		turn("a", "swings", "/p", local(2026, 8, 14, 12, 0), 1_000_000), // before
		turn("b", "swings", "/p", local(2026, 8, 15, 12, 0), 1_000_000), // on the day
		turn("c", "swings", "/p", local(2026, 8, 20, 12, 0), 1_000_000), // after
	}
	rep := Build(turns, table, Filter{}, Daily, 0, nil)

	want := map[string]float64{"2026-08-14": 100, "2026-08-15": 20, "2026-08-20": 20}
	for day, expect := range want {
		b, ok := find(rep.Series, day)
		if !ok {
			t.Fatalf("missing bucket %s", day)
		}
		if b.Cost != expect {
			t.Errorf("%s cost = %v, want %v (rate in force that day)", day, b.Cost, expect)
		}
	}
	if rep.Totals.Cost != 140 {
		t.Errorf("total = %v, want 140 (100 + 20 + 20, not 3x either rate)", rep.Totals.Cost)
	}
}

// Nested grouping produces the dimensions asked for, in order.
func TestGroupByNestsDimensions(t *testing.T) {
	a := turn("a", "cheap", "/p", local(2026, 8, 1, 10, 0), 1_000_000)
	a.Agent = model.AgentClaude
	b := turn("b", "dear", "/p", local(2026, 8, 1, 11, 0), 1_000_000)
	b.Agent = model.AgentCodex

	rep := Build([]model.Turn{a, b}, tbl(), Filter{}, Daily, 0,
		[]Dimension{DimAgent, DimModel})

	day, ok := find(rep.Series, "2026-08-01")
	if !ok || len(day.Breakdown) != 2 {
		t.Fatalf("day breakdown = %+v, want two agents", day.Breakdown)
	}
	for _, agentBucket := range day.Breakdown {
		if len(agentBucket.Breakdown) != 1 {
			t.Errorf("agent %s has %d model rows, want 1", agentBucket.Key, len(agentBucket.Breakdown))
		}
	}
}

func TestParseDimensionsRejectsTypos(t *testing.T) {
	if _, err := ParseDimensions("agent,modle"); err == nil {
		t.Error("a misspelt dimension was accepted")
	}
	dims, err := ParseDimensions(" agent , model ")
	if err != nil || len(dims) != 2 || dims[0] != DimAgent || dims[1] != DimModel {
		t.Errorf("ParseDimensions = %v, %v", dims, err)
	}
}

// "none" is how the flat table stays reachable now that grouping is the default.
func TestParseDimensionsNoneMeansFlat(t *testing.T) {
	for _, spec := range []string{"none", "flat", "None"} {
		dims, err := ParseDimensions(spec)
		if err != nil || len(dims) != 0 {
			t.Errorf("ParseDimensions(%q) = %v, %v; want no dimensions", spec, dims, err)
		}
	}
}
