package report

import (
	"strings"

	"github.com/VasiHemanth/tokentelemetry/engine/internal/cost"
	"github.com/VasiHemanth/tokentelemetry/engine/internal/model"
)

// Dimension is something usage can be grouped by. Grouping is composable:
// `--group-by agent,model` nests models inside agents inside whatever the
// command's own top-level grouping is.
type Dimension string

const (
	DimDay      Dimension = "day"
	DimWeek     Dimension = "week"
	DimMonth    Dimension = "month"
	DimAgent    Dimension = "agent"
	DimModel    Dimension = "model"
	DimProvider Dimension = "provider"
	DimProject  Dimension = "project"
	DimSession  Dimension = "session"
)

// Dimensions lists every valid grouping, for help text and validation.
var Dimensions = []Dimension{
	DimDay, DimWeek, DimMonth, DimAgent, DimModel, DimProvider, DimProject, DimSession,
}

// ParseDimensions turns a comma-separated list into dimensions, rejecting
// anything unknown so a typo fails loudly instead of silently grouping by
// nothing.
func ParseDimensions(spec string) ([]Dimension, error) {
	if strings.TrimSpace(spec) == "" {
		return nil, nil
	}
	var out []Dimension
	for _, part := range strings.Split(spec, ",") {
		p := Dimension(strings.ToLower(strings.TrimSpace(part)))
		if p == "" {
			continue
		}
		// An explicit opt-out of nesting, so the flat table stays reachable now
		// that grouping is the default.
		if p == "none" || p == "flat" {
			return nil, nil
		}
		if !p.valid() {
			return nil, &UnknownDimensionError{Name: string(p)}
		}
		out = append(out, p)
	}
	return out, nil
}

// UnknownDimensionError reports a grouping name we do not recognise.
type UnknownDimensionError struct{ Name string }

func (e *UnknownDimensionError) Error() string {
	names := make([]string, len(Dimensions))
	for i, d := range Dimensions {
		names[i] = string(d)
	}
	return "unknown grouping " + e.Name + " (valid: " + strings.Join(names, ", ") + ")"
}

func (d Dimension) valid() bool {
	for _, x := range Dimensions {
		if x == d {
			return true
		}
	}
	return false
}

// Title is the column heading for this dimension.
func (d Dimension) Title() string { return strings.ToUpper(string(d)) }

// keyOf extracts a turn's value for this dimension.
func (d Dimension) keyOf(t model.Turn, c cost.Cost, g Granularity) string {
	switch d {
	case DimDay:
		return bucketKey(t.Timestamp, Daily)
	case DimWeek:
		return bucketKey(t.Timestamp, Weekly)
	case DimMonth:
		return bucketKey(t.Timestamp, Monthly)
	case DimAgent:
		return string(t.Agent)
	case DimModel:
		if c.Model != "" {
			return c.Model
		}
		return t.Model
	case DimProvider:
		return t.Provider
	case DimProject:
		return t.Project
	case DimSession:
		return t.SessionID
	}
	return ""
}
