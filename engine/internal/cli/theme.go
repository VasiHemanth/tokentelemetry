package cli

import (
	"strings"
	"unicode/utf8"
)

// ANSI codes. Kept to the 16-colour basic set so the output looks right on a
// default terminal, over SSH, and inside tmux without a 256-colour TERM.
const (
	ansiReset  = "\x1b[0m"
	ansiBold   = "\x1b[1m"
	ansiDim    = "\x1b[2m"
	ansiRed    = "\x1b[31m"
	ansiGreen  = "\x1b[32m"
	ansiYellow = "\x1b[33m"
	ansiBlue   = "\x1b[34m"
	ansiCyan   = "\x1b[36m"
)

// theme applies colour, or does not. Every style is a method rather than a
// bare constant so the no-colour path is a single branch in one place and
// width calculations never have to know whether escapes are present.
type theme struct{ on bool }

func (t theme) wrap(code, s string) string {
	if !t.on || s == "" {
		return s
	}
	return code + s + ansiReset
}

// Accent is the `::` section marker — the one strong colour in the output.
func (t theme) accent(s string) string { return t.wrap(ansiBold+ansiBlue, s) }
func (t theme) head(s string) string   { return t.wrap(ansiBold, s) }
func (t theme) rule(s string) string   { return t.wrap(ansiDim, s) }
func (t theme) dim(s string) string    { return t.wrap(ansiDim, s) }
func (t theme) warn(s string) string   { return t.wrap(ansiYellow, s) }
func (t theme) bad(s string) string    { return t.wrap(ansiRed, s) }
func (t theme) money(s string) string  { return t.wrap(ansiGreen, s) }
func (t theme) strong(s string) string { return t.wrap(ansiBold, s) }
func (t theme) label(s string) string  { return t.wrap(ansiCyan, s) }

// displayWidth measures a string in terminal cells.
//
// Escape sequences occupy no cells, and East Asian characters occupy two —
// both matter here because project names are arbitrary filesystem paths, and
// getting either wrong knocks every column after it out of alignment.
func displayWidth(s string) int {
	w := 0
	inEscape := false
	for _, r := range s {
		if inEscape {
			if r == 'm' {
				inEscape = false
			}
			continue
		}
		if r == 0x1b {
			inEscape = true
			continue
		}
		w += runeWidth(r)
	}
	return w
}

// runeWidth reports the terminal cells a rune occupies. Only the wide ranges
// that actually turn up in paths and model ids are enumerated; everything else
// is single-width.
func runeWidth(r rune) int {
	switch {
	case r < 0x1100:
		return 1
	case r >= 0x1100 && r <= 0x115F, // Hangul Jamo
		r >= 0x2E80 && r <= 0xA4CF, // CJK radicals, Kangxi, CJK ideographs
		r >= 0xAC00 && r <= 0xD7A3, // Hangul syllables
		r >= 0xF900 && r <= 0xFAFF, // CJK compatibility ideographs
		r >= 0xFE30 && r <= 0xFE6F, // CJK compatibility forms
		r >= 0xFF00 && r <= 0xFF60, // Fullwidth forms
		r >= 0xFFE0 && r <= 0xFFE6,
		r >= 0x1F300 && r <= 0x1F64F, // emoji
		r >= 0x1F900 && r <= 0x1F9FF,
		r >= 0x20000 && r <= 0x3FFFD: // CJK extension planes
		return 2
	}
	return 1
}

// truncate shortens a string to width cells, marking the cut with an ellipsis.
// Truncation happens on the LEFT for paths, because the distinguishing part of
// a filesystem path is its tail.
func truncate(s string, width int, fromLeft bool) string {
	if displayWidth(s) <= width || width <= 1 {
		return s
	}
	runes := []rune(s)
	if fromLeft {
		w := 0
		for i := len(runes) - 1; i >= 0; i-- {
			w += runeWidth(runes[i])
			if w > width-1 {
				return "…" + string(runes[i+1:])
			}
		}
		return s
	}
	w := 0
	for i, r := range runes {
		w += runeWidth(r)
		if w > width-1 {
			return string(runes[:i]) + "…"
		}
	}
	return s
}

// pad aligns s within width cells.
func pad(s string, width int, right bool) string {
	gap := width - displayWidth(s)
	if gap <= 0 {
		return s
	}
	fill := strings.Repeat(" ", gap)
	if right {
		return fill + s
	}
	return s + fill
}

func repeat(s string, n int) string {
	if n <= 0 {
		return ""
	}
	return strings.Repeat(s, n)
}

var _ = utf8.RuneCountInString // retained for reference; displayWidth supersedes it
