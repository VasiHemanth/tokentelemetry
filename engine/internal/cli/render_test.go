package cli

import (
	"bytes"
	"strings"
	"testing"

	"github.com/VasiHemanth/tokentelemetry/engine/internal/pricing"
)

// Every line of a table must be the same width and every column must start at
// the same offset. This is the property that makes a figure matchable to its
// header without counting columns.
func TestTableColumnsAlign(t *testing.T) {
	th := theme{on: false}
	tbl := newTable(th,
		column{title: "NAME", align: alignLeft},
		column{title: "A", align: alignRight},
		column{title: "B", align: alignRight},
	)
	tbl.add(plain("short"), plain("1"), plain("22"))
	tbl.add(plain("a-much-longer-name"), plain("333333"), plain("4"))
	tbl.addSub(plain("nested"), plain("55"), plain("6"))

	var buf bytes.Buffer
	tbl.render(&buf)
	lines := strings.Split(strings.TrimRight(buf.String(), "\n"), "\n")

	// Right-aligned columns share a right edge, so the last character of every
	// data line sits at the same offset.
	var width int
	for i, ln := range lines {
		if i == 1 || i == len(lines)-1 {
			continue // rules
		}
		w := displayWidth(ln)
		if width == 0 {
			width = w
		} else if w != width {
			t.Errorf("line %d width %d, want %d\n%q", i, w, width, ln)
		}
	}
}

// An indented detail row consumes part of the first column, so its figures must
// still land on the parent's grid.
func TestSubRowStaysOnGrid(t *testing.T) {
	th := theme{on: false}
	tbl := newTable(th,
		column{title: "DATE", align: alignLeft},
		column{title: "COST", align: alignRight},
	)
	tbl.add(plain("2026-08-23"), plain("$44.56"))
	tbl.addSub(plain("model-x"), plain("$42.63"))

	var buf bytes.Buffer
	tbl.render(&buf)
	lines := strings.Split(strings.TrimRight(buf.String(), "\n"), "\n")
	parent, sub := lines[2], lines[3]
	if strings.Index(parent, "$44.56") != strings.Index(sub, "$42.63") {
		t.Errorf("sub-row cost column misaligned:\n%q\n%q", parent, sub)
	}
}

// Colour must not change layout: escape sequences occupy no terminal cells.
func TestColorDoesNotDisturbAlignment(t *testing.T) {
	build := func(on bool) string {
		th := theme{on: on}
		tbl := newTable(th, column{title: "A", align: alignLeft}, column{title: "B", align: alignRight})
		tbl.add(plain("x"), styled("$1.00", th.money))
		tbl.add(plain("yyyy"), styled("$22.00", th.money))
		var buf bytes.Buffer
		tbl.render(&buf)
		return buf.String()
	}
	plainOut, colorOut := build(false), build(true)
	pl := strings.Split(strings.TrimRight(plainOut, "\n"), "\n")
	cl := strings.Split(strings.TrimRight(colorOut, "\n"), "\n")
	for i := range pl {
		if displayWidth(pl[i]) != displayWidth(cl[i]) {
			t.Errorf("line %d: plain width %d, coloured width %d", i, displayWidth(pl[i]), displayWidth(cl[i]))
		}
	}
}

func TestDisplayWidth(t *testing.T) {
	for in, want := range map[string]int{
		"abc":               3,
		"":                  0,
		"\x1b[1mabc\x1b[0m": 3,
		"日本語":               6, // wide runes
		"a日":                3,
	} {
		if got := displayWidth(in); got != want {
			t.Errorf("displayWidth(%q) = %d, want %d", in, got, want)
		}
	}
}

// Paths truncate from the left because a path's tail identifies it.
func TestTruncate(t *testing.T) {
	if got := truncate("/home/user/code/project", 10, true); !strings.HasSuffix(got, "project") {
		t.Errorf("left-truncate = %q, want the tail preserved", got)
	}
	if got := truncate("verylongmodelname-v2", 10, false); !strings.HasPrefix(got, "very") {
		t.Errorf("right-truncate = %q, want the head preserved", got)
	}
	if got := truncate("short", 10, false); got != "short" {
		t.Errorf("truncate widened a short string to %q", got)
	}
}

// Each rate column picks one precision, so decimal points line up.
func TestNeededDecimals(t *testing.T) {
	for v, want := range map[float64]int{
		1.0: 2, 6.0: 2, 0.25: 2, 0.625: 3, 0.02: 2, 0.0075: 4, 0: 2,
	} {
		if got := neededDecimals(v); got != want {
			t.Errorf("neededDecimals(%v) = %d, want %d", v, got, want)
		}
	}
}

// A price change is summarised so the reader does not have to do arithmetic
// across two rows.
func TestDescribeChange(t *testing.T) {
	cut := describeChange(rateOf(6.0), rateOf(1.2))
	if cut != "then 80% cut" {
		t.Errorf("describeChange 6.00 -> 1.20 = %q, want \"then 80%% cut\"", cut)
	}
	rise := describeChange(rateOf(10.0), rateOf(15.0))
	if rise != "then 50% rise" {
		t.Errorf("describeChange 10 -> 15 = %q, want \"then 50%% rise\"", rise)
	}
}

func TestMoneyAndTokenFormatting(t *testing.T) {
	for v, want := range map[float64]string{
		0: "$0.00", 0.0001: "$0.0001", 12.5: "$12.50", 8496.97: "$8,496.97",
	} {
		if got := money(v); got != want {
			t.Errorf("money(%v) = %q, want %q", v, got, want)
		}
	}
	for v, want := range map[int64]string{
		0: "0", 812: "812", 60645: "60.6K", 1_500_000: "1.5M", 21_870_000_000: "21.87B",
	} {
		if got := tokens(v); got != want {
			t.Errorf("tokens(%d) = %q, want %q", v, got, want)
		}
	}
}

// rateOf builds a minimal rate for change-description tests.
func rateOf(out float64) pricing.Rate { return pricing.Rate{Out: out} }
