// Command pricing-sync regenerates the embedded pricing dataset from
// models.dev. It is a maintainer/CI tool and is never shipped to users — the
// tokentelemetry binary performs no network I/O at all.
//
// The behaviour that matters here is provider ranking. models.dev publishes the
// same model under every provider that resells it, and the Python sync this
// replaces walked those providers in *alphabetical* order and kept the first:
//
//	for provider_id, provider in sorted(data.items()):
//	    pricing.setdefault(mid, rates)
//
// "abacus" and "ai-router" sort before "anthropic" and "openai", so the flat
// table filled up with resellers' undiscounted list prices. gpt-5.6-luna was
// billed at $1.00/$6.00 (a reseller) instead of OpenAI's $0.20/$1.20 — a 5x
// overcharge that hid an 80% price cut. Measured across the dataset, 18% of
// models with a known first-party price got the wrong rate, spanning 0.05x to
// 267x.
//
// Here, providers are ranked: the vendor that makes the model always wins, and
// aggregators are only consulted for models no vendor publishes directly.
//
// Rates are appended to a dated series rather than overwriting, so each run
// records what changed and when.
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"sort"
	"strings"
	"time"

	"github.com/VasiHemanth/tokentelemetry/engine/internal/pricing"
)

const modelsDevURL = "https://models.dev/api.json"

// firstParty ranks the providers that actually make models, best first. A model
// published by any of these is priced from the highest-ranked one; everything
// not listed is an aggregator and only used when no vendor publishes the model.
var firstParty = []string{
	"openai",
	"anthropic",
	"google",
	"google-vertex",
	"google-vertex-anthropic",
	"deepseek",
	"xai",
	"moonshotai",
	"minimax",
	"zhipuai",
	"alibaba",
	"mistral",
	"meta",
	"cohere",
	"nvidia",
	"xiaomi",
	"stepfun",
	"inception",
	"morph",
	"perplexity",
	"llama",
}

// infraFallback ranks providers that host open-weight models nobody publishes
// first-party. Used only after every firstParty option has missed.
var infraFallback = []string{
	"groq", "cerebras", "fireworks-ai", "together-ai", "deepinfra",
	"sambanova", "vercel", "azure", "amazon-bedrock",
}

// rankOf places a provider in a tier (0 = makes the model, 1 = hosts
// open-weight models, 2 = reseller) and a rank within that tier. Returned in
// (tier, rank) order to match how callers destructure it — getting this pair
// backwards is precisely how the previous implementation let resellers win.
func rankOf(provider string) (tier int, rank int) {
	for i, p := range firstParty {
		if p == provider {
			return 0, i
		}
	}
	for i, p := range infraFallback {
		if p == provider {
			return 1, i
		}
	}
	return 2, 0
}

// better reports whether candidate (aTier,aRank) beats (bTier,bRank).
func better(aTier, aRank, bTier, bRank int) bool {
	if aTier != bTier {
		return aTier < bTier
	}
	return aRank < bRank
}

// providerAliases map models.dev provider ids onto the names our scanners
// record in a turn's Provider field, so provider-keyed lookups actually hit.
var providerAliases = map[string]string{
	"fireworks-ai":            "fireworks",
	"together-ai":             "together",
	"moonshotai":              "moonshot",
	"zhipuai":                 "z.ai",
	"google-vertex-anthropic": "vertex-anthropic",
}

// --- models.dev wire format -------------------------------------------------

type mdCost struct {
	Input      *float64 `json:"input"`
	Output     *float64 `json:"output"`
	CacheRead  *float64 `json:"cache_read"`
	CacheWrite *float64 `json:"cache_write"`
	Tiers      []mdTier `json:"tiers"`
}

type mdTier struct {
	Input      *float64 `json:"input"`
	Output     *float64 `json:"output"`
	CacheRead  *float64 `json:"cache_read"`
	CacheWrite *float64 `json:"cache_write"`
	Tier       struct {
		Type string `json:"type"`
		Size int64  `json:"size"`
	} `json:"tier"`
}

type mdModel struct {
	ID   string  `json:"id"`
	Cost *mdCost `json:"cost"`
}

type mdProvider struct {
	ID     string             `json:"id"`
	Models map[string]mdModel `json:"models"`
}

// --- output format ----------------------------------------------------------

