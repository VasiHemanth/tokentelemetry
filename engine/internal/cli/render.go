package cli

import (
	"fmt"
	"io"
	"path/filepath"
	"strings"
	"time"

	"github.com/VasiHemanth/tokentelemetry/engine/internal/model"
	"github.com/VasiHemanth/tokentelemetry/engine/internal/plans"
	"github.com/VasiHemanth/tokentelemetry/engine/internal/report"
)

// planCharges prorates the configured subscriptions over the window actually on
// screen. Returns nothing when no plans file exists — a real-spend line is only
// ever shown from a figure the user supplied, never inferred.
func planCharges(rep *report.Report, agents []string) []plans.Charge {
	cfg := plans.Load()
	if cfg.Empty() || rep.WindowFrom == "" {
		return nil
	}
	from, err1 := time.ParseInLocation("2006-01-02", rep.WindowFrom, time.Local)
	to, err2 := time.ParseInLocation("2006-01-02", rep.WindowTo, time.Local)
	if err1 != nil || err2 != nil {
		return nil
	}
	return cfg.ChargesFor(from, to, agents)
}

// chargeNote names the plans and the period they were prorated over.
func chargeNote(charges []plans.Charge) string {
	parts := make([]string, 0, len(charges))
	days := 0
	for _, c := range charges {
		parts = append(parts, fmt.Sprintf("%s %s", c.Name, money(c.USD)))
		if c.Days > days {
			days = c.Days
		}
	}
	return strings.Join(parts, " + ") + " · " + plural(days, "day")
}

func render(w io.Writer, cmd string, rep *report.Report, limit int, color, verbose, compact bool, agents []string) {
	th := theme{on: color}
	// Full counts with separators by default. They are what every other usage
	// tool prints, and an exact figure is what someone reconciling against a
	// bill actually needs; --compact trades that for a narrower table.
	fmtNum := func(n int64) string { return group(fmt.Sprintf("%d", n)) }
	if compact {
		fmtNum = tokens
	}

	rows := rep.Series
	label, colMax, truncLeft := "DATE", 0, false
	switch cmd {
	case "session":
		rows, label, colMax = rep.Sessions, "SESSION", 26
	case "model":
		rows, label, colMax = rep.ByModel, "MODEL", 32
	case "project":
		rows, label, colMax, truncLeft = rep.ByProject, "PROJECT", 34, true
	}
	if len(rows) == 0 {
		io.WriteString(w, "\n  "+th.dim("No usage matched those filters.")+"\n\n")
		return
	}

	truncated := 0
	if limit > 0 && len(rows) > limit {
		truncated = len(rows) - limit
		rows = rows[:limit]
	}

	section(w, th, title(cmd, rep))

	// One column per grouping level, rather than indentation alone: with the
	// level in its own column the eye can scan a single agent down the page,
	// which is not possible when the only cue is how far a label is inset.
	cols := []column{{title: label, align: alignLeft, max: colMax, truncLeft: truncLeft}}
	for _, d := range rep.GroupBy {
		cols = append(cols, column{title: d.Title(), align: alignLeft, max: 28})
	}
	// Which models produced a row is the first thing anyone asks of a usage
	// table, so it is shown by default rather than hidden behind a flag. It is
	// dropped only where it would duplicate a column already present: when
	// models are themselves a grouping level, or when the rows ARE models.
	showModels := !hasDim(rep.GroupBy, report.DimModel) && cmd != "model"
	if showModels {
		cols = append(cols, column{title: "MODELS", align: alignLeft, max: 30})
	}
	cols = append(cols,
		column{title: "INPUT", align: alignRight},
		column{title: "OUTPUT", align: alignRight},
		column{title: "CACHE W", align: alignRight},
		column{title: "CACHE R", align: alignRight},
		column{title: "TOTAL", align: alignRight},
		column{title: "COST", align: alignRight},
	)
	t := newTable(th, cols...)

	nDims := len(rep.GroupBy)
	for i, r := range rows {
		// Blank line between groups, but only when a group spans several lines;
		// separating single-line rows would just double the report's length.
		spaced := i > 0 && nDims > 0 && len(r.Breakdown) > 0
		emitGroup(t, th, r, rowLabel(cmd, r.Key), 0, nDims, showModels, fmtNum, spaced)
	}
	// A closing total, so a truncated or filtered view still shows what the rows
	// on screen add up to.
	if len(rows) > 1 {
		var tot report.Bucket
		for _, r := range rows {
			tot.Usage.Add(r.Usage)
			tot.Cost += r.Cost
		}
		cells := []cell{styled("Total", th.strong)}
		for i := 0; i < nDims; i++ {
			cells = append(cells, plain(""))
		}
		if showModels {
			cells = append(cells, plain(""))
		}
		cells = append(cells, numbers(th, tot.Usage, tot.Cost, fmtNum, th.strong)...)
		t.addRuled(cells...)
	}
	t.render(w)

	summary(w, th, rep, truncated, verbose, agents)
}

