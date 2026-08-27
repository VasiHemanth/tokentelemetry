package cli

import (
	"bytes"
	"strings"
	"testing"
)

func TestMultiLineCellAlignment(t *testing.T) {
	th := theme{on: false}
	tbl := newTable(th,
		column{title: "DATE", align: alignLeft},
		column{title: "AGENT", align: alignLeft},
		column{title: "MODELS", align: alignLeft},
		column{title: "COST", align: alignRight},
	)
	tbl.add(plain("2026-08-25"), plain("- codex"),
		multi([]string{"- aaa", "- bbbbb", "- cc"}, nil), plain("$1.00"))
	var buf bytes.Buffer
	tbl.render(&buf)
	lines := strings.Split(strings.TrimRight(buf.String(), "\n"), "\n")
	for i, l := range lines {
		t.Logf("%d: %q", i, l)
	}
	base := strings.Index(lines[2], "- aaa")
	for _, want := range []string{"- bbbbb", "- cc"} {
		for _, l := range lines[3:] {
			if strings.Contains(l, want) {
				if got := strings.Index(l, want); got != base {
					t.Errorf("%q at col %d, want %d", want, got, base)
				}
			}
		}
	}
}

// A styled cell with no visible text must occupy exactly its column width.
// Trimming a blank cell made lead and trail each equal the full width, so it
// rendered twice as wide and shifted every column after it.
func TestBlankStyledCellKeepsWidth(t *testing.T) {
	th := theme{on: false}
	tbl := newTable(th,
		column{title: "A", align: alignLeft},
		column{title: "BBBBBBBB", align: alignLeft},
		column{title: "C", align: alignLeft},
	)
	tbl.add(plain("x"), styled("- filled", th.label), plain("here"))
	tbl.add(plain("y"), styled("", th.label), plain("here"))

	var buf bytes.Buffer
	tbl.render(&buf)
	lines := strings.Split(strings.TrimRight(buf.String(), "\n"), "\n")
	if a, b := strings.Index(lines[2], "here"), strings.Index(lines[3], "here"); a != b {
		t.Errorf("column C at %d with a filled cell, %d with a blank one:\n%q\n%q", a, b, lines[2], lines[3])
	}
}
