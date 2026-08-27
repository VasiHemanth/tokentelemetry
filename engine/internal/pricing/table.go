// Package pricing resolves a model id and a point in time to a token rate.
//
// Two properties distinguish this from the table it replaces:
//
//  1. Rates are effective-dated. A model carries a series of rates, each with
//     the date it took effect, and a call is priced with the rate that was
//     live when the call happened. A price cut does not silently rewrite what
//     last month cost. This is what makes discount windows and the gpt-5.6
//     luna/terra cuts representable at all.
//
//  2. A miss is a miss. The old table fell back to a substring scan and then
//     to a $2/$10 "_default", so an unknown model silently produced a
//     confident-looking wrong number — 965 sessions on a *free* model were
//     billed $380. Here an unresolved model returns ConfidenceUnpriced and a
//     zero cost, and the caller is expected to surface that.
package pricing

import (
	"fmt"
	"sort"
	"strings"
	"time"
)

// Confidence records how a rate was resolved, so reports can be honest about
// which dollars are solid and which are inferred.
type Confidence uint8

const (
	// ConfidenceUnpriced means no rate is known. Cost is zero and must be
	// reported as unknown, never as $0.00 of real spend.
	ConfidenceUnpriced Confidence = iota
	// ConfidenceAlias resolved through a known alias of a priced model.
	ConfidenceAlias
	// ConfidenceProvider matched a (provider, model) pair exactly.
	ConfidenceProvider
	// ConfidenceExact matched the model id in the first-party table.
	ConfidenceExact
)

func (c Confidence) String() string {
	switch c {
	case ConfidenceExact:
		return "exact"
	case ConfidenceProvider:
		return "provider"
	case ConfidenceAlias:
		return "alias"
	default:
		return "unpriced"
	}
}

// Rate is a price schedule effective from a given date, in USD per 1M tokens.
//
// TierThreshold, when non-zero, is the prompt size above which the long-context
// surcharge applies (OpenAI charges double above 272k on the gpt-5.6 line;
// Anthropic above 200k). The old implementation dropped tiers entirely and so
// under-billed exactly the huge-context agent sessions that dominate real cost.
type Rate struct {
	From       Date    `json:"from"`
	In         float64 `json:"in"`
	Out        float64 `json:"out"`
	CacheRead  float64 `json:"cache_read"`
	CacheWrite float64 `json:"cache_write"`
	// CacheWrite1h prices Anthropic's 1-hour prompt-cache TTL, which bills at
	// 2x input against the 5-minute TTL's 1.25x. Resolved at sync time rather
	// than by a multiplier here, because the old code applied Anthropic's
	// 1.25x rule to every provider's cache writes.
	CacheWrite1h float64 `json:"cache_write_1h,omitempty"`

	TierThreshold  int64   `json:"tier_threshold,omitempty"`
	TierIn         float64 `json:"tier_in,omitempty"`
	TierOut        float64 `json:"tier_out,omitempty"`
	TierCacheRead  float64 `json:"tier_cache_read,omitempty"`
	TierCacheWrite float64 `json:"tier_cache_write,omitempty"`

	// Source is the provider this rate was taken from, kept so a surprising
	// number can be traced back to whoever published it.
	Source string `json:"source,omitempty"`
}

// ForContext returns the rate components to use for a prompt of the given size,
// applying the long-context tier when one is configured and exceeded.
func (r Rate) ForContext(ctx int64) (in, out, cacheRead, cacheWrite float64) {
	if r.TierThreshold > 0 && ctx > r.TierThreshold {
		return r.TierIn, r.TierOut, r.TierCacheRead, r.TierCacheWrite
	}
	return r.In, r.Out, r.CacheRead, r.CacheWrite
}

// Model is one model's full price history.
type Model struct {
	ID string `json:"id"`
	// Rates sorted ascending by effective date.
	Rates []Rate `json:"rates"`
	// FirstParty is true when these rates come from the vendor that makes the
	// model rather than a reseller.
	FirstParty bool `json:"first_party,omitempty"`
}

// rateAt returns the rate in force at t. Calls that predate the earliest known
// rate use that earliest rate — the alternative is refusing to price the entire
// backlog, which is worse than pricing it at the oldest rate we have.
func (m *Model) rateAt(t time.Time) (Rate, bool) {
	if len(m.Rates) == 0 {
		return Rate{}, false
	}
	if t.IsZero() {
		return m.Rates[len(m.Rates)-1], true
	}
	d := DateOf(t)
	// Rates are sorted ascending; find the last one that had taken effect.
	i := sort.Search(len(m.Rates), func(i int) bool {
		return m.Rates[i].From.After(d)
	})
	if i == 0 {
		return m.Rates[0], true
	}
	return m.Rates[i-1], true
}