// emitGroup writes one bucket and, recursively, its nested breakdown. depth is
// which grouping column this bucket's key belongs in.
func emitGroup(t *table, th theme, b report.Bucket, topLabel string, depth, nDims int, showModels bool, fmtNum func(int64) string, spaced bool) {
	cells := make([]cell, 0, nDims+8)

	// Leading label column: only the top-level row carries it.
	if depth == 0 {
		// The group's own row is its heading, so it carries the emphasis and the
		// detail rows beneath stay quiet.
		cells = append(cells, styled(topLabel, th.strong))
	} else {
		cells = append(cells, plain(""))
	}
	for i := 0; i < nDims; i++ {
		switch {
		case depth == 0 && i == 0:
			// The top row summarises every group beneath it.
			cells = append(cells, styled("All", th.dim))
		case i == depth-1:
			cells = append(cells, styled("- "+b.Key, th.label))
		default:
			cells = append(cells, plain(""))
		}
	}
	if showModels {
		// Models are listed in-cell on the deepest row, where they describe
		// exactly the usage on that line.
		if depth == nDims && len(b.Models) > 0 {
			lines := make([]string, 0, len(b.Models))
			for _, m := range b.Models {
				lines = append(lines, "- "+m)
			}
			cells = append(cells, multi(lines, th.dim))
		} else {
			cells = append(cells, plain(""))
		}
	}
	costStyle := th.money
	if depth == 0 {
		costStyle = func(s string) string { return th.strong(th.money(s)) }
	}
	cells = append(cells, numbers(th, b.Usage, b.Cost, fmtNum, costStyle)...)
	if spaced {
		t.addGroup(cells...)
	} else {
		t.add(cells...)
	}

	for _, sub := range b.Breakdown {
		emitGroup(t, th, sub, "", depth+1, nDims, showModels, fmtNum, false)
	}
}

// numbers renders the six figure columns.
func numbers(th theme, u model.Usage, cost float64, fmtNum func(int64) string, costStyle func(string) string) []cell {
	return []cell{
		num(th, u.Input, fmtNum), num(th, u.Output, fmtNum),
		num(th, u.CacheWrite, fmtNum), num(th, u.CacheRead, fmtNum),
		num(th, u.Total(), fmtNum),
		styled(money(cost), costStyle),
	}
}

// plural renders a count with a correctly inflected noun.
func plural(n int, noun string) string {
	if n == 1 {
		return fmt.Sprintf("%d %s", n, noun)
	}
	return fmt.Sprintf("%d %ss", n, noun)
}

func hasDim(dims []report.Dimension, want report.Dimension) bool {
	for _, d := range dims {
		if d == want {
			return true
		}
	}
	return false
}

