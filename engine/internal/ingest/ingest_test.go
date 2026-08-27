package ingest

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/VasiHemanth/tokentelemetry/engine/internal/model"
)

func writeFile(t *testing.T, path string, lines ...string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(strings.Join(lines, "\n")+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
}

func scan(t *testing.T, s Scanner) []model.Turn {
	t.Helper()
	var turns []model.Turn
	if err := s.Scan(context.Background(), func(x model.Turn) { turns = append(turns, x) }); err != nil {
		t.Fatalf("scan: %v", err)
	}
	return turns
}

func totalOut(turns []model.Turn) int64 {
	var n int64
	for _, x := range turns {
		n += x.Usage.Output
	}
	return n
}

// --- Claude -----------------------------------------------------------------

func claudeLine(msgID, reqID, model, ts string, in, out, cr, cw int64) string {
	return `{"type":"assistant","timestamp":"` + ts + `","requestId":"` + reqID +
		`","sessionId":"s1","cwd":"/proj","message":{"id":"` + msgID + `","model":"` + model +
		`","usage":{"input_tokens":` + itoa(in) + `,"output_tokens":` + itoa(out) +
		`,"cache_read_input_tokens":` + itoa(cr) + `,"cache_creation_input_tokens":` + itoa(cw) + `}}}`
}

func itoa(n int64) string {
	if n == 0 {
		return "0"
	}
	var b []byte
	neg := n < 0
	if neg {
		n = -n
	}
	for n > 0 {
		b = append([]byte{byte('0' + n%10)}, b...)
		n /= 10
	}
	if neg {
		return "-" + string(b)
	}
	return string(b)
}

func newClaudeAt(root string) *Claude { return &Claude{root: root} }

// Resuming or forking a Claude session copies earlier assistant messages into
// the new transcript verbatim. Half of all assistant messages on the audited
// machine were such copies. They must be counted exactly once.
func TestClaudeDedupsReplayedCalls(t *testing.T) {
	root := t.TempDir()
	proj := filepath.Join(root, "projects", "-proj")

	original := claudeLine("msg_1", "req_1", "claude-opus-5", "2026-08-01T10:00:00Z", 10, 100, 1000, 50)
	second := claudeLine("msg_2", "req_2", "claude-opus-5", "2026-08-01T10:05:00Z", 20, 200, 2000, 60)
	// The resumed transcript replays msg_1 and then adds its own call.
	writeFile(t, filepath.Join(proj, "sessionA.jsonl"), original, second)
	writeFile(t, filepath.Join(proj, "sessionB.jsonl"), original, second,
		claudeLine("msg_3", "req_3", "claude-opus-5", "2026-08-01T11:00:00Z", 30, 300, 3000, 70))

	res, err := Run(context.Background(), []Scanner{newClaudeAt(root)})
	if err != nil {
		t.Fatal(err)
	}
	if got, want := len(res.Turns), 3; got != want {
		t.Fatalf("kept %d turns, want %d", got, want)
	}
	if got, want := res.Duplicates, 2; got != want {
		t.Errorf("dropped %d duplicates, want %d", got, want)
	}
	if got, want := totalOut(res.Turns), int64(600); got != want {
		t.Errorf("output = %d, want %d", got, want)
	}
}

// A retry of the same logical message is a separate billable call, and Claude
// Code reuses message.id across retries. Only the pair is unique.
func TestClaudeKeyUsesBothIDs(t *testing.T) {
	root := t.TempDir()
	proj := filepath.Join(root, "projects", "-proj")
	writeFile(t, filepath.Join(proj, "s.jsonl"),
		claudeLine("msg_1", "req_1", "claude-opus-5", "2026-08-01T10:00:00Z", 1, 10, 0, 0),
		claudeLine("msg_1", "req_2", "claude-opus-5", "2026-08-01T10:00:05Z", 1, 10, 0, 0),
	)
	res, _ := Run(context.Background(), []Scanner{newClaudeAt(root)})
	if len(res.Turns) != 2 {
		t.Errorf("kept %d turns, want 2 (a retry is a separate call)", len(res.Turns))
	}
}

// Locally fabricated messages carry no real usage.
func TestClaudeSkipsSynthetic(t *testing.T) {
	root := t.TempDir()
	proj := filepath.Join(root, "projects", "-proj")
	writeFile(t, filepath.Join(proj, "s.jsonl"),
		claudeLine("msg_1", "req_1", "<synthetic>", "2026-08-01T10:00:00Z", 5, 5, 0, 0),
		claudeLine("msg_2", "req_2", "claude-opus-5", "2026-08-01T10:01:00Z", 5, 5, 0, 0),
	)
	turns := scan(t, newClaudeAt(root))
	if len(turns) != 1 || turns[0].Model != "claude-opus-5" {
		t.Errorf("got %d turns %v, want 1 real turn", len(turns), turns)
	}
}

// Delegated subagent transcripts are separate conversations and real spend.
func TestClaudeCountsSubagents(t *testing.T) {
	root := t.TempDir()
	proj := filepath.Join(root, "projects", "-proj")
	writeFile(t, filepath.Join(proj, "s1.jsonl"),
		claudeLine("msg_1", "req_1", "claude-opus-5", "2026-08-01T10:00:00Z", 1, 100, 0, 0))
	writeFile(t, filepath.Join(proj, "s1", "subagents", "agent-a.jsonl"),
		claudeLine("msg_9", "req_9", "claude-opus-5", "2026-08-01T10:02:00Z", 1, 500, 0, 0))

	turns := scan(t, newClaudeAt(root))
	if got, want := totalOut(turns), int64(600); got != want {
		t.Fatalf("output = %d, want %d (subagent work must be counted)", got, want)
	}
	var sub int
	for _, x := range turns {
		if x.Subagent {
			sub++
		}
	}
	if sub != 1 {
		t.Errorf("marked %d turns as subagent, want 1", sub)
	}
}

// --- Codex ------------------------------------------------------------------

func newCodexAt(root string) *Codex { return &Codex{root: root} }

func codexMeta(id, parent, source, model string) string {
	p := `"id":"` + id + `","cwd":"/proj","model_provider":"openai","thread_source":"` + source + `"`
	if parent != "" {
		p += `,"parent_thread_id":"` + parent + `","forked_from_id":"` + parent + `"`
	}
	if model != "" {
		p += `,"model":"` + model + `"`
	}
	return `{"timestamp":"2026-08-01T10:00:00.000Z","type":"session_meta","payload":{` + p + `}}`
}

func codexTurnContext(model string) string {
	return `{"timestamp":"2026-08-01T10:00:01.000Z","type":"turn_context","payload":{"model":"` + model + `","cwd":"/proj"}}`
}

func codexTokens(ts string, in, cached, out int64) string {
	last := `{"input_tokens":` + itoa(in) + `,"cached_input_tokens":` + itoa(cached) +
		`,"cache_write_input_tokens":0,"output_tokens":` + itoa(out) + `,"reasoning_output_tokens":0}`
	return `{"timestamp":"` + ts + `","type":"event_msg","payload":{"type":"token_count","info":{` +
		`"total_token_usage":` + last + `,"last_token_usage":` + last + `}}}`
}

// Codex reports a GROSS input that already includes cached tokens. Failing to
// net it bills the cache twice — once at input rate, once at cache-read rate.
func TestCodexNetsGrossInput(t *testing.T) {
	root := t.TempDir()
	writeFile(t, filepath.Join(root, "sessions", "2026", "08", "01", "rollout-x-s1.jsonl"),
		codexMeta("s1", "", "user", "gpt-5.6-terra"),
		codexTokens("2026-08-01T10:00:02.000Z", 10_000, 8_000, 500),
	)
	turns := scan(t, newCodexAt(root))
	if len(turns) != 1 {
		t.Fatalf("got %d turns, want 1", len(turns))
	}
	u := turns[0].Usage
	if u.Input != 2_000 || u.CacheRead != 8_000 {
		t.Errorf("input/cacheRead = %d/%d, want 2000/8000", u.Input, u.CacheRead)
	}
	if u.ContextTokens != 10_000 {
		t.Errorf("context = %d, want the gross 10000 for tier pricing", u.ContextTokens)
	}
}

// A forked or subagent rollout replays the parent's whole history as a burst of
// token_count events sharing the fork timestamp. Counting them attributed 382M
// inherited tokens to each of 45 children and turned a $117 day into $3,790.
func TestCodexSkipsReplayedForkHistory(t *testing.T) {
	root := t.TempDir()
	fork := "2026-08-02T22:48:11.653Z"
	writeFile(t, filepath.Join(root, "sessions", "2026", "08", "02", "rollout-x-s2.jsonl"),
		codexMeta("s2", "s1", "subagent", "gpt-5.6-terra"),
		codexMeta("s1", "", "user", "gpt-5.6-terra"), // parent meta, written by the fork
		// Replayed parent history — all at the fork's timestamp.
		codexTokens(fork, 1_000, 0, 1_000),
		codexTokens(fork, 2_000, 0, 2_000),
		codexTokens(fork, 3_000, 0, 3_000),
		// This thread's own work.
		codexTokens("2026-08-02T22:53:00.000Z", 500, 0, 42),
	)
	turns := scan(t, newCodexAt(root))
	if got, want := totalOut(turns), int64(42); got != want {
		t.Errorf("output = %d, want %d (inherited history must not be counted)", got, want)
	}
	if len(turns) != 1 || !turns[0].Subagent {
		t.Errorf("got %d turns (subagent=%v), want 1 subagent turn", len(turns), turns[0].Subagent)
	}
}

// The replay burst does NOT share one timestamp. On the audited machine a
// 3,071-event replay spanned 125 distinct milliseconds, which defeated an
// equality check and let 1.12M inherited output tokens through. Detection must
// key on density, not on the timestamp string.
func TestCodexSkipsReplayWithDriftingTimestamps(t *testing.T) {
	root := t.TempDir()
	lines := []string{
		codexMeta("s7", "s1", "subagent", "gpt-5.6-terra"),
		codexMeta("s1", "", "user", "gpt-5.6-terra"),
	}
	// 200 replayed events drifting across ~200ms, exactly as Codex writes them.
	for i := range 200 {
		ts := time.Date(2026, 8, 2, 22, 48, 11, (650+i)*int(time.Millisecond), time.UTC)
		lines = append(lines, codexTokens(ts.Format("2006-01-02T15:04:05.000Z"), 1_000, 0, 1_000))
	}
	// The thread's own work, after a real pause.
	lines = append(lines, codexTokens("2026-08-02T22:53:00.000Z", 500, 0, 42))
	writeFile(t, filepath.Join(root, "sessions", "2026", "08", "02", "rollout-x-s7.jsonl"), lines...)

	turns := scan(t, newCodexAt(root))
	if got, want := totalOut(turns), int64(42); got != want {
		t.Errorf("output = %d, want %d (a drifting-timestamp replay must still be dropped)", got, want)
	}
}

// Real consecutive API calls are seconds apart and must all survive, even on a
// forked thread.
func TestCodexKeepsSpacedCallsOnFork(t *testing.T) {
	root := t.TempDir()
	lines := []string{codexMeta("s8", "s1", "subagent", "gpt-5.6-terra")}
	for i := range 5 {
		ts := time.Date(2026, 8, 2, 10, i*2, 0, 0, time.UTC)
		lines = append(lines, codexTokens(ts.Format("2006-01-02T15:04:05.000Z"), 100, 0, 10))
	}
	writeFile(t, filepath.Join(root, "sessions", "2026", "08", "02", "rollout-x-s8.jsonl"), lines...)

	turns := scan(t, newCodexAt(root))
	if got, want := totalOut(turns), int64(50); got != want {
		t.Errorf("output = %d, want %d (spaced real calls must not be treated as replay)", got, want)
	}
}

// A forked thread whose first call happens to be its own — a single leading
// event, not a burst — must keep that call.
func TestCodexKeepsLoneFirstCallOnFork(t *testing.T) {
	root := t.TempDir()
	writeFile(t, filepath.Join(root, "sessions", "2026", "08", "02", "rollout-x-s3.jsonl"),
		codexMeta("s3", "s1", "user", "gpt-5.6-terra"),
		codexTokens("2026-08-02T10:00:00.000Z", 100, 0, 7),
		codexTokens("2026-08-02T10:05:00.000Z", 200, 0, 11),
	)
	turns := scan(t, newCodexAt(root))
	if got, want := totalOut(turns), int64(18); got != want {
		t.Errorf("output = %d, want %d", got, want)
	}
}

// A non-forked session is never subject to burst detection, even if several
// calls share a timestamp.
func TestCodexPlainSessionKeepsEverything(t *testing.T) {
	root := t.TempDir()
	ts := "2026-08-01T10:00:02.000Z"
	writeFile(t, filepath.Join(root, "sessions", "2026", "08", "01", "rollout-x-s4.jsonl"),
		codexMeta("s4", "", "user", "gpt-5.6-terra"),
		codexTokens(ts, 100, 0, 10),
		codexTokens(ts, 100, 0, 10),
		codexTokens(ts, 100, 0, 10),
	)
	turns := scan(t, newCodexAt(root))
	if got, want := totalOut(turns), int64(30); got != want {
		t.Errorf("output = %d, want %d", got, want)
	}
}

// Some rollouts log usage before the turn_context that names the model. Those
// calls used to end up modelless and therefore unpriced, silently dropping
// 1.03B tokens out of the totals.
func TestCodexBackfillsModelLoggedLate(t *testing.T) {
	root := t.TempDir()
	writeFile(t, filepath.Join(root, "sessions", "2026", "08", "01", "rollout-x-s5.jsonl"),
		codexMeta("s5", "", "user", ""), // no model on the meta
		codexTokens("2026-08-01T10:00:02.000Z", 100, 0, 10),
		codexTurnContext("gpt-5.6-sol"),
		codexTokens("2026-08-01T10:00:09.000Z", 100, 0, 10),
	)
	turns := scan(t, newCodexAt(root))
	if len(turns) != 2 {
		t.Fatalf("got %d turns, want 2", len(turns))
	}
	for i, x := range turns {
		if x.Model != "gpt-5.6-sol" {
			t.Errorf("turn %d model = %q, want gpt-5.6-sol", i, x.Model)
		}
	}
}

// Every call carries its own clock, which is what lets a session spanning
// midnight split across days.
func TestCodexTurnsCarryOwnTimestamps(t *testing.T) {
	root := t.TempDir()
	writeFile(t, filepath.Join(root, "sessions", "2026", "08", "01", "rollout-x-s6.jsonl"),
		codexMeta("s6", "", "user", "gpt-5.6-terra"),
		codexTokens("2026-08-01T23:59:00.000Z", 100, 0, 10),
		codexTokens("2026-08-02T00:01:00.000Z", 100, 0, 20),
	)
	turns := scan(t, newCodexAt(root))
	if len(turns) != 2 {
		t.Fatalf("got %d turns, want 2", len(turns))
	}
	if turns[0].Timestamp.Equal(turns[1].Timestamp) {
		t.Error("turns share a timestamp; per-call clocks were lost")
	}
}

// --- shared -----------------------------------------------------------------

// Very long lines are routine: transcripts embed whole files and tool outputs.
// bufio.Scanner would silently stop the scan at 64KB.
func TestHandlesVeryLongLines(t *testing.T) {
	root := t.TempDir()
	proj := filepath.Join(root, "projects", "-proj")
	huge := strings.Repeat("x", 900_000)
	line := `{"type":"assistant","timestamp":"2026-08-01T10:00:00Z","requestId":"r","sessionId":"s","cwd":"/p","pad":"` +
		huge + `","message":{"id":"m","model":"claude-opus-5","usage":{"input_tokens":1,"output_tokens":7,` +
		`"cache_read_input_tokens":0,"cache_creation_input_tokens":0}}}`
	writeFile(t, filepath.Join(proj, "s.jsonl"), line,
		claudeLine("m2", "r2", "claude-opus-5", "2026-08-01T10:01:00Z", 1, 5, 0, 0))

	turns := scan(t, newClaudeAt(root))
	if got, want := totalOut(turns), int64(12); got != want {
		t.Errorf("output = %d, want %d (a long line must not truncate the scan)", got, want)
	}
}

// A missing agent directory is not an error, it just means the agent is not
// installed.
func TestMissingRootIsNotAnError(t *testing.T) {
	res, err := Run(context.Background(), []Scanner{newClaudeAt(t.TempDir()), newCodexAt(t.TempDir())})
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if len(res.Turns) != 0 {
		t.Errorf("got %d turns from empty roots", len(res.Turns))
	}
}

// --- corrupt-record handling -------------------------------------------------

// Agent logs are appended live, so torn and garbled writes are normal. A single
// bad record must not be able to move the total: a fuzz run fed one line
// claiming 99,999,999,999,999 output tokens and the report produced
// $2,500,000,000.00.
func TestAbsurdTokenCountIsDropped(t *testing.T) {
	root := t.TempDir()
	proj := filepath.Join(root, "projects", "-proj")
	writeFile(t, filepath.Join(proj, "s.jsonl"),
		claudeLine("m1", "r1", "claude-opus-5", "2026-08-01T10:00:00Z", 1, 99_999_999_999_999, 0, 0),
		claudeLine("m2", "r2", "claude-opus-5", "2026-08-01T10:01:00Z", 1, 500, 0, 0),
	)
	turns := scan(t, newClaudeAt(root))
	if got, want := totalOut(turns), int64(500); got != want {
		t.Errorf("output = %d, want %d (the impossible record must be dropped)", got, want)
	}
}

// Negative counts are field-level corruption; zero that field rather than
// discard an otherwise good call, and never let it subtract from the total.
func TestNegativeTokenCountIsClamped(t *testing.T) {
	root := t.TempDir()
	proj := filepath.Join(root, "projects", "-proj")
	writeFile(t, filepath.Join(proj, "s.jsonl"),
		claudeLine("m1", "r1", "claude-opus-5", "2026-08-01T10:00:00Z", -999, 10, 0, 0))
	turns := scan(t, newClaudeAt(root))
	if len(turns) != 1 {
		t.Fatalf("got %d turns, want 1", len(turns))
	}
	if turns[0].Usage.Input != 0 {
		t.Errorf("input = %d, want 0 (negatives clamp, never subtract)", turns[0].Usage.Input)
	}
}

// Garbage lines, empty files and unparseable dates must not abort a scan or
// crash the process.
func TestCorruptFilesDoNotAbortScan(t *testing.T) {
	root := t.TempDir()
	proj := filepath.Join(root, "projects", "-proj")
	writeFile(t, filepath.Join(proj, "empty.jsonl"), "")
	writeFile(t, filepath.Join(proj, "garbage.jsonl"), "not json", `{"type":"assistant"`, "\x00\x01\xff")
	writeFile(t, filepath.Join(proj, "baddate.jsonl"),
		claudeLine("m1", "r1", "claude-opus-5", "NOT-A-DATE", 1, 9, 0, 0))
	writeFile(t, filepath.Join(proj, "good.jsonl"),
		claudeLine("m2", "r2", "claude-opus-5", "2026-08-01T10:00:00Z", 1, 4, 0, 0))

	turns := scan(t, newClaudeAt(root))
	if got, want := totalOut(turns), int64(13); got != want {
		t.Errorf("output = %d, want %d (good records survive alongside corrupt ones)", got, want)
	}
}