// Table is the loaded pricing dataset.
type Table struct {
	Updated Date
	// Models keyed by normalised model id, carrying first-party rates.
	Models map[string]*Model
	// ByProvider keyed by "provider\x00model" for reseller-specific rates,
	// used only when the scanner actually recorded which provider served the
	// call. Never consulted otherwise — guessing a provider is how the old
	// table ended up billing luna at a reseller's undiscounted rate.
	ByProvider map[string]*Model
	// Aliases maps a non-canonical id an agent emits to a canonical model id.
	// This replaces the old substring scan, which matched "auto" inside
	// "codex-auto-review" and billed it at Claude Sonnet rates.
	Aliases map[string]string
}

const providerSep = "\x00"

func providerKey(provider, model string) string {
	return strings.ToLower(strings.TrimSpace(provider)) + providerSep + model
}

// Normalize lowercases a model id and strips aggregator namespace prefixes and
// the deployment suffixes agents bolt on. It is deliberately conservative:
// every transformation here is reversible-in-meaning, unlike substring search.
func Normalize(model string) string {
	m := strings.ToLower(strings.TrimSpace(model))
	if m == "" {
		return ""
	}
	// "openrouter/anthropic/claude-opus-5" -> "claude-opus-5"
	for _, prefix := range []string{"openrouter/", "fireworks/", "together/", "accounts/fireworks/models/", "models/"} {
		if strings.HasPrefix(m, prefix) {
			m = m[len(prefix):]
		}
	}
	// Vendor-namespaced ids from aggregators: "moonshotai/kimi-k2" -> keep the
	// tail, which is what the first-party table is keyed on.
	if i := strings.LastIndex(m, "/"); i >= 0 && i < len(m)-1 {
		m = m[i+1:]
	}
	// Bedrock/Vertex deployment suffixes: "claude-opus-5-v1:0" -> "claude-opus-5".
	if i := strings.Index(m, ":"); i > 0 {
		m = m[:i]
	}
	m = strings.TrimSuffix(m, "-latest")
	return m
}

// Lookup resolves a model (and optional provider) to the rate in force at t.
func (tbl *Table) Lookup(model, provider string, t time.Time) (Rate, Confidence, bool) {
	id := Normalize(model)
	if id == "" {
		return Rate{}, ConfidenceUnpriced, false
	}
	// A recorded provider is authoritative: it tells us who actually billed the
	// call, markup included.
	if provider != "" {
		if m, ok := tbl.ByProvider[providerKey(provider, id)]; ok {
			if r, ok := m.rateAt(t); ok {
				return r, ConfidenceProvider, true
			}
		}
	}
	if m, ok := tbl.Models[id]; ok {
		if r, ok := m.rateAt(t); ok {
			return r, ConfidenceExact, true
		}
	}
	if canon, ok := tbl.Aliases[id]; ok {
		if m, ok := tbl.Models[canon]; ok {
			if r, ok := m.rateAt(t); ok {
				return r, ConfidenceAlias, true
			}
		}
	}
	return Rate{}, ConfidenceUnpriced, false
}

// Find resolves a query to a model, following aliases. The second return is the
// id the query resolved through, so a caller can show that an alias was used.
func (tbl *Table) Find(query string) (*Model, string, bool) {
	id := Normalize(query)
	if id == "" {
		return nil, "", false
	}
	if m, ok := tbl.Models[id]; ok {
		return m, id, true
	}
	if canon, ok := tbl.Aliases[id]; ok {
		if m, ok := tbl.Models[canon]; ok {
			return m, id, true
		}
	}
	return nil, id, false
}

// Describe renders a model's price history, for `tokentelemetry price`.
func (tbl *Table) Describe(model string) (string, bool) {
	id := Normalize(model)
	m, ok := tbl.Models[id]
	if !ok {
		if canon, aliased := tbl.Aliases[id]; aliased {
			m, ok = tbl.Models[canon]
		}
	}
	if !ok {
		return "", false
	}
	var b strings.Builder
	fmt.Fprintf(&b, "%s\n", m.ID)
	for _, r := range m.Rates {
		fmt.Fprintf(&b, "  from %s  in $%.4g  out $%.4g  cache-read $%.4g  cache-write $%.4g",
			r.From, r.In, r.Out, r.CacheRead, r.CacheWrite)
		if r.TierThreshold > 0 {
			fmt.Fprintf(&b, "  (>%dk ctx: in $%.4g out $%.4g)", r.TierThreshold/1000, r.TierIn, r.TierOut)
		}
		if r.Source != "" {
			fmt.Fprintf(&b, "  [%s]", r.Source)
		}
		b.WriteByte('\n')
	}
	return b.String(), true
}