func title(cmd string, rep *report.Report) string {
	switch cmd {
	case "session":
		return "Usage by session"
	case "model":
		return "Usage by model"
	case "project":
		return "Usage by project"
	case "weekly":
		return "Usage by week"
	case "monthly":
		return "Usage by month"
	default:
		return "Usage by day"
	}
}

// num renders a token count, dimming zeros so the eye skips them.
func num(th theme, n int64, fmtNum func(int64) string) cell {
	if n == 0 {
		return styled("—", th.dim)
	}
	return plain(fmtNum(n))
}

func summary(w io.Writer, th theme, rep *report.Report, truncated int, verbose bool, agents []string) {
	t := rep.Totals

	section(w, th, "Summary")
	rows := []fieldRow{
		{label: "Total cost", value: th.strong(th.money(money(t.Cost))), note: "at API list rates"},
		{label: "Turns", value: humanInt(t.Turns), note: fmt.Sprintf("across %s sessions", humanInt(t.Sessions))},
		{label: "Tokens", value: tokens(t.Usage.Total()), note: tokenMix(t)},
	}
	// How the list price was actually paid for. The figure never changes; this
	// says which part of it a flat subscription already covered.
	for _, k := range []string{"api", "subscription", "local"} {
		if v, ok := t.CostByBilling[k]; ok && v > 0 {
			rows = append(rows, fieldRow{
				label: billingLabel(k), value: th.money(money(v)), note: billingNote(k), sub: true,
			})
		}
	}
	// What the user actually pays. List price is the comparable unit, but it is
	// not a bill; when the plans file says what the flat subscriptions cost,
	// show that and the ratio between them.
	if charges := planCharges(rep, agents); len(charges) > 0 {
		paid := plans.Total(charges)
		rows = append(rows,
			fieldRow{label: "You actually paid", value: th.strong(th.money(money(paid))), note: chargeNote(charges)})
		if paid > 0 && t.Cost > 0 {
			rows = append(rows, fieldRow{
				label: "Leverage", value: fmt.Sprintf("%.0fx", t.Cost/paid),
				note: "list value per dollar paid", sub: true,
			})
		}
	}

	fields(w, th, rows)

	// Caveats sit directly under the figures they qualify rather than in their
	// own section: a heading plus its blank lines cost more screen than the one
	// or two short lines it introduces.
	blank := false
	note := func(marker func(string) string, glyph, text string) {
		if !blank {
			io.WriteString(w, "\n")
			blank = true
		}
		io.WriteString(w, "    "+marker(glyph)+"  "+text+"\n")
	}

	// A warning means money is missing from the total and cannot be inferred
	// from anything else on screen. Nothing else earns a `!`.
	if t.UnpricedTurns > 0 {
		note(th.warn, "!", fmt.Sprintf("%s turns unpriced and excluded — %s",
			humanInt(t.UnpricedTurns), strings.Join(truncateList(t.UnpricedModels, 3), ", ")))
	}
	if truncated > 0 {
		note(th.dim, "·", th.dim(fmt.Sprintf("%s more rows — raise --limit", humanInt(truncated))))
	}
	note(th.dim, "·", th.dim(ratesLine(rep)))

	// Diagnostics: true, but never actionable. They belong behind a flag rather
	// than in front of someone checking what they spent.
	if verbose {
		if rep.Duplicates > 0 {
			note(th.dim, "·", th.dim(fmt.Sprintf("%s replayed calls dropped as duplicates", humanInt(rep.Duplicates))))
		}
		note(th.dim, "·", th.dim(fmt.Sprintf("%s turns scanned, %s matched the filters",
			humanInt(rep.ScannedTurns), humanInt(rep.MatchedTurns))))
	}
	io.WriteString(w, "\n")
}