type dataset struct {
	Schema     int                       `json:"schema"`
	Updated    pricing.Date              `json:"updated"`
	Sources    []string                  `json:"sources,omitempty"`
	Models     map[string]*pricing.Model `json:"models"`
	ByProvider map[string]*pricing.Model `json:"by_provider,omitempty"`
	Aliases    map[string]string         `json:"aliases,omitempty"`
}

// Sanity bounds in USD per 1M tokens. Anything outside is a units bug upstream
// (per-1K quoted as per-1M, say) and is dropped rather than shipped.
const (
	minRate = 0.0
	maxRate = 10_000.0
)

func main() {
	var (
		out       = flag.String("out", "internal/pricing/data/pricing.json", "dataset path to write")
		src       = flag.String("source", modelsDevURL, "models.dev API url, or a local file path for offline runs")
		asOf      = flag.String("as-of", "", "effective date to stamp new rates with (default: today)")
		dryRun    = flag.Bool("dry-run", false, "report what would change without writing")
		backfillF = flag.String("backfill", "", "schema-1 pricing_data.json to date-stamp existing rates from (implies -as-of, skips the network)")
	)
	flag.Parse()

	effective := pricing.DateOf(time.Now())
	if *asOf != "" {
		d, err := pricing.ParseDate(*asOf)
		if err != nil {
			fatal("bad -as-of %q: %v", *asOf, err)
		}
		effective = d
	}

	// Backfill mode works purely on the committed dataset plus an old snapshot;
	// it never touches the network and never introduces a rate.
	if *backfillF != "" {
		if *asOf == "" {
			fatal("-backfill requires -as-of YYYY-MM-DD (the snapshot's date)")
		}
		ds := readExisting(*out)
		if ds == nil {
			fatal("could not read the existing dataset at %s", *out)
		}
		moved, rejected, ambiguous, err := backfill(ds, *backfillF, effective)
		if err != nil {
			fatal("%v", err)
		}
		fmt.Printf("backfill from %s (as of %s)\n", *backfillF, effective)
		fmt.Printf("  %d rates dated back to %s (snapshot agrees with the current first-party rate)\n", moved, effective)
		fmt.Printf("  %d rejected as reseller prices the old alphabetical sync mistakenly recorded\n", rejected)
		fmt.Printf("  %d left alone as ambiguous\n", ambiguous)
		if *dryRun {
			fmt.Println("\n(dry run — nothing written)")
			return
		}
		if err := write(*out, ds); err != nil {
			fatal("write %s: %v", *out, err)
		}
		fmt.Printf("\nWrote %s\n", *out)
		return
	}

	raw, err := fetch(*src)
	if err != nil {
		fatal("%v", err)
	}
	var providers map[string]mdProvider
	if err := json.Unmarshal(raw, &providers); err != nil {
		fatal("models.dev returned invalid JSON: %v", err)
	}
	if len(providers) == 0 {
		fatal("models.dev returned an empty payload; refusing to overwrite the dataset")
	}

	next := build(providers, effective)
	if len(next.Models) == 0 {
		fatal("transformed dataset is empty; refusing to overwrite the dataset")
	}

	prev := readExisting(*out)
	changes := merge(prev, next, effective)

	report(changes)
	if *dryRun {
		fmt.Println("\n(dry run — nothing written)")
		return
	}
	if err := write(*out, next); err != nil {
		fatal("write %s: %v", *out, err)
	}
	fmt.Printf("\nWrote %s — %d models, %d provider-keyed, %d aliases (effective %s)\n",
		*out, len(next.Models), len(next.ByProvider), len(next.Aliases), effective)
}

