// Package plans records what the user actually pays for flat-rate
// subscriptions, so a report can show real spend next to API list value.
//
// Everything else in this tool prices usage at API list rates, which is the
// right unit for comparing agents and models. But it answers the wrong
// question on its own: a report reading "$8,511.69, all covered by a flat plan"
// never says the plan costs $120 a month. Both numbers matter, and the ratio
// between them is arguably the most useful figure the tool can produce.
//
// Config lives at ~/.tokentelemetry/plans.json:
//
//	{
//	  "subscriptions": [
//	    {"agent": "codex",  "name": "ChatGPT Pro", "monthly_usd": 100},
//	    {"agent": "claude", "name": "Claude Pro",  "monthly_usd": 20, "from": "2026-03-01"}
//	  ]
//	}
//
// Absent config means no real-spend line is shown — never a guess.
package plans

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// Subscription is one flat-rate plan.
type Subscription struct {
	Agent      string  `json:"agent"`
	Name       string  `json:"name"`
	MonthlyUSD float64 `json:"monthly_usd"`
	// From and Until bound the period the plan was held, so a report over a
	// window that predates the subscription does not charge for it. Both are
	// optional YYYY-MM-DD.
	From  string `json:"from,omitempty"`
	Until string `json:"until,omitempty"`
}

// Config is the whole plans file.
type Config struct {
	Subscriptions []Subscription `json:"subscriptions"`
}

// Charge is one subscription's prorated cost over a window.
type Charge struct {
	Agent string
	Name  string
	USD   float64
	Days  int
}

// Load reads the plans file. A missing or malformed file yields an empty
// config, because a real-spend line is a bonus and must never break a report.
func Load() Config {
	path := os.Getenv("TT_PLANS_FILE")
	if path == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return Config{}
		}
		path = filepath.Join(home, ".tokentelemetry", "plans.json")
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return Config{}
	}
	var c Config
	if err := json.Unmarshal(raw, &c); err != nil {
		return Config{}
	}
	// Drop entries that carry no usable figure rather than treating them as free.
	out := c.Subscriptions[:0]
	for _, s := range c.Subscriptions {
		if s.MonthlyUSD > 0 && s.Agent != "" {
			out = append(out, s)
		}
	}
	c.Subscriptions = out
	return c
}

// Empty reports whether any subscription is configured.
func (c Config) Empty() bool { return len(c.Subscriptions) == 0 }

// ChargesFor prorates every applicable subscription across [from, to].
//
// Proration is per calendar day, dividing each month's fee by that month's own
// length rather than an average. A subscription is charged for days the user
// held it whether or not they ran anything — that is what a flat plan means, and
// dividing by "days with usage" would flatter a quiet month.
//
// agents, when non-empty, restricts to those agents, so `--agent claude` does
// not bill a ChatGPT plan against a Claude-only report.
func (c Config) ChargesFor(from, to time.Time, agents []string) []Charge {
	if c.Empty() || from.IsZero() || to.IsZero() || to.Before(from) {
		return nil
	}
	var out []Charge
	for _, s := range c.Subscriptions {
		if len(agents) > 0 && !containsFold(agents, s.Agent) {
			continue
		}
		start, end := from, to
		if s.From != "" {
			if d, err := time.ParseInLocation("2006-01-02", s.From, time.Local); err == nil && d.After(start) {
				start = d
			}
		}
		if s.Until != "" {
			if d, err := time.ParseInLocation("2006-01-02", s.Until, time.Local); err == nil && d.Before(end) {
				end = d
			}
		}
		if end.Before(start) {
			continue
		}
		usd, days := prorate(s.MonthlyUSD, start, end)
		if usd <= 0 {
			continue
		}
		name := s.Name
		if name == "" {
			name = s.Agent
		}
		out = append(out, Charge{Agent: s.Agent, Name: name, USD: usd, Days: days})
	}
	return out
}

// prorate sums a monthly fee across the calendar days in [from, to] inclusive.
func prorate(monthly float64, from, to time.Time) (float64, int) {
	d := time.Date(from.Year(), from.Month(), from.Day(), 0, 0, 0, 0, time.Local)
	last := time.Date(to.Year(), to.Month(), to.Day(), 0, 0, 0, 0, time.Local)
	var total float64
	var days int
	for !d.After(last) {
		total += monthly / float64(daysInMonth(d))
		days++
		d = d.AddDate(0, 0, 1)
	}
	return total, days
}

// daysInMonth returns the length of t's month.
func daysInMonth(t time.Time) int {
	first := time.Date(t.Year(), t.Month(), 1, 0, 0, 0, 0, time.Local)
	return int(first.AddDate(0, 1, 0).Sub(first).Hours() / 24)
}

// Total sums charges.
func Total(charges []Charge) float64 {
	var v float64
	for _, c := range charges {
		v += c.USD
	}
	return v
}

func containsFold(list []string, v string) bool {
	for _, x := range list {
		if strings.EqualFold(x, v) {
			return true
		}
	}
	return false
}