// ratesLine dates the prices and, when it matters, says how much of the total
// was priced with a rate we only learned after the fact.
//
// Deliberately one dim clause rather than a warning: for a backlog older than
// the price history this covers nearly everything, and a `!` that fires on
// every run is one nobody reads.
func ratesLine(rep *report.Report) string {
	line := "rates " + rep.PricingDate.String()
	if rep.Totals.Cost > 0 && rep.Totals.StaleRatedCost > 0 {
		pct := rep.Totals.StaleRatedCost / rep.Totals.Cost * 100
		if pct >= 1 {
			line += fmt.Sprintf(" · %.0f%% of cost predates our price history", pct)
		}
	}
	return line
}

func billingLabel(k string) string {
	switch k {
	case "subscription":
		return "of which subscription"
	case "local":
		return "of which local"
	default:
		return "of which metered API"
	}
}

func billingNote(k string) string {
	switch k {
	case "subscription":
		return "covered by a flat plan — not a bill"
	case "local":
		return "ran on your hardware — cloud equivalent"
	default:
		return "approximates your actual bill"
	}
}

// tokenMix summarises where the tokens went, since cache reads dominate agent
// workloads and that is not obvious from a single total.
func tokenMix(t report.Totals) string {
	total := t.Usage.Total()
	if total == 0 {
		return ""
	}
	pct := func(n int64) string {
		p := float64(n) / float64(total) * 100
		if p > 0 && p < 1 {
			return "<1%"
		}
		return fmt.Sprintf("%.0f%%", p)
	}
	return fmt.Sprintf("cache read %s · input %s · output %s",
		pct(t.Usage.CacheRead), pct(t.Usage.Input), pct(t.Usage.Output))
}

// rowLabel shortens keys that would otherwise dominate the table.
func rowLabel(cmd, key string) string {
	switch cmd {
	case "session":
		// "agent:uuid" -> "agent  uuid-prefix"
		if i := strings.IndexByte(key, ':'); i > 0 {
			agent, id := key[:i], key[i+1:]
			if len(id) > 8 {
				id = id[:8]
			}
			return fmt.Sprintf("%-9s %s", agent, id)
		}
	case "project":
		if key == "(unknown)" {
			return key
		}
		return filepath.Base(key)
	}
	return key
}

func truncateList(items []string, n int) []string {
	if len(items) <= n {
		return items
	}
	out := append([]string{}, items[:n]...)
	return append(out, fmt.Sprintf("and %d more", len(items)-n))
}

// tokens renders a count compactly with a fixed one-decimal form, so the
// figures in a column share a decimal position and can be compared by eye.
func tokens(n int64) string {
	switch {
	case n >= 1_000_000_000:
		return fmt.Sprintf("%.2fB", float64(n)/1e9)
	case n >= 1_000_000:
		return fmt.Sprintf("%.1fM", float64(n)/1e6)
	case n >= 1_000:
		return fmt.Sprintf("%.1fK", float64(n)/1e3)
	default:
		return fmt.Sprintf("%d", n)
	}
}

// money renders USD with enough precision to stay useful at both ends of the
// range: sub-cent calls still show a figure, four-digit totals stay readable.
func money(v float64) string {
	switch {
	case v == 0:
		return "$0.00"
	case v < 0.01:
		return fmt.Sprintf("$%.4f", v)
	case v < 1000:
		return fmt.Sprintf("$%.2f", v)
	default:
		return "$" + humanFloat(v)
	}
}

func humanFloat(v float64) string {
	s := fmt.Sprintf("%.2f", v)
	dot := strings.IndexByte(s, '.')
	return group(s[:dot]) + s[dot:]
}

func humanInt(n int) string { return group(fmt.Sprintf("%d", n)) }

// group inserts thousands separators.
func group(s string) string {
	neg := strings.HasPrefix(s, "-")
	if neg {
		s = s[1:]
	}
	var b strings.Builder
	for i, c := range s {
		if i > 0 && (len(s)-i)%3 == 0 {
			b.WriteByte(',')
		}
		b.WriteRune(c)
	}
	if neg {
		return "-" + b.String()
	}
	return b.String()
}
