package cli

import (
	"io"
	"strings"
)

// align controls a column's horizontal alignment.
type align uint8

const (
	alignLeft align = iota
	alignRight
)

// column describes one column of a table.
type column struct {
	title string
	align align
	// max caps the rendered width; longer cells are truncated. Zero means no
	// cap. Paths truncate from the left, since a path's tail identifies it.
	max       int
	truncLeft bool
}

// cell is one rendered value plus the style to paint it with. Style is applied
// only after widths are computed, so escape sequences can never disturb
// alignment.
type cell struct {
	text string
	// lines carries a multi-line value, rendered one physical line each with the
	// other columns blank beneath. This is how a row lists the several models an
	// agent used on a day without spawning a row per model.
	lines []string
	style func(string) string
}

func plain(s string) cell { return cell{text: s} }

func styled(s string, f func(string) string) cell { return cell{text: s, style: f} }

func multi(lines []string, f func(string) string) cell {
	if len(lines) == 0 {
		return cell{}
	}
	return cell{text: lines[0], lines: lines, style: f}
}

// height is how many physical lines the cell occupies.
func (c cell) height() int {
	if len(c.lines) == 0 {
		return 1
	}
	return len(c.lines)
}

// lineAt returns the nth physical line of the cell, or "" past its end.
func (c cell) lineAt(n int) string {
	if len(c.lines) == 0 {
		if n == 0 {
			return c.text
		}
		return ""
	}
	if n < len(c.lines) {
		return c.lines[n]
	}
	return ""
}

func (c cell) render() string {
	if c.style == nil {
		return c.text
	}
	return c.style(c.text)
}

// row is a table row. indent renders it as a nested detail line under the
// preceding row, which is how per-model breakdowns attach to their parent.
type row struct {
	cells []cell
	// indent insets the first column, used for nested detail rows.
	indent bool
	// rule draws a separator above the row, used to close a group.
	rule bool
	// spacer draws a blank line above the row, separating one top-level group
	// from the next. Without it a long report is an undifferentiated wall and
	// finding where one day ends means reading the date column character by
	// character.
	spacer bool
}

// table lays out aligned columns.
//
// text/tabwriter is deliberately not used: it left-aligns every cell, which is
// the reason numeric output was hard to read — the eye has no common edge to
// scan down, so matching a figure to its header means counting columns.
// Numbers are right-aligned here and share a right edge.
type table struct {
	cols   []column
	rows   []row
	th     theme
	indent string
}

func newTable(th theme, cols ...column) *table {
	return &table{cols: cols, th: th, indent: "  "}
}

func (t *table) add(cells ...cell) { t.rows = append(t.rows, row{cells: cells}) }

func (t *table) addSub(cells ...cell) { t.rows = append(t.rows, row{cells: cells, indent: true}) }

// addRuled adds a row preceded by a separator, closing off what came before.
func (t *table) addRuled(cells ...cell) { t.rows = append(t.rows, row{cells: cells, rule: true}) }

// addGroup adds a row preceded by a blank line, opening a new top-level group.
func (t *table) addGroup(cells ...cell) { t.rows = append(t.rows, row{cells: cells, spacer: true}) }

// widths computes each column's rendered width from its header and content.
func (t *table) widths() []int {
	w := make([]int, len(t.cols))
	for i, c := range t.cols {
		w[i] = displayWidth(c.title)
	}
	for _, r := range t.rows {
		for i, c := range r.cells {
			if i >= len(w) {
				break
			}
			n := 0
			for k := 0; k < c.height(); k++ {
				if x := displayWidth(c.lineAt(k)); x > n {
					n = x
				}
			}
			if t.cols[i].max > 0 && n > t.cols[i].max {
				n = t.cols[i].max
			}
			// An indented row spends part of the first column on its indent, so
			// it must claim that space here or the sub-row's figures land two
			// cells right of the parent's and the grid breaks.
			if i == 0 && r.indent {
				n += subIndent
			}
			if n > w[i] {
				w[i] = n
			}
		}
	}
	return w
}

// subIndent is how far a detail row is inset beneath its parent.
const subIndent = 2

const colGap = "   "

