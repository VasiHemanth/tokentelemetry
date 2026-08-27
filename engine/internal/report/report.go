// Package report aggregates priced turns into the views the CLI and API serve.
//
// Aggregation runs over turns, so every dimension is exact: a turn contributes
// to the day it actually happened on and the model that actually served it. The
// session-level implementation this replaces could do neither — 25% of Codex
// cost sat in sessions spanning more than one local day and was charged
// entirely to the last day.
//
// Filtering by model, project and agent is the capability ccusage does not
// offer at all; its daily/monthly commands accept only --since/--until.
package report

import (
	"sort"
	"strings"
	"time"

	"github.com/VasiHemanth/tokentelemetry/engine/internal/cost"
	"github.com/VasiHemanth/tokentelemetry/engine/internal/model"
	"github.com/VasiHemanth/tokentelemetry/engine/internal/pricing"
)

// Granularity is the bucket width for time series.
type Granularity string

const (
	Daily   Granularity = "day"
	Weekly  Granularity = "week"
	Monthly Granularity = "month"
)

// Filter narrows the working set. Empty fields mean "no filter".
//
// From/To are inclusive LOCAL calendar days. Local, not UTC: a user in IST
// asking for "today" means their today, and formatting a local midnight through
// UTC rolls it back a day — the bug that put the old activity heatmap off by
// one.
type Filter struct {
	From     string
	To       string
	Agents   []string
	Models   []string
	Projects []string
	// Subagents controls delegated turns: "include" (default), "only", "exclude".
	Subagents string
}

func (f Filter) match(t model.Turn, resolvedModel string) bool {
	if len(f.Agents) > 0 && !containsFold(f.Agents, string(t.Agent)) {
		return false
	}
	// Model matching accepts either the id the agent recorded or the normalised
	// id it resolved to, so `--model claude-opus-5` catches a turn logged as
	// `anthropic/claude-opus-5`.
	if len(f.Models) > 0 && !containsFold(f.Models, t.Model) && !containsFold(f.Models, resolvedModel) {
		return false
	}
	if len(f.Projects) > 0 && !matchProject(f.Projects, t.Project) {
		return false
	}
	switch f.Subagents {
	case "only":
		if !t.Subagent {
			return false
		}
	case "exclude":
		if t.Subagent {
			return false
		}
	}
	if f.From != "" && dayKey(t.Timestamp) < f.From {
		return false
	}
	if f.To != "" && dayKey(t.Timestamp) > f.To {
		return false
	}
	return true
}

// Totals is the headline summary.
type Totals struct {
	Usage    model.Usage `json:"usage"`
	Cost     float64     `json:"cost"`
	Turns    int         `json:"turns"`
	Sessions int         `json:"sessions"`

	// UnpricedTurns counts calls we hold no rate for. Their cost is excluded
	// from Cost entirely rather than being invented — the old $2/$10 fallback
	// billed 965 sessions of a free model at $380.
	UnpricedTurns  int      `json:"unpriced_turns"`
	UnpricedModels []string `json:"unpriced_models,omitempty"`

	// StaleRatedTurns counts calls priced with a rate that took effect after
	// the call happened.
	StaleRatedTurns int     `json:"stale_rated_turns"`
	StaleRatedCost  float64 `json:"stale_rated_cost"`

	// CostByBilling splits the total by how it was actually paid for. The cost
	// figure is always API list price; this says which parts of it a flat
	// subscription already covered.
	CostByBilling map[string]float64 `json:"cost_by_billing,omitempty"`
}

// Bucket is one row of an aggregate.
type Bucket struct {
	Key      string      `json:"key"`
	Usage    model.Usage `json:"usage"`
	Cost     float64     `json:"cost"`
	Turns    int         `json:"turns"`
	Sessions int         `json:"sessions"`
	Unpriced int         `json:"unpriced,omitempty"`
	// Models lists the distinct models in this bucket, busiest first.
	Models []string `json:"models,omitempty"`
	// Breakdown splits the bucket by model, most expensive first. Populated for
	// every bucket; the CLI shows it under --breakdown, and JSON consumers get
	// it unconditionally so a caller never has to re-run with a different
	// grouping to answer "which model drove this day".
	Breakdown []Bucket `json:"breakdown,omitempty"`
}

