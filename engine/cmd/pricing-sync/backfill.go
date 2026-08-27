package main

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"sort"

	"github.com/VasiHemanth/tokentelemetry/engine/internal/pricing"
)

// legacyFile is the schema-1 dataset the Python implementation shipped: a flat
// model→rate map with no time dimension.
type legacyFile struct {
	Updated    string                `json:"updated"`
	Pricing    map[string]legacyRate `json:"pricing"`
	ByProvider map[string]legacyRate `json:"by_provider"`
}

type legacyRate struct {
	In         *float64 `json:"in"`
	Out        *float64 `json:"out"`
	CachedRead *float64 `json:"cached_read"`
}

// backfill extends the earliest known rate of each model backwards to asOf,
// using an old snapshot as evidence that the price was already in force then.
//
// This needs care, because those snapshots were themselves produced by the
// alphabetical-provider bug and frequently record a RESELLER's price rather
// than the vendor's. Importing them wholesale would write the very error this
// rewrite exists to remove — a snapshot from 2026-08-10 lists gpt-5.6-luna at
// $1.00/$6.00, which was ai-router's price, not OpenAI's $0.20/$1.20.
//
// So a snapshot is only ever used to move a date, never to introduce a rate:
//
//   - snapshot agrees with the current first-party rate → the price was already
//     this on that date, so the effective date moves back. Safe and useful: it
//     shrinks the "priced at a rate newer than the call" caveat.
//   - snapshot matches some provider's CURRENT price for that model → almost
//     certainly the reseller the old sync mistakenly picked, not history.
//     Discarded.
//   - anything else is genuinely ambiguous: either a real past price or a
//     reseller who has since moved. Discarded, because a wrong date is worse
//     than an honest "unknown".
func backfill(ds *dataset, path string, asOf pricing.Date) (moved, rejected, ambiguous int, err error) {
	raw, readErr := os.ReadFile(path)
	if readErr != nil {
		return 0, 0, 0, readErr
	}
	var lf legacyFile
	if jsonErr := json.Unmarshal(raw, &lf); jsonErr != nil {
		return 0, 0, 0, fmt.Errorf("%s is not a schema-1 pricing file: %w", path, jsonErr)
	}
	if len(lf.Pricing) == 0 {
		return 0, 0, 0, fmt.Errorf("%s contains no pricing entries", path)
	}

	// Index every provider's current price per model, to recognise a reseller
	// figure masquerading as history.
	resellerRates := map[string][][2]float64{}
	for key, m := range ds.ByProvider {
		if len(m.Rates) == 0 {
			continue
		}
		id := key
		if i := indexByte(key, 0); i >= 0 {
			id = key[i+1:]
		}
		r := m.Rates[len(m.Rates)-1]
		resellerRates[id] = append(resellerRates[id], [2]float64{r.In, r.Out})
	}

	// Sorted iteration keeps the reported counts reproducible. The dataset that
	// results is order-independent either way, because a snapshot can only move
	// a date backwards and only once — but this file is committed, so a stable
	// run-to-run report matters for reviewing the diff.
	ids := make([]string, 0, len(lf.Pricing))
	for k := range lf.Pricing {
		ids = append(ids, k)
	}
	sort.Strings(ids)

	for _, rawID := range ids {
		lr := lf.Pricing[rawID]
		if lr.In == nil && lr.Out == nil {
			continue
		}
		id := pricing.Normalize(rawID)
		m, ok := ds.Models[id]
		if !ok || len(m.Rates) == 0 {
			continue
		}
		earliest := &m.Rates[0]
		// Never move a date forward, and never disturb a series that already
		// records a change at or before this snapshot.
		if !earliest.From.After(asOf) {
			continue
		}

		legacyIn, legacyOut := deref(lr.In), deref(lr.Out)
		if sameMoney(legacyIn, earliest.In) && sameMoney(legacyOut, earliest.Out) {
			earliest.From = asOf
			moved++
			continue
		}
		if matchesAnyProvider(resellerRates[id], legacyIn, legacyOut) {
			rejected++
			continue
		}
		ambiguous++
	}
	return moved, rejected, ambiguous, nil
}

func matchesAnyProvider(rates [][2]float64, in, out float64) bool {
	for _, r := range rates {
		if sameMoney(r[0], in) && sameMoney(r[1], out) {
			return true
		}
	}
	return false
}

// sameMoney compares per-million rates with a tolerance well below a cent, so
// float round-tripping through JSON cannot register as a price change.
func sameMoney(a, b float64) bool { return math.Abs(a-b) < 1e-6 }

func deref(p *float64) float64 {
	if p == nil {
		return 0
	}
	return *p
}

func indexByte(s string, b byte) int {
	for i := 0; i < len(s); i++ {
		if s[i] == b {
			return i
		}
	}
	return -1
}