// render writes the table: a header, a rule, the rows, and a closing rule.
func (t *table) render(out io.Writer) {
	if len(t.rows) == 0 {
		return
	}
	w := t.widths()

	// Header.
	var head strings.Builder
	for i, c := range t.cols {
		if i > 0 {
			head.WriteString(colGap)
		}
		head.WriteString(pad(c.title, w[i], c.align == alignRight))
	}
	io.WriteString(out, t.indent+t.th.head(strings.TrimRight(head.String(), " "))+"\n")
	t.writeRule(out, w)

	for _, r := range t.rows {
		if r.spacer {
			io.WriteString(out, "\n")
		}
		if r.rule {
			t.writeRule(out, w)
		}
		height := 1
		for _, c := range r.cells {
			if h := c.height(); h > height {
				height = h
			}
		}
		for ln := 0; ln < height; ln++ {
			t.writeLine(out, w, r, ln)
		}
	}
	t.writeRule(out, w)
}

// writeLine emits one physical line of a (possibly multi-line) row.
func (t *table) writeLine(out io.Writer, w []int, r row, ln int) {
	{
		var line strings.Builder
		for i := range t.cols {
			if i > 0 {
				line.WriteString(colGap)
			}
			var c cell
			if i < len(r.cells) {
				c = r.cells[i]
			}
			c.text = c.lineAt(ln)
			// The first column of a detail row is narrowed by the indent it
			// already consumed, keeping every later column on the parent grid.
			cw := w[i]
			if i == 0 && r.indent {
				cw -= subIndent
			}
			text := c.text
			if lim := t.cols[i].max; lim > 0 {
				text = truncate(text, lim, t.cols[i].truncLeft)
			}
			text = truncate(text, cw, t.cols[i].truncLeft)

			// Pad the plain text, then style — never the other way round, or the
			// escape sequences would be counted as visible width.
			padded := pad(text, cw, t.cols[i].align == alignRight)
			// Style the visible text only, preserving the padding either side.
			// An entirely blank cell must be left alone: trimming it would make
			// `lead` and `trail` each equal the full width, and the cell would
			// render twice as wide as its column — which knocked every later
			// column out of line on multi-line rows.
			if c.style != nil && strings.TrimSpace(padded) != "" {
				lead := len(padded) - len(strings.TrimLeft(padded, " "))
				trail := len(padded) - len(strings.TrimRight(padded, " "))
				padded = padded[:lead] + c.style(strings.TrimSpace(padded)) + repeat(" ", trail)
			}
			line.WriteString(padded)
		}
		prefix := t.indent
		if r.indent {
			prefix = t.indent + repeat(" ", subIndent)
		}
		io.WriteString(out, strings.TrimRight(prefix+line.String(), " ")+"\n")
	}
}

func (t *table) writeRule(out io.Writer, w []int) {
	total := 0
	for i, n := range w {
		if i > 0 {
			total += len(colGap)
		}
		total += n
	}
	io.WriteString(out, t.indent+t.th.rule(repeat("─", total))+"\n")
}

// section writes a `::`-prefixed heading, the one structural marker in the
// output. Borrowed from pacman, where it reliably separates phases of a run
// without needing boxes or blank-line gymnastics.
func section(out io.Writer, th theme, title string) {
	io.WriteString(out, "\n"+th.accent(" ::")+" "+th.strong(title)+"\n\n")
}

// fieldRow is one line of a summary block. sub indents the label without
// disturbing the shared value edge.
type fieldRow struct {
	label string
	value string
	note  string
	sub   bool
}

// fields renders a summary block with the labels left-aligned and the VALUES
// sharing a right edge, so figures can be compared down the column and the
// trailing notes all start at the same place.
func fields(out io.Writer, th theme, rows []fieldRow) {
	lw, vw := 0, 0
	for _, r := range rows {
		l := displayWidth(r.label)
		if r.sub {
			l += 2
		}
		if l > lw {
			lw = l
		}
		if v := displayWidth(r.value); v > vw {
			vw = v
		}
	}
	for _, r := range rows {
		label := r.label
		if r.sub {
			label = "  " + label
		}
		line := "    " + pad(label, lw, false) + "   " + pad(r.value, vw, true)
		if r.note != "" {
			line += "   " + th.dim(r.note)
		}
		io.WriteString(out, strings.TrimRight(line, " ")+"\n")
	}
}
