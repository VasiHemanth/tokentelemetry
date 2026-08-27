package ingest

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"time"

	"github.com/VasiHemanth/tokentelemetry/engine/internal/model"
)

// Claude scans Claude Code transcripts.
//
// Layout is ~/.claude/projects/<url-encoded-cwd>/<session-uuid>.jsonl, one JSON
// object per line, plus delegated work under
// <project>/<session>/subagents/agent-<id>.jsonl.
//
// The critical detail is that these files are not append-only histories of
// distinct calls. Resuming, forking or compacting a session copies earlier
// assistant messages into the new transcript verbatim, so the same API call
// appears in several files. Anthropic stamps each call with a stable
// message id and request id, and the pair survives the copy — which is what
// makes deduplication possible at all.
type Claude struct {
	root string
}

func NewClaude() *Claude {
	return &Claude{root: envDir("CLAUDE_CONFIG_DIR", ".claude")}
}

func (c *Claude) Agent() model.Agent { return model.AgentClaude }

func (c *Claude) Roots() []string {
	if c.root == "" {
		return nil
	}
	if d := existingDir(filepath.Join(c.root, "projects")); d != "" {
		return []string{d}
	}
	return nil
}

// claudeRecord is the subset of a transcript line we care about. Decoding a
// narrow struct rather than a map avoids allocating the enormous content
// blocks, which dominate these files.
type claudeRecord struct {
	Type        string `json:"type"`
	Timestamp   string `json:"timestamp"`
	RequestID   string `json:"requestId"`
	SessionID   string `json:"sessionId"`
	CWD         string `json:"cwd"`
	IsSidechain bool   `json:"isSidechain"`
	Message     struct {
		ID    string `json:"id"`
		Model string `json:"model"`
		Usage struct {
			Input         int64  `json:"input_tokens"`
			Output        int64  `json:"output_tokens"`
			CacheRead     int64  `json:"cache_read_input_tokens"`
			CacheCreate   int64  `json:"cache_creation_input_tokens"`
			ServiceTier   string `json:"service_tier"`
			CacheCreation struct {
				Ephemeral1h int64 `json:"ephemeral_1h_input_tokens"`
			} `json:"cache_creation"`
		} `json:"usage"`
	} `json:"message"`
}

func (c *Claude) Scan(ctx context.Context, emit func(model.Turn)) error {
	roots := c.Roots()
	if len(roots) == 0 {
		return nil
	}
	projects := roots[0]

	entries, err := os.ReadDir(projects)
	if err != nil {
		return err
	}
	// Collect every path first, then read them in parallel. Transcripts sit
	// directly in the project dir; delegated subagent transcripts sit one level
	// deeper. Both are real spend.
	var paths []string
	var subagentPath = map[string]bool{}
	for _, e := range entries {
		if err := ctx.Err(); err != nil {
			return err
		}
		if !e.IsDir() {
			continue
		}
		dir := filepath.Join(projects, e.Name())
		for _, p := range globJSONL(filepath.Join(dir, "*.jsonl")) {
			paths = append(paths, p)
		}
		for _, p := range c.subagentFiles(dir) {
			paths = append(paths, p)
			subagentPath[p] = true
		}
	}
	turns := mapFiles(ctx, paths, func(path string) []model.Turn {
		return c.scanFile(path, subagentPath[path])
	})
	for _, t := range turns {
		emit(t)
	}
	return nil
}

func globJSONL(pattern string) []string {
	matches, err := filepath.Glob(pattern)
	if err != nil {
		return nil
	}
	return matches
}

// subagentFiles lists <project>/<session-id>/subagents/agent-*.jsonl. These are
// separate API conversations spawned by delegation and are billed separately,
// so they are counted — they are not a duplicate view of the parent.
func (c *Claude) subagentFiles(dir string) []string {
	sessions, err := os.ReadDir(dir)
	if err != nil {
		return nil
	}
	var out []string
	for _, s := range sessions {
		if !s.IsDir() {
			continue
		}
		sub := filepath.Join(dir, s.Name(), "subagents")
		if existingDir(sub) == "" {
			continue
		}
		out = append(out, globJSONL(filepath.Join(sub, "agent-*.jsonl"))...)
	}
	return out
}

func (c *Claude) scanFile(path string, subagent bool) []model.Turn {
	f, err := os.Open(path)
	if err != nil {
		return nil
	}
	defer f.Close()

	var turns []model.Turn

	for line := range jsonLines(f) {
		var r claudeRecord
		if err := json.Unmarshal(line, &r); err != nil {
			continue // a truncated tail line is normal on a live session
		}
		if r.Type != "assistant" {
			continue
		}
		u := r.Message.Usage
		usage := model.Usage{
			Input:        u.Input,
			Output:       u.Output,
			CacheRead:    u.CacheRead,
			CacheWrite:   u.CacheCreate,
			CacheWrite1h: u.CacheCreation.Ephemeral1h,
		}
		usage, ok := usage.Sanitize()
		if !ok || usage.IsZero() {
			continue // corrupt or empty record
		}
		// "<synthetic>" marks messages Claude Code fabricates locally (error
		// placeholders, interrupts). They carry no real usage.
		if r.Message.Model == "" || r.Message.Model == "<synthetic>" {
			continue
		}

		ts := parseTime(r.Timestamp)
		turns = append(turns, model.Turn{
			Key:       claudeKey(r.Message.ID, r.RequestID),
			SessionID: r.SessionID,
			Agent:     model.AgentClaude,
			Timestamp: ts,
			Model:     r.Message.Model,
			// Claude Code talks to Anthropic directly; recording it makes the
			// provider a groupable dimension and lets provider-keyed pricing hit.
			Provider:    "anthropic",
			Project:     r.CWD,
			Usage:       usage,
			ServiceTier: u.ServiceTier,
			Subagent:    subagent || r.IsSidechain,
		})
	}
	return turns
}

// claudeKey identifies one API call across every transcript that replays it.
//
// message.id alone is not enough: Claude Code reuses an id across the streaming
// retries of a single logical turn, and a retry is a separate billable call.
// requestId alone is not enough either, because it is absent on older records.
// The pair is stable and unique.
func claudeKey(messageID, requestID string) string {
	if messageID == "" && requestID == "" {
		return "" // unkeyed: counted, never deduped
	}
	return "claude|" + messageID + "|" + requestID
}

func parseTime(s string) time.Time {
	if s == "" {
		return time.Time{}
	}
	if t, err := time.Parse(time.RFC3339Nano, s); err == nil {
		return t
	}
	if t, err := time.Parse(time.RFC3339, s); err == nil {
		return t
	}
	return time.Time{}
}
