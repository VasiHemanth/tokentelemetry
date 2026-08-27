package ingest

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"

	"github.com/VasiHemanth/tokentelemetry/engine/internal/model"
)

// Gemini scans Gemini CLI chat sessions.
//
// Layout is ~/.gemini/tmp/<project-hash>/chats/session-*.json — a single JSON
// document per session with a messages array. Assistant turns have type
// "gemini" and carry their own token block and model, so turns keep per-call
// timestamps and per-call model attribution.
//
// The project is only recorded as an opaque hash of its path, so sessions
// group correctly but cannot be labelled with a real directory.
type Gemini struct {
	root string
}

func NewGemini() *Gemini {
	return &Gemini{root: envDir("GEMINI_CONFIG_DIR", ".gemini")}
}

func (g *Gemini) Agent() model.Agent { return model.AgentGemini }

func (g *Gemini) Roots() []string {
	if g.root == "" {
		return nil
	}
	if d := existingDir(filepath.Join(g.root, "tmp")); d != "" {
		return []string{d}
	}
	return nil
}

type geminiSession struct {
	SessionID   string `json:"sessionId"`
	ProjectHash string `json:"projectHash"`
	Messages    []struct {
		Type      string `json:"type"`
		Timestamp string `json:"timestamp"`
		Model     string `json:"model"`
		Tokens    *struct {
			Input    int64 `json:"input"`
			Output   int64 `json:"output"`
			Cached   int64 `json:"cached"`
			Thoughts int64 `json:"thoughts"`
			Tool     int64 `json:"tool"`
			Total    int64 `json:"total"`
		} `json:"tokens"`
	} `json:"messages"`
}

func (g *Gemini) Scan(ctx context.Context, emit func(model.Turn)) error {
	roots := g.Roots()
	if len(roots) == 0 {
		return nil
	}
	projects, err := os.ReadDir(roots[0])
	if err != nil {
		return err
	}
	var paths []string
	for _, p := range projects {
		if !p.IsDir() {
			continue
		}
		paths = append(paths, globJSON(filepath.Join(roots[0], p.Name(), "chats", "session-*.json"))...)
	}
	for _, t := range mapFiles(ctx, paths, g.scanFile) {
		emit(t)
	}
	return nil
}

func (g *Gemini) scanFile(path string) []model.Turn {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil
	}
	var s geminiSession
	if err := json.Unmarshal(raw, &s); err != nil {
		return nil
	}
	var turns []model.Turn
	for i, m := range s.Messages {
		if m.Type != "gemini" || m.Tokens == nil || m.Model == "" {
			continue
		}
		// `input` is already exclusive of `cached`: the recorded total is
		// input + output + thoughts, with cached tracked alongside rather than
		// folded in. Reasoning ("thoughts") bills as output.
		usage := model.Usage{
			Input:     m.Tokens.Input,
			Output:    m.Tokens.Output + m.Tokens.Thoughts,
			CacheRead: m.Tokens.Cached,
			Reasoning: m.Tokens.Thoughts,
		}
		usage, ok := usage.Sanitize()
		if !ok || usage.IsZero() {
			continue
		}
		turns = append(turns, model.Turn{
			Key:       "gemini|" + s.SessionID + "|" + itoaInt(i),
			SessionID: s.SessionID,
			Agent:     model.AgentGemini,
			Timestamp: parseTime(m.Timestamp),
			Model:     m.Model,
			Provider:  "google",
			Usage:     usage,
		})
	}
	return turns
}

func globJSON(pattern string) []string {
	matches, err := filepath.Glob(pattern)
	if err != nil {
		return nil
	}
	return matches
}

func itoaInt(n int) string {
	if n == 0 {
		return "0"
	}
	var b []byte
	for n > 0 {
		b = append([]byte{byte('0' + n%10)}, b...)
		n /= 10
	}
	return string(b)
}