func fetch(src string) ([]byte, error) {
	if !strings.HasPrefix(src, "http://") && !strings.HasPrefix(src, "https://") {
		return os.ReadFile(src)
	}
	req, err := http.NewRequest("GET", src, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", "tokentelemetry-pricing-sync")
	client := &http.Client{Timeout: 60 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("could not reach %s: %w (this tool is maintainer-only and needs network access; the existing dataset is untouched)", src, err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("%s returned HTTP %d", src, resp.StatusCode)
	}
	return io.ReadAll(io.LimitReader(resp.Body, 64<<20))
}

// candidate tracks the best provider seen so far for one model id.
type candidate struct {
	tier, rank int
	provider   string
	rate       pricing.Rate
}

func build(providers map[string]mdProvider, effective pricing.Date) *dataset {
	ds := &dataset{
		Schema:     pricing.SchemaVersion,
		Updated:    effective,
		Sources:    []string{modelsDevURL},
		Models:     map[string]*pricing.Model{},
		ByProvider: map[string]*pricing.Model{},
		Aliases:    map[string]string{},
	}
	best := map[string]candidate{}

	// Sorted iteration keeps output deterministic; correctness comes from the
	// ranking, never from iteration order.
	provIDs := make([]string, 0, len(providers))
	for id := range providers {
		provIDs = append(provIDs, id)
	}
	sort.Strings(provIDs)

	for _, provID := range provIDs {
		prov := providers[provID]
		modelIDs := make([]string, 0, len(prov.Models))
		for id := range prov.Models {
			modelIDs = append(modelIDs, id)
		}
		sort.Strings(modelIDs)

		for _, modelID := range modelIDs {
			m := prov.Models[modelID]
			if m.Cost == nil {
				continue
			}
			id := pricing.Normalize(modelID)
			if id == "" {
				continue
			}
			rate, ok := toRate(*m.Cost, id, provID, effective)
			if !ok {
				continue
			}

			// Provider-keyed entry: always recorded, so a scanner that knows
			// the route gets the real (marked-up or discounted) price.
			key := providerLookupKey(provID, id)
			ds.ByProvider[key] = &pricing.Model{ID: id, Rates: []pricing.Rate{rate}}

			tier, rank := rankOf(provID)
			if cur, seen := best[id]; !seen || better(tier, rank, cur.tier, cur.rank) {
				best[id] = candidate{tier: tier, rank: rank, provider: provID, rate: rate}
			}
		}
	}

	for id, c := range best {
		ds.Models[id] = &pricing.Model{
			ID:         id,
			Rates:      []pricing.Rate{c.rate},
			FirstParty: c.tier == 0,
		}
	}
	buildAliases(ds)
	return ds
}

func toRate(c mdCost, modelID, provID string, effective pricing.Date) (pricing.Rate, bool) {
	in, okIn := sane(c.Input)
	out, okOut := sane(c.Output)
	if !okIn && !okOut {
		return pricing.Rate{}, false
	}
	r := pricing.Rate{From: effective, In: in, Out: out, Source: provID}
	if v, ok := sane(c.CacheRead); ok {
		r.CacheRead = v
	}

	anthropicFamily := provID == "anthropic" || strings.HasPrefix(modelID, "claude")
	if v, ok := sane(c.CacheWrite); ok {
		r.CacheWrite = v
	} else if anthropicFamily {
		// Anthropic bills a 5-minute cache write at 1.25x input. Applied only
		// to Anthropic; the old code applied it to every provider.
		r.CacheWrite = in * 1.25
	} else {
		r.CacheWrite = in
	}
	if anthropicFamily {
		r.CacheWrite1h = in * 2.0
	}

	// Long-context tier. Providers express it as a tiers[] entry keyed on
	// prompt size; the surcharge is real money on agent workloads, which run
	// enormous prompts, and the previous implementation ignored it entirely.
	for _, t := range c.Tiers {
		if t.Tier.Type != "context" || t.Tier.Size <= 0 {
			continue
		}
		ti, okTi := sane(t.Input)
		to, okTo := sane(t.Output)
		if !okTi && !okTo {
			continue
		}
		r.TierThreshold = t.Tier.Size
		r.TierIn, r.TierOut = ti, to
		if v, ok := sane(t.CacheRead); ok {
			r.TierCacheRead = v
		}
		if v, ok := sane(t.CacheWrite); ok {
			r.TierCacheWrite = v
		} else if anthropicFamily {
			r.TierCacheWrite = ti * 1.25
		} else {
			r.TierCacheWrite = ti
		}
		break
	}
	return r, true
}

func sane(v *float64) (float64, bool) {
	if v == nil {
		return 0, false
	}
	f := *v
	if f < minRate || f > maxRate {
		return 0, false
	}
	return f, true
}

func providerLookupKey(provID, modelID string) string {
	name := provID
	if alias, ok := providerAliases[provID]; ok {
		name = alias
	}
	return strings.ToLower(name) + "\x00" + modelID
}

// buildAliases maps the id spellings agents actually emit onto canonical ids.
// This replaces the old substring fallback, which matched the key "auto" inside
// "codex-auto-review" and billed it at Claude Sonnet rates. An alias is an
// explicit equivalence; a substring match is a guess.
func buildAliases(ds *dataset) {
	add := func(from, to string) {
		if from == "" || from == to {
			return
		}
		if _, taken := ds.Models[from]; taken {
			return // never shadow a real model
		}
		if _, dup := ds.Aliases[from]; dup {
			return
		}
		ds.Aliases[from] = to
	}
	for id := range ds.Models {
		// Version separator variants: agents emit claude-haiku-4.5 where the
		// canonical id is claude-haiku-4-5, and Fireworks writes kimi-k2p6 for
		// kimi-k2.6.
		if strings.Contains(id, ".") {
			add(strings.ReplaceAll(id, ".", "-"), id)
			add(strings.ReplaceAll(id, ".", "p"), id)
		}
		add(id+"-latest", id)
	}
	// Hand-curated equivalences that no rule derives.
	for from, to := range map[string]string{
		"claude-3.5-sonnet": "claude-3-5-sonnet",
		"claude-3.5-haiku":  "claude-3-5-haiku",
		"grok-code-fast":    "grok-code-fast-1",
	} {
		if _, ok := ds.Models[to]; ok {
			add(from, to)
		}
	}
}

// --- merge ------------------------------------------------------------------

type change struct {
	model    string
	kind     string // "new", "changed", "source"
	from, to string
}

func readExisting(path string) *dataset {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil
	}
	var ds dataset
	if err := json.Unmarshal(raw, &ds); err != nil {
		return nil
	}
	return &ds
}

// merge carries prior rate history into the freshly built dataset. A rate that
// matches the most recent known one is not re-recorded; a rate that differs is
// appended with the new effective date, which is what makes a price cut
// visible as an event rather than a silent overwrite.
func merge(prev, next *dataset, effective pricing.Date) []change {
	var changes []change
	if prev == nil {
		for id := range next.Models {
			changes = append(changes, change{model: id, kind: "new"})
		}
		return changes
	}
	for id, nm := range next.Models {
		pm, ok := prev.Models[id]
		if !ok || len(pm.Rates) == 0 {
			changes = append(changes, change{model: id, kind: "new"})
			continue
		}
		latest := pm.Rates[len(pm.Rates)-1]
		fresh := nm.Rates[0]
		if sameRate(latest, fresh) {
			// Unchanged: keep the original history untouched, including the
			// date the rate first took effect.
			nm.Rates = pm.Rates
			continue
		}
		fresh.From = effective
		nm.Rates = append(append([]pricing.Rate{}, pm.Rates...), fresh)
		changes = append(changes, change{
			model: id, kind: "changed",
			from: fmt.Sprintf("$%.4g/$%.4g", latest.In, latest.Out),
			to:   fmt.Sprintf("$%.4g/$%.4g", fresh.In, fresh.Out),
		})
	}
	// Models that vanished upstream keep their history so old usage stays
	// priced; they simply stop receiving new rates.
	for id, pm := range prev.Models {
		if _, ok := next.Models[id]; !ok {
			next.Models[id] = pm
		}
	}
	return changes
}

func sameRate(a, b pricing.Rate) bool {
	return a.In == b.In && a.Out == b.Out &&
		a.CacheRead == b.CacheRead && a.CacheWrite == b.CacheWrite &&
		a.CacheWrite1h == b.CacheWrite1h &&
		a.TierThreshold == b.TierThreshold && a.TierIn == b.TierIn && a.TierOut == b.TierOut
}

func report(changes []change) {
	var added, changed int
	var changedList []change
	for _, c := range changes {
		switch c.kind {
		case "new":
			added++
		case "changed":
			changed++
			changedList = append(changedList, c)
		}
	}
	fmt.Printf("%d new models, %d price changes\n", added, changed)
	sort.Slice(changedList, func(i, j int) bool { return changedList[i].model < changedList[j].model })
	for _, c := range changedList {
		fmt.Printf("  ~ %-34s %s -> %s\n", c.model, c.from, c.to)
	}
}

func write(path string, ds *dataset) error {
	if err := os.MkdirAll(dirOf(path), 0o755); err != nil {
		return err
	}
	buf, err := json.MarshalIndent(ds, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, append(buf, '\n'), 0o644)
}

func dirOf(p string) string {
	if i := strings.LastIndexByte(p, '/'); i > 0 {
		return p[:i]
	}
	return "."
}

func fatal(format string, args ...any) {
	fmt.Fprintf(os.Stderr, "pricing-sync: "+format+"\n", args...)
	os.Exit(1)
}
