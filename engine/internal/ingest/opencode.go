package ingest

import (
	"context"
	"database/sql"
	"encoding/json"
	"os"
	"path/filepath"
	"time"

	"github.com/VasiHemanth/tokentelemetry/engine/internal/model"
)

// OpenCode scans the OpenCode CLI's SQLite store.
//
// Layout is ~/.local/share/opencode/opencode.db, with a `message` row per turn
// whose `data` column holds the JSON payload — including per-message token
// counts and the model that served it. That makes this the most precise of the
// SQLite-backed agents: unlike Hermes, the per-call detail survives, so turns
// carry their own clock and bucket into the correct local day.
//
// Token counts here are already NET of cache: the payload's total equals
// input + output + cache.read, so input must not be reduced again.
type OpenCode struct {
	dbPath string
}

func NewOpenCode() *OpenCode {
	// XDG first, then the legacy location the older builds used.
	var candidates []string
	if x := os.Getenv("XDG_DATA_HOME"); x != "" {
		candidates = append(candidates, filepath.Join(x, "opencode", "opencode.db"))
	}
	if home := homeDir(); home != "" {
		candidates = append(candidates,
			filepath.Join(home, ".local", "share", "opencode", "opencode.db"),
			filepath.Join(home, ".opencode", "opencode.db"))
	}
	for _, c := range candidates {
		if fileExists(c) {
			return &OpenCode{dbPath: c}
		}
	}
	return &OpenCode{}
}

func (o *OpenCode) Agent() model.Agent { return model.AgentOpenCode }

func (o *OpenCode) Roots() []string {
	if o.dbPath == "" {
		return nil
	}
	return []string{o.dbPath}
}

// openCodeMessage is the subset of the JSON payload we need.
type openCodeMessage struct {
	Role       string `json:"role"`
	ModelID    string `json:"modelID"`
	ProviderID string `json:"providerID"`
	Tokens     struct {
		Input     int64 `json:"input"`
		Output    int64 `json:"output"`
		Reasoning int64 `json:"reasoning"`
		Cache     struct {
			Read  int64 `json:"read"`
			Write int64 `json:"write"`
		} `json:"cache"`
	} `json:"tokens"`
	Time struct {
		Created   int64 `json:"created"`
		Completed int64 `json:"completed"`
	} `json:"time"`
}

const openCodeQuery = `
SELECT m.id, m.session_id, CAST(m.time_created AS INTEGER), m.data,
       COALESCE(s.directory, '')
FROM message m
LEFT JOIN session s ON s.id = m.session_id
`

func (o *OpenCode) Scan(ctx context.Context, emit func(model.Turn)) error {
	if o.dbPath == "" {
		return nil
	}
	db, err := sql.Open("sqlite", "file:"+o.dbPath+"?mode=ro&_pragma=busy_timeout(3000)")
	if err != nil {
		return nil
	}
	defer db.Close()

	rows, err := db.QueryContext(ctx, openCodeQuery)
	if err != nil {
		return nil
	}
	defer rows.Close()

	for rows.Next() {
		var (
			id, sessionID, data, dir string
			created                  int64
		)
		if err := rows.Scan(&id, &sessionID, &created, &data, &dir); err != nil {
			continue
		}
		var m openCodeMessage
		if err := json.Unmarshal([]byte(data), &m); err != nil {
			continue
		}
		if m.Role != "assistant" || m.ModelID == "" {
			continue
		}
		usage := model.Usage{
			Input:      m.Tokens.Input,
			Output:     m.Tokens.Output,
			CacheRead:  m.Tokens.Cache.Read,
			CacheWrite: m.Tokens.Cache.Write,
			Reasoning:  m.Tokens.Reasoning,
		}
		usage, ok := usage.Sanitize()
		if !ok || usage.IsZero() {
			continue
		}
		// Prefer the payload's own clock; fall back to the row's.
		ts := m.Time.Created
		if ts == 0 {
			ts = created
		}
		emit(model.Turn{
			Key:       "opencode|" + id,
			SessionID: sessionID,
			Agent:     model.AgentOpenCode,
			Timestamp: unixMillis(ts),
			Model:     m.ModelID,
			Provider:  m.ProviderID,
			Project:   dir,
			Usage:     usage,
		})
	}
	return nil
}

// unixMillis converts JavaScript-style epoch milliseconds to a time.
func unixMillis(ms int64) time.Time {
	if ms <= 0 {
		return time.Time{}
	}
	return time.UnixMilli(ms)
}