// Report is the full aggregate.
type Report struct {
	Totals    Totals   `json:"totals"`
	Series    []Bucket `json:"series,omitempty"`
	ByAgent   []Bucket `json:"by_agent,omitempty"`
	ByModel   []Bucket `json:"by_model,omitempty"`
	ByProject []Bucket `json:"by_project,omitempty"`
	Sessions  []Bucket `json:"sessions,omitempty"`

	// WindowFrom/WindowTo bound the matched turns as local day keys, used to
	// prorate flat-rate subscriptions over exactly the period on screen.
	WindowFrom string `json:"window_from,omitempty"`
	WindowTo   string `json:"window_to,omitempty"`

	// GroupBy records the nested dimensions applied beneath each row.
	GroupBy []Dimension `json:"group_by,omitempty"`

	Granularity  Granularity  `json:"granularity"`
	PricingDate  pricing.Date `json:"pricing_updated"`
	Duplicates   int          `json:"duplicates_dropped"`
	MatchedTurns int          `json:"matched_turns"`
	ScannedTurns int          `json:"scanned_turns"`
}

type acc struct {
	usage    model.Usage
	cost     float64
	turns    int
	unpriced int
	sessions map[string]struct{}
	models   map[string]int64
	// sub holds this bucket's split by the next grouping dimension, and dims
	// holds the dimensions still to apply beneath it. An empty dims stops the
	// recursion, so the nesting depth is exactly what the caller asked for.
	sub  map[string]*acc
	dims []Dimension
}

func newAcc(dims []Dimension) *acc {
	a := &acc{sessions: map[string]struct{}{}, models: map[string]int64{}, dims: dims}
	if len(dims) > 0 {
		a.sub = map[string]*acc{}
	}
	return a
}

func (a *acc) add(t model.Turn, c cost.Cost) {
	a.usage.Add(t.Usage)
	a.turns++
	if c.Priced() {
		a.cost += c.USD
	} else {
		a.unpriced++
	}
	if t.SessionID != "" {
		a.sessions[t.SessionID] = struct{}{}
	}
	name := c.Model
	if name == "" {
		name = t.Model
	}
	if name != "" {
		a.models[name] += t.Usage.Total()
	}
	if len(a.dims) > 0 {
		key := a.dims[0].keyOf(t, c, Daily)
		if key == "" {
			key = "(unknown)"
		}
		s, ok := a.sub[key]
		if !ok {
			s = newAcc(a.dims[1:])
			a.sub[key] = s
		}
		s.add(t, c)
	}
}

func (a *acc) bucket(key string) Bucket {
	models := make([]string, 0, len(a.models))
	for m := range a.models {
		models = append(models, m)
	}
	sort.Slice(models, func(i, j int) bool {
		if a.models[models[i]] != a.models[models[j]] {
			return a.models[models[i]] > a.models[models[j]]
		}
		return models[i] < models[j]
	})
	b := Bucket{
		Key: key, Usage: a.usage, Cost: a.cost, Turns: a.turns,
		Sessions: len(a.sessions), Unpriced: a.unpriced, Models: models,
	}
	for k, s := range a.sub {
		b.Breakdown = append(b.Breakdown, s.bucket(k))
	}
	sort.Slice(b.Breakdown, func(i, j int) bool {
		if b.Breakdown[i].Cost != b.Breakdown[j].Cost {
			return b.Breakdown[i].Cost > b.Breakdown[j].Cost
		}
		return b.Breakdown[i].Key < b.Breakdown[j].Key
	})
	return b
}

