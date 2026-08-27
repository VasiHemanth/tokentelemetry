package cli

import (
	"fmt"
	"io"
	"math"
	"os"
	"strconv"
	"strings"

	"github.com/VasiHemanth/tokentelemetry/engine/internal/pricing"
)

func cmdPrice(args []string) int {
	var models []string
	color := true
	for _, a := range args {
		switch a {
		case "--no-color":
			color = false
		default:
			if !strings.HasPrefix(a, "-") {
				models = append(models, a)
			}
		}
	}
	if len(models) == 0 {
		fmt.Fprintln(os.Stderr, "tokentelemetry: price needs a model id, e.g. `tokentelemetry price gpt-5.6-luna`")
		return 2
	}
	tbl, err := pricing.Load()
	if err != nil {
		fmt.Fprintf(os.Stderr, "tokentelemetry: %v\n", err)
		return 1
	}
	th := theme{on: colorEnabled(!color)}

	code := 0
	for _, q := range models {
		if !renderPrice(os.Stdout, th, tbl, q) {
			code = 1
		}
	}
	io.WriteString(os.Stdout, "\n")
	return code
}

// renderPrice shows a model's full rate history, newest last, so a price change
// reads as an event with a date rather than a single number of unknown vintage.
func renderPrice(w io.Writer, th theme, tbl *pricing.Table, query string) bool {
	m, resolved, ok := tbl.Find(query)
	if !ok {
		section(w, th, query)
		io.WriteString(w, "    "+th.warn("!")+"  no rate on file\n")
		io.WriteString(w, "    "+th.dim("·")+"  "+th.dim("usage of this model is reported as unpriced, never estimated")+"\n")
		return false
	}

	heading := m.ID
	if resolved != m.ID {
		heading = fmt.Sprintf("%s  →  %s", query, m.ID)
	}
	section(w, th, heading)

	src := ""
	if len(m.Rates) > 0 {
		src = m.Rates[len(m.Rates)-1].Source
	}
	origin := "reseller"
	if m.FirstParty {
		origin = "first-party"
	}
	if src != "" {
		io.WriteString(w, "    "+th.dim(fmt.Sprintf("priced from %s · %s", src, origin))+"\n\n")
	}

	// Decide each column's decimal precision from the values it will hold, so a
	// column shares one decimal position and the figures can be compared by eye.
	// A single global rule cannot do this: $0.02 needs three decimals to stay
	// meaningful while $30.00 needs two, and mixing them in one column puts the
	// decimal points out of line.
	prec := [4]int{}
	for c, get := range [4]func(pricing.Rate) float64{
		func(r pricing.Rate) float64 { return r.In },
		func(r pricing.Rate) float64 { return r.Out },
		func(r pricing.Rate) float64 { return r.CacheRead },
		func(r pricing.Rate) float64 { return r.CacheWrite },
	} {
		prec[c] = 2
		for _, r := range m.Rates {
			if p := neededDecimals(get(r)); p > prec[c] {
				prec[c] = p
			}
		}
	}

	t := newTable(th,
		column{title: "EFFECTIVE", align: alignLeft},
		column{title: "INPUT", align: alignRight},
		column{title: "OUTPUT", align: alignRight},
		column{title: "CACHE R", align: alignRight},
		column{title: "CACHE W", align: alignRight},
		column{title: "", align: alignLeft},
	)
	for i, r := range m.Rates {
		marker := ""
		if i == len(m.Rates)-1 {
			marker = "current"
		} else if change := describeChange(m.Rates[i], m.Rates[i+1]); change != "" {
			marker = change
		}
		markerCell := styled(marker, th.dim)
		if strings.HasPrefix(marker, "then ") {
			markerCell = styled(marker, th.warn)
		}
		t.add(
			plain(r.From.String()),
			plain(rateAt(r.In, prec[0])), plain(rateAt(r.Out, prec[1])),
			plain(rateAt(r.CacheRead, prec[2])), plain(rateAt(r.CacheWrite, prec[3])),
			markerCell,
		)
	}
	t.render(w)

	// Long-context surcharge, which applies above a prompt-size threshold and
	// is where large agent runs actually get expensive.
	last := m.Rates[len(m.Rates)-1]
	if last.TierThreshold > 0 {
		io.WriteString(w, "    "+th.dim(fmt.Sprintf(
			"above %s context: input %s · output %s · cache read %s",
			tokens(last.TierThreshold),
			rateAt(last.TierIn, neededDecimals(last.TierIn)),
			rateAt(last.TierOut, neededDecimals(last.TierOut)),
			rateAt(last.TierCacheRead, neededDecimals(last.TierCacheRead))))+"\n")
	}

	if len(m.Rates) == 1 {
		io.WriteString(w, "\n    "+th.dim("·")+"  "+th.dim(
			"only one observation on file — earlier usage is priced at this rate and flagged in reports")+"\n")
	}
	return true
}

// describeChange summarises the move from one rate to the next, so a cut or a
// hike is legible without doing arithmetic across two rows.
func describeChange(from, to pricing.Rate) string {
	if from.Out == 0 || to.Out == 0 {
		return ""
	}
	ratio := to.Out / from.Out
	switch {
	case ratio < 0.995:
		return fmt.Sprintf("then %.0f%% cut", (1-ratio)*100)
	case ratio > 1.005:
		return fmt.Sprintf("then %.0f%% rise", (ratio-1)*100)
	default:
		return "then adjusted"
	}
}

// neededDecimals is the smallest precision (at least 2) that renders v without
// losing a digit that matters. Cache-read rates run to $0.0075, so two decimals
// would show them all as $0.01 or $0.00.
func neededDecimals(v float64) int {
	if v == 0 {
		return 2
	}
	for _, p := range []int{2, 3, 4} {
		if rounded, _ := strconv.ParseFloat(strconv.FormatFloat(v, 'f', p, 64), 64); math.Abs(rounded-v) < 1e-9 {
			return p
		}
	}
	return 4
}

// rateAt renders a per-million price at a fixed precision.
func rateAt(v float64, decimals int) string {
	if v == 0 {
		return "—"
	}
	return "$" + strconv.FormatFloat(v, 'f', decimals, 64)
}
