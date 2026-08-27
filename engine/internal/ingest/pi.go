package ingest

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"

	"github.com/VasiHemanth/tokentelemetry/engine/internal/model"
)

// Pi scans the Pi agent's session transcripts.
//
// Layout is ~/.pi/agent/sessions/<encoded-cwd>/<timestamp>_<uuid>.jsonl, one
// JSON object per line. Assistant turns carry provider, model and a usage block
// with cache reads and writes broken out separately, so no reconstruction is
// needed.
//
// The directory name is the working directory with path separators escaped,
// which is decoded back into a real path for project grouping.
type Pi struct {
	root string
}

func NewPi() *Pi {
	home := homeDir()
	if home == "" {
		return &Pi{}
	}
	return &Pi{root: existingDir(filepath.Join(home, ".pi", "agent", "sessions"))}
}

func (p *Pi) Agent() model.Agent { return model.AgentPi }

func (p *Pi) Roots() []string {
	if p.root == "" {
		return nil
	}
	return []string{p.root}
}

type piRecord struct {
	Type      string `json:"type"`
	ID        string `json:"id"`
	Timestamp string `json:"timestamp"`
	Message   struct {
		Role     string `json:"role"`
		Provider string `json:"provider"`
		Model    string `json:"model"`
		Usage    *struct {
			Input      int64 `json:"input"`
			Output     int64 `json:"output"`
			CacheRead  int64 `json:"cacheRead"`
			CacheWrite int64 `json:"cacheWrite"`
		} `json:"usage"`
	} `json:"message"`
}

func (p *Pi) Scan(ctx context.Context, emit func(model.Turn)) error {
	if p.root == "" {
		return nil
	}
	dirs, err := os.ReadDir(p.root)
	if err != nil {
		return err
	}
	var paths []string
	for _, d := range dirs {
		if !d.IsDir() {
			continue
		}
		paths = append(paths, globJSONL(filepath.Join(p.root, d.Name(), "*.jsonl"))...)
	}
	for _, t := range mapFiles(ctx, paths, p.scanFile) {
		emit(t)
	}
	return nil
}

func (p *Pi) scanFile(path string) []model.Turn {
	f, err := os.Open(path)
	if err != nil {
		return nil
	}
	defer f.Close()

	sessionID := strings.TrimSuffix(filepath.Base(path), ".jsonl")
	if i := strings.LastIndex(sessionID, "_"); i >= 0 {
		sessionID = sessionID[i+1:]
	}
	project := decodePiDir(filepath.Base(filepath.Dir(path)))

	var turns []model.Turn
	for line := range jsonLines(f) {
		var r piRecord
		if err := json.Unmarshal(line, &r); err != nil {
			continue
		}
		if r.Type != "message" || r.Message.Role != "assistant" || r.Message.Usage == nil {
			continue
		}
		u := r.Message.Usage
		usage := model.Usage{
			Input: u.Input, Output: u.Output,
			CacheRead: u.CacheRead, CacheWrite: u.CacheWrite,
		}
		usage, ok := usage.Sanitize()
		if !ok || usage.IsZero() || r.Message.Model == "" {
			continue
		}
		turns = append(turns, model.Turn{
			Key:       "pi|" + sessionID + "|" + r.ID,
			SessionID: sessionID,
			Agent:     model.AgentPi,
			Timestamp: parseTime(r.Timestamp),
			Model:     r.Message.Model,
			Provider:  r.Message.Provider,
			Project:   project,
			Usage:     usage,
		})
	}
	return turns
}

// decodePiDir turns Pi's escaped directory name back into a path.
// "--home-semyon--" encodes "/home/semyon/".
func decodePiDir(name string) string {
	if name == "" {
		return ""
	}
	return strings.ReplaceAll(name, "-", "/")
}
