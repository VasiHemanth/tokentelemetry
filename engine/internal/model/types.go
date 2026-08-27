// Package model holds the core data shapes every scanner produces and every
// report consumes.
//
// The central decision here is that a Turn — one API call — is the atom, not a
// session. The Python implementation aggregated at session level, which forced
// three bugs that could not be fixed locally:
//
//   - one model per session (first one seen won), so a thread that switched
//     models billed everything at the first model's rate;
//   - one timestamp per session, so a run spanning midnight dumped its whole
//     cost onto the last day;
//   - no identity per API call, so replayed history in a resumed or forked
//     transcript was counted again.
//
// Keying on the turn makes all three fall out for free: dedup on the turn's
// identity, bucket on the turn's own clock, price with the turn's own model.
package model

import "time"

// Agent is the coding agent a turn came from.
type Agent string

const (
	AgentClaude      Agent = "claude"
	AgentCodex       Agent = "codex"
	AgentOpenCode    Agent = "opencode"
	AgentHermes      Agent = "hermes"
	AgentGemini      Agent = "gemini"
	AgentAntigravity Agent = "antigravity"
	AgentCopilot     Agent = "copilot"
	AgentCursor      Agent = "cursor"
	AgentQwen        Agent = "qwen"
	AgentGrok        Agent = "grok"
	AgentCline       Agent = "cline"
	AgentPi          Agent = "pi"
	AgentSmallCode   Agent = "smallcode"
	AgentVibe        Agent = "vibe"
)

// Usage is the token accounting for a single API call.
//
// Input is the NET uncached prompt, never the gross figure. Providers differ
// here — Anthropic reports input_tokens already exclusive of cache reads, while
// Codex reports a gross input_tokens that includes cached_input_tokens — so
// each scanner normalises to net on the way in. Downstream code can therefore
// always treat the four buckets as disjoint and sum them without
// double-counting.
type Usage struct {
	Input         int64 `json:"input"`
	Output        int64 `json:"output"`
	CacheRead     int64 `json:"cache_read"`
	CacheWrite    int64 `json:"cache_write"`
	CacheWrite1h  int64 `json:"cache_write_1h,omitempty"`
	Reasoning     int64 `json:"reasoning,omitempty"`
	ContextTokens int64 `json:"context_tokens,omitempty"`
}

// Total is every billable token in the call.
func (u Usage) Total() int64 {
	return u.Input + u.Output + u.CacheRead + u.CacheWrite
}

// Add accumulates another usage into this one.
func (u *Usage) Add(o Usage) {
	u.Input += o.Input
	u.Output += o.Output
	u.CacheRead += o.CacheRead
	u.CacheWrite += o.CacheWrite
	u.CacheWrite1h += o.CacheWrite1h
	u.Reasoning += o.Reasoning
	if o.ContextTokens > u.ContextTokens {
		u.ContextTokens = o.ContextTokens
	}
}

// IsZero reports whether the call carried no billable tokens at all. Scanners
// use it to drop the empty usage blocks agents emit for synthetic messages.
func (u Usage) IsZero() bool { return u.Total() == 0 && u.Reasoning == 0 }

// MaxPerCallTokens bounds any single bucket of a single API call.
//
// The largest context windows in service are a few million tokens, so 50M is
// far above anything real while still catching a corrupt record. This matters
// because agent logs are appended live and a torn or garbled write is normal:
// a fuzz run fed one line claiming 99,999,999,999,999 output tokens and the
// report obediently produced $2,500,000,000.00.
const MaxPerCallTokens = 50_000_000

// Sanitize clamps impossible counts and reports whether the usage is plausible.
//
// Negative counts are clamped to zero rather than rejected — they show up as
// isolated field-level corruption in otherwise good records, and zeroing one
// field loses less than discarding the call. A count beyond MaxPerCallTokens is
// different in kind: it means the record cannot be trusted at all, so the
// caller is told to drop it.
func (u Usage) Sanitize() (Usage, bool) {
	clamp := func(v *int64) {
		if *v < 0 {
			*v = 0
		}
	}
	clamp(&u.Input)
	clamp(&u.Output)
	clamp(&u.CacheRead)
	clamp(&u.CacheWrite)
	clamp(&u.CacheWrite1h)
	clamp(&u.Reasoning)
	clamp(&u.ContextTokens)

	for _, v := range [...]int64{u.Input, u.Output, u.CacheRead, u.CacheWrite, u.Reasoning} {
		if v > MaxPerCallTokens {
			return u, false
		}
	}
	// The 1-hour cache figure is a subset of the cache writes, never an extra
	// bucket, so a larger value is a misread rather than extra spend.
	if u.CacheWrite1h > u.CacheWrite {
		u.CacheWrite1h = u.CacheWrite
	}
	return u, true
}

// Turn is one API call, the unit of dedup, pricing and bucketing.
type Turn struct {
	// Identity. Key is what dedup runs on; scanners build it from whatever the
	// agent's log format offers that is stable across a replay (Claude's
	// message id + request id, Codex's turn id + cumulative counter).
	Key       string `json:"key"`
	SessionID string `json:"session_id"`
	Agent     Agent  `json:"agent"`

	// When the call happened, per the log. Bucketing uses this, so a session
	// spanning midnight splits across days correctly.
	Timestamp time.Time `json:"timestamp"`

	// Model as the agent recorded it, before normalisation. Provider is the
	// routing destination when the agent records one ("openai", "together",
	// "fireworks"); empty when unknown.
	Model    string `json:"model"`
	Provider string `json:"provider,omitempty"`

	// Endpoint is the base URL the call went to, when recorded. Used to
	// recognise subscription-backed routing (chatgpt.com/backend-api/codex) so
	// it can be labelled — never to zero the cost out. See package cost.
	Endpoint string `json:"endpoint,omitempty"`

	Project string `json:"project,omitempty"`
	Usage   Usage  `json:"usage"`

	// ServiceTier is the provider's billing tier for the call ("standard",
	// "batch", "priority"). Batch traffic bills at half rate, so ignoring this
	// overstates the cost of anything run through a batch queue.
	ServiceTier string `json:"service_tier,omitempty"`

	// Subagent marks a turn belonging to a delegated thread. These are real
	// spend and are always counted; the flag exists so reports can break
	// delegation out, and because ccusage misses them entirely on Codex.
	Subagent bool `json:"subagent,omitempty"`
}

// Session is the turn-level rollup of one agent conversation. It is derived
// from turns, never the other way around.
type Session struct {
	ID       string    `json:"id"`
	Agent    Agent     `json:"agent"`
	Project  string    `json:"project,omitempty"`
	Title    string    `json:"title,omitempty"`
	Start    time.Time `json:"start"`
	End      time.Time `json:"end"`
	Turns    int       `json:"turns"`
	Usage    Usage     `json:"usage"`
	Models   []string  `json:"models,omitempty"`
	ParentID string    `json:"parent_id,omitempty"`
	Subagent bool      `json:"subagent,omitempty"`
}
