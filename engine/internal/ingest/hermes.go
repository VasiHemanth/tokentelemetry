package ingest

import (
	"context"
	"database/sql"
	"os"
	"path/filepath"
	"time"

	_ "modernc.org/sqlite" // pure-Go driver: keeps CGO_ENABLED=0 cross-compiles working

	"github.com/VasiHemanth/tokentelemetry/engine/internal/model"
)

// Hermes scans the Nous Research Hermes agent's SQLite state.
//
// Unlike the file-based agents, Hermes keeps its own accounting in
// ~/.hermes/state.db (plus one per profile under profiles/<name>/state.db).
// The table that matters is session_model_usage: one row per (session, model)
// carrying token counts, the billing route, and first/last timestamps. That
// pre-aggregation is why this scanner emits a turn per row rather than per API
// call — the per-call detail is not recorded anywhere.
//
// The consequence is bucketing granularity: a row is attributed to the local
// day of its last_seen. A Hermes session that ran across midnight lands wholly
// on the day it finished, where a Claude or Codex session would split. Totals
// and per-model attribution are exact; only the day boundary is approximate.
type Hermes struct {
	root string
}

func NewHermes() *Hermes {
	return &Hermes{root: envDir("HERMES_HOME", ".hermes")}
}

func (h *Hermes) Agent() model.Agent { return model.AgentHermes }

// Roots lists every state.db: the default profile plus any named profiles.
func (h *Hermes) Roots() []string {
	if h.root == "" {
		return nil
	}
	var out []string
	if main := filepath.Join(h.root, "state.db"); fileExists(main) {
		out = append(out, main)
	}
	profiles, err := os.ReadDir(filepath.Join(h.root, "profiles"))
	if err == nil {
		for _, p := range profiles {
			if !p.IsDir() {
				continue
			}
			if db := filepath.Join(h.root, "profiles", p.Name(), "state.db"); fileExists(db) {
				out = append(out, db)
			}
		}
	}
	return out
}

func (h *Hermes) Scan(ctx context.Context, emit func(model.Turn)) error {
	for _, db := range h.Roots() {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		// One unreadable or mid-write database must not lose the others.
		for _, t := range h.scanDB(ctx, db) {
			emit(t)
		}
	}
	return nil
}

// hermesQuery reads per-model usage joined to its session for the working
// directory. Every numeric column is CAST because Hermes stores them as TEXT in
// places — SQLite's dynamic typing means a bare scan into int64 fails on rows
// written by an older build.
const hermesQuery = `
SELECT
  u.session_id,
  COALESCE(u.model, s.model, '')                        AS model,
  COALESCE(u.billing_provider, s.billing_provider, '')  AS provider,
  COALESCE(u.billing_base_url, s.billing_base_url, '')  AS endpoint,
  CAST(COALESCE(u.input_tokens, 0) AS INTEGER)          AS input_tokens,
  CAST(COALESCE(u.output_tokens, 0) AS INTEGER)         AS output_tokens,
  CAST(COALESCE(u.cache_read_tokens, 0) AS INTEGER)     AS cache_read,
  CAST(COALESCE(u.cache_write_tokens, 0) AS INTEGER)    AS cache_write,
  CAST(COALESCE(u.reasoning_tokens, 0) AS INTEGER)      AS reasoning,
  CAST(COALESCE(u.last_seen, u.first_seen, 0) AS REAL)  AS seen_at,
  COALESCE(s.cwd, '')                                   AS cwd,
  COALESCE(s.parent_session_id, '')                     AS parent_id
FROM session_model_usage u
LEFT JOIN sessions s ON s.id = u.session_id
`

func (h *Hermes) scanDB(ctx context.Context, path string) []model.Turn {
	// Read-only, and immutable=false so a live WAL is still read correctly.
	// A busy timeout keeps a concurrently-writing Hermes from failing the scan.
	dsn := "file:" + path + "?mode=ro&_pragma=busy_timeout(3000)"
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil
	}
	defer db.Close()

	rows, err := db.QueryContext(ctx, hermesQuery)
	if err != nil {
		return nil // schema older than session_model_usage, or db unreadable
	}
	defer rows.Close()

	var turns []model.Turn
	for rows.Next() {
		var (
			sessionID, modelID, provider, endpoint, cwd, parentID string
			in, out, cr, cw, reasoning                            int64
			seenAt                                                float64
		)
		if err := rows.Scan(&sessionID, &modelID, &provider, &endpoint,
			&in, &out, &cr, &cw, &reasoning, &seenAt, &cwd, &parentID); err != nil {
			continue
		}
		usage := model.Usage{
			Input: in, Output: out, CacheRead: cr, CacheWrite: cw, Reasoning: reasoning,
		}
		usage, ok := usage.Sanitize()
		if !ok || usage.IsZero() || modelID == "" {
			continue
		}
		turns = append(turns, model.Turn{
			Key:       "hermes|" + path + "|" + sessionID + "|" + modelID,
			SessionID: sessionID,
			Agent:     model.AgentHermes,
			Timestamp: unixFloat(seenAt),
			Model:     modelID,
			Provider:  provider,
			Endpoint:  endpoint,
			Project:   cwd,
			Usage:     usage,
			Subagent:  parentID != "",
		})
	}
	return turns
}

// unixFloat converts Hermes's fractional unix seconds to a time.
func unixFloat(v float64) time.Time {
	if v <= 0 {
		return time.Time{}
	}
	sec := int64(v)
	return time.Unix(sec, int64((v-float64(sec))*1e9))
}

func fileExists(p string) bool {
	fi, err := os.Stat(p)
	return err == nil && !fi.IsDir()
}
