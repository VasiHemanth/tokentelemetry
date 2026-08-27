// Package cli implements the tokentelemetry command line.
package cli

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"strings"
	"time"

	"github.com/VasiHemanth/tokentelemetry/engine/internal/ingest"
	"github.com/VasiHemanth/tokentelemetry/engine/internal/pricing"
	"github.com/VasiHemanth/tokentelemetry/engine/internal/report"
)

// Version is stamped at build time with -ldflags.
var Version = "dev"

const usage = `tokentelemetry — local cost and token telemetry for AI coding agents

USAGE
  tokentelemetry <command> [flags]

COMMANDS
  daily      usage per day
  weekly     usage per ISO week
  monthly    usage per month
  session    usage per session, most expensive first
  model      usage per model
  project    usage per project
  price      show a model's rate history
  agents     list detected agents and where their logs live
  version    print the version

FILTERS (every report command)
  --since, --from DATE   include usage on or after DATE (YYYY-MM-DD)
  --until, --to DATE     include usage on or before DATE
  --agent NAME           repeatable; e.g. --agent claude --agent codex
  --model NAME           repeatable; e.g. --model claude-opus-5
  --project NAME         repeatable; full path or trailing folder name
  --subagents MODE       include (default) | only | exclude

OUTPUT
  --json                 machine-readable output
  --group-by DIMS        nest rows by dimensions (default: model)
                         day, week, month, agent, model, provider, project,
                         session, or "none" for a flat table
                         e.g. --group-by agent,model
  --compact              abbreviate counts (1.2M) instead of full digits
  --limit N              show at most N rows (0 = all)
  --verbose              add scan diagnostics (dedup counts, turns scanned)
  --no-color             disable colour (also honours NO_COLOR)

EXAMPLES
  tokentelemetry daily --since 2026-08-01
  tokentelemetry daily --group-by agent,model
  tokentelemetry monthly --group-by provider
  tokentelemetry session --project tokentelemetry --limit 10
  tokentelemetry price gpt-5.6-luna
`

// Main runs the CLI and returns a process exit code.
func Main(args []string) int {
	if len(args) < 2 {
		fmt.Fprint(os.Stderr, usage)
		return 2
	}
	cmd := args[1]
	rest := args[2:]

	switch cmd {
	case "-h", "--help", "help":
		fmt.Print(usage)
		return 0
	case "version", "--version", "-v":
		fmt.Printf("tokentelemetry %s\n", Version)
		return 0
	case "price":
		return cmdPrice(rest)
	case "agents":
		return cmdAgents(rest)
	case "daily", "weekly", "monthly", "session", "model", "project":
		return cmdReport(cmd, rest)
	default:
		fmt.Fprintf(os.Stderr, "tokentelemetry: unknown command %q\n\n", cmd)
		fmt.Fprint(os.Stderr, usage)
		return 2
	}
}

type stringList []string

func (s *stringList) String() string { return strings.Join(*s, ",") }
func (s *stringList) Set(v string) error {
	// Accept both repeated flags and a single comma-separated value, because
	// both spellings are what people reach for.
	for _, part := range strings.Split(v, ",") {
		if part = strings.TrimSpace(part); part != "" {
			*s = append(*s, part)
		}
	}
	return nil
}