// Build aggregates turns into a report.
//
// groupBy nests additional dimensions inside the command's own top-level
// grouping, so `daily --group-by agent,model` yields day → agent → model.
func Build(turns []model.Turn, tbl *pricing.Table, f Filter, g Granularity, duplicates int, groupBy []Dimension) *Report {
	if g == "" {
		g = Daily
	}
	rep := &Report{
		Granularity: g, PricingDate: tbl.Updated, Duplicates: duplicates,
		ScannedTurns: len(turns), GroupBy: groupBy,
	}

	series := map[string]*acc{}
	byAgent := map[string]*acc{}
	byModel := map[string]*acc{}
	byProject := map[string]*acc{}
	bySession := map[string]*acc{}
	unpricedModels := map[string]struct{}{}
	totals := newAcc(nil)
	billing := map[string]float64{}

	for _, t := range turns {
		c := cost.Of(t, tbl)
		if !f.match(t, c.Model) {
			continue
		}
		rep.MatchedTurns++
		if d := dayKey(t.Timestamp); d != "" {
			if rep.WindowFrom == "" || d < rep.WindowFrom {
				rep.WindowFrom = d
			}
			if d > rep.WindowTo {
				rep.WindowTo = d
			}
		}

		totals.add(t, c)
		if !c.Priced() {
			name := t.Model
			if name == "" {
				name = "(unknown)"
			}
			unpricedModels[name] = struct{}{}
		} else {
			billing[c.Billing.String()] += c.USD
			if c.RateNewerThanCall {
				rep.Totals.StaleRatedTurns++
				rep.Totals.StaleRatedCost += c.USD
			}
		}

		addTo(series, bucketKey(t.Timestamp, g), t, c, groupBy)
		addTo(byAgent, string(t.Agent), t, c, groupBy)
		addTo(byModel, displayModel(t, c), t, c, groupBy)
		addTo(byProject, displayProject(t.Project), t, c, groupBy)
		if t.SessionID != "" {
			addTo(bySession, string(t.Agent)+":"+t.SessionID, t, c, groupBy)
		}
	}

	rep.Totals.Usage = totals.usage
	rep.Totals.Cost = totals.cost
	rep.Totals.Turns = totals.turns
	rep.Totals.Sessions = len(totals.sessions)
	rep.Totals.UnpricedTurns = totals.unpriced
	rep.Totals.CostByBilling = billing
	for m := range unpricedModels {
		rep.Totals.UnpricedModels = append(rep.Totals.UnpricedModels, m)
	}
	sort.Strings(rep.Totals.UnpricedModels)

	rep.Series = sortedByKey(series)
	rep.ByAgent = sortedByCost(byAgent)
	rep.ByModel = sortedByCost(byModel)
	rep.ByProject = sortedByCost(byProject)
	rep.Sessions = sortedByCost(bySession)
	return rep
}

func addTo(m map[string]*acc, key string, t model.Turn, c cost.Cost, dims []Dimension) {
	if key == "" {
		return
	}
	a, ok := m[key]
	if !ok {
		a = newAcc(dims)
		m[key] = a
	}
	a.add(t, c)
}

func sortedByKey(m map[string]*acc) []Bucket {
	out := make([]Bucket, 0, len(m))
	for k, a := range m {
		out = append(out, a.bucket(k))
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Key < out[j].Key })
	return out
}

func sortedByCost(m map[string]*acc) []Bucket {
	out := make([]Bucket, 0, len(m))
	for k, a := range m {
		out = append(out, a.bucket(k))
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].Cost != out[j].Cost {
			return out[i].Cost > out[j].Cost
		}
		if out[i].Usage.Total() != out[j].Usage.Total() {
			return out[i].Usage.Total() > out[j].Usage.Total()
		}
		return out[i].Key < out[j].Key
	})
	return out
}

func displayModel(t model.Turn, c cost.Cost) string {
	if c.Model != "" {
		return c.Model
	}
	if t.Model != "" {
		return t.Model
	}
	return string(t.Agent) + " (unknown model)"
}

func displayProject(p string) string {
	if p == "" {
		return "(unknown)"
	}
	return p
}

// bucketKey renders a turn's LOCAL day/week/month key.
func bucketKey(ts time.Time, g Granularity) string {
	if ts.IsZero() {
		return "(undated)"
	}
	local := ts.Local()
	switch g {
	case Monthly:
		return local.Format("2006-01")
	case Weekly:
		// ISO week, anchored to the Monday, so a week key is also a real date.
		wd := (int(local.Weekday()) + 6) % 7
		return local.AddDate(0, 0, -wd).Format("2006-01-02")
	default:
		return local.Format("2006-01-02")
	}
}

func dayKey(ts time.Time) string {
	if ts.IsZero() {
		return ""
	}
	return ts.Local().Format("2006-01-02")
}

func containsFold(list []string, v string) bool {
	for _, x := range list {
		if strings.EqualFold(x, v) {
			return true
		}
	}
	return false
}

// matchProject accepts an exact path or a trailing path segment, so
// `--project tokentelemetry` matches /home/user/code/tokentelemetry.
func matchProject(list []string, p string) bool {
	if p == "" {
		return false
	}
	base := p
	if i := strings.LastIndexAny(p, `/\`); i >= 0 {
		base = p[i+1:]
	}
	for _, x := range list {
		if strings.EqualFold(x, p) || strings.EqualFold(x, base) {
			return true
		}
	}
	return false
}