func cmdReport(cmd string, args []string) int {
	fs := flag.NewFlagSet(cmd, flag.ContinueOnError)
	fs.SetOutput(io.Discard)

	var agents, models, projects stringList
	since := fs.String("since", "", "")
	from := fs.String("from", "", "")
	until := fs.String("until", "", "")
	to := fs.String("to", "", "")
	subagents := fs.String("subagents", "include", "")
	asJSON := fs.Bool("json", false, "")
	breakdown := fs.Bool("breakdown", false, "")
	limit := fs.Int("limit", 0, "")
	noColor := fs.Bool("no-color", false, "")
	verbose := fs.Bool("verbose", false, "")
	compact := fs.Bool("compact", false, "")
	groupBy := fs.String("group-by", "", "")
	by := fs.String("by", "", "")
	fs.Var(&agents, "agent", "")
	fs.Var(&models, "model", "")
	fs.Var(&projects, "project", "")

	if err := fs.Parse(args); err != nil {
		fmt.Fprintf(os.Stderr, "tokentelemetry: %v\n\n%s", err, usage)
		return 2
	}

	f := report.Filter{
		From:      firstNonEmpty(*since, *from),
		To:        firstNonEmpty(*until, *to),
		Agents:    agents,
		Models:    models,
		Projects:  projects,
		Subagents: *subagents,
	}
	for _, d := range []string{f.From, f.To} {
		if d == "" {
			continue
		}
		if _, err := time.Parse("2006-01-02", d); err != nil {
			fmt.Fprintf(os.Stderr, "tokentelemetry: bad date %q, expected YYYY-MM-DD\n", d)
			return 2
		}
	}
	switch f.Subagents {
	case "include", "only", "exclude":
	default:
		fmt.Fprintf(os.Stderr, "tokentelemetry: --subagents must be include, only or exclude\n")
		return 2
	}

	dims, err := report.ParseDimensions(firstNonEmpty(*groupBy, *by))
	if err != nil {
		fmt.Fprintf(os.Stderr, "tokentelemetry: %v\n", err)
		return 2
	}
	// --breakdown is the common case spelled short.
	if len(dims) == 0 && *breakdown {
		dims = []report.Dimension{report.DimModel}
	}
	// Default to a row per model. Listing model names beside a row's combined
	// figures says which models were involved but not how much each one cost,
	// which is the question people are actually asking. A row per model costs
	// no extra screen — the name list already occupied one line each — and
	// every number becomes attributable. `--group-by none` restores the flat
	// table.
	if firstNonEmpty(*groupBy, *by) == "" && !*breakdown && cmd != "model" {
		dims = []report.Dimension{report.DimModel}
	}

	tbl, err := pricing.Load()
	if err != nil {
		fmt.Fprintf(os.Stderr, "tokentelemetry: %v\n", err)
		return 1
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	scanners := ingest.Available()
	if len(scanners) == 0 {
		fmt.Fprintln(os.Stderr, "tokentelemetry: no agent logs found on this machine (try `tokentelemetry agents`)")
		return 1
	}
	res, err := ingest.Run(ctx, scanners)
	if err != nil {
		fmt.Fprintf(os.Stderr, "tokentelemetry: %v\n", err)
		return 1
	}
	for _, e := range res.Errors {
		fmt.Fprintf(os.Stderr, "tokentelemetry: warning: %v\n", e)
	}

	g := report.Daily
	switch cmd {
	case "weekly":
		g = report.Weekly
	case "monthly":
		g = report.Monthly
	}
	rep := report.Build(res.Turns, tbl, f, g, res.Duplicates, dims)

	if *asJSON {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		if err := enc.Encode(view(cmd, rep)); err != nil {
			fmt.Fprintf(os.Stderr, "tokentelemetry: %v\n", err)
			return 1
		}
		return 0
	}
	render(os.Stdout, cmd, rep, *limit, colorEnabled(*noColor), *verbose, *compact, agents)
	return 0
}

// view narrows the report to the rows the chosen command is about, so `--json`
// output does not carry four aggregates the caller did not ask for.
func view(cmd string, rep *report.Report) any {
	type out struct {
		Command string          `json:"command"`
		Rows    []report.Bucket `json:"rows"`
		*report.Report
	}
	o := out{Command: cmd, Report: rep}
	switch cmd {
	case "session":
		o.Rows = rep.Sessions
	case "model":
		o.Rows = rep.ByModel
	case "project":
		o.Rows = rep.ByProject
	default:
		o.Rows = rep.Series
	}
	// Rows are the answer; the per-dimension aggregates stay available but are
	// not duplicated into Rows.
	o.Report.Series = nil
	if cmd != "model" {
		o.Report.ByModel = nil
	}
	if cmd != "project" {
		o.Report.ByProject = nil
	}
	if cmd != "session" {
		o.Report.Sessions = nil
	}
	return o
}

func cmdAgents(args []string) int {
	asJSON := len(args) > 0 && args[0] == "--json"
	type row struct {
		Agent     string   `json:"agent"`
		Installed bool     `json:"installed"`
		Roots     []string `json:"roots,omitempty"`
	}
	var rows []row
	for _, s := range ingest.All() {
		r := s.Roots()
		rows = append(rows, row{Agent: string(s.Agent()), Installed: len(r) > 0, Roots: r})
	}
	if asJSON {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		_ = enc.Encode(rows)
		return 0
	}
	for _, r := range rows {
		mark := "—"
		if r.Installed {
			mark = "✓"
		}
		fmt.Printf(" %s  %-14s %s\n", mark, r.Agent, strings.Join(r.Roots, ", "))
	}
	return 0
}

func firstNonEmpty(vals ...string) string {
	for _, v := range vals {
		if v != "" {
			return v
		}
	}
	return ""
}

func colorEnabled(noColor bool) bool {
	if noColor || os.Getenv("NO_COLOR") != "" || os.Getenv("TERM") == "dumb" {
		return false
	}
	fi, err := os.Stdout.Stat()
	if err != nil {
		return false
	}
	return fi.Mode()&os.ModeCharDevice != 0
}
