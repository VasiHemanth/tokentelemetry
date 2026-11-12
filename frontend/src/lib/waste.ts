// Response types and flag copy for GET /waste (backend/waste.py::aggregate).
// A null count or ratio means the agent's logs do not record it. It is never
// zero, and the UI must not render it as zero.

export type WasteFlag =
  | "tool_failures" | "retry_loop" | "rereads"
  | "context_bloat" | "low_cache" | "no_artifact";

export const WASTE_FLAGS: WasteFlag[] = [
  "tool_failures", "retry_loop", "rereads", "context_bloat", "low_cache", "no_artifact",
];

export interface WasteSummary {
  sessions: number;
  analysed: number;          // includes failed
  pending: number;
  failed: number;
  total_cost: number;
  flagged_sessions: number;
  flagged_cost: number;
  tool_calls: number;
  tool_errors: number;
  failure_rate: number | null; // 0 to 1 ratio
  retry_calls: number;
  reread_calls: number;
  no_artifact_sessions: number;
  cost_per_session: number;
  turns_per_session: number;
  cost_per_turn: number;
}

// Keys match backend CAPABILITY_KEYS. false means the agent's logs lack it.
export interface WasteCapabilities {
  tool_errors: boolean;
  retries: boolean;
  rereads: boolean;
  turns: boolean;
  context_growth: boolean;
  cache: boolean;
}

export interface WasteAgentRow {
  agent: string;
  sessions: number;
  analysed: number;
  cost: number;
  flagged_sessions: number;
  flagged_cost: number;
  failure_rate: number | null;
  retry_calls: number | null;
  reread_calls: number | null;
  cost_per_session: number;
  turns_per_session: number | null;
  capabilities: WasteCapabilities;
}

export interface WasteFlagRow {
  flag: WasteFlag;
  sessions: number;
  cost: number;
}

export interface WasteSessionRow {
  id: string;
  agent: string;
  project: string;
  timestamp: string | null;
  display: string;
  model: string;
  cost: number;
  tokens_total: number;
  user_turns: number | null;
  tool_calls: number;
  tool_errors: number | null;
  retry_calls: number | null;
  reread_calls: number | null;
  edit_calls: number | null;
  cache_hit_pct: number | null; // 0 to 100
  context_growth: number | null;
  flags: WasteFlag[];
}

export interface WasteThresholds {
  tool_failures_min_calls: number;
  tool_failures_rate: number;
  retry_loop_calls: number;
  rereads_calls: number;
  context_bloat_growth: number;
  low_cache_min_tokens: number;
  low_cache_hit_pct: number;
  no_artifact_min_calls: number;
  retry_run_min: number;
  context_growth_min_turns: number;
}

export interface WasteResponse {
  summary: WasteSummary;
  by_agent: WasteAgentRow[];
  by_flag: WasteFlagRow[];
  sessions: WasteSessionRow[];
  thresholds: WasteThresholds;
}

export const FLAG_INFO: Record<WasteFlag, { label: string; description: string }> = {
  tool_failures: {
    label: "Tool failures",
    description: "A large share of the session's tool calls returned an error.",
  },
  retry_loop: {
    label: "Retry loop",
    description: "The same tool call was repeated with identical arguments several times in a row.",
  },
  rereads: {
    label: "Repeated reads",
    description: "The same file was read again and again within one session.",
  },
  context_bloat: {
    label: "Context growth",
    description: "The context sent per turn grew many times larger between the start and the end of the session.",
  },
  low_cache: {
    label: "Low cache hits",
    description: "A large session where little of the input was served from the prompt cache.",
  },
  no_artifact: {
    label: "No edits",
    description: "Many tool calls and above-median cost, but no file edit through an edit tool and no artifact. Work done only through shell commands is not seen, so check the session before concluding anything.",
  },
};

// Table column to the capability that says whether the agent records it.
export const COLUMN_CAPABILITY = {
  failure_rate: "tool_errors",
  retry_calls: "retries",
  reread_calls: "rereads",
  turns_per_session: "turns",
} as const satisfies Record<string, keyof WasteCapabilities>;

export function thresholdLines(t: WasteThresholds): { flag: WasteFlag; text: string }[] {
  const pct = (r: number) => `${Math.round(r * 100)}%`;
  const n = (v: number) => v.toLocaleString();
  return [
    { flag: "tool_failures", text: `At least ${n(t.tool_failures_min_calls)} tool calls and ${pct(t.tool_failures_rate)} or more of them failed.` },
    { flag: "retry_loop", text: `${n(t.retry_loop_calls)} or more repeated calls, counting runs of ${n(t.retry_run_min)} or more identical consecutive calls.` },
    { flag: "rereads", text: `${n(t.rereads_calls)} or more repeat reads of a file already read in the session.` },
    { flag: "context_bloat", text: `Context per turn grew ${t.context_bloat_growth}x or more, in sessions with at least ${n(t.context_growth_min_turns)} turns of usage data.` },
    { flag: "low_cache", text: `At least ${n(t.low_cache_min_tokens)} input tokens and a cache hit rate under ${t.low_cache_hit_pct}%. Only agents that report cache usage.` },
    { flag: "no_artifact", text: `At least ${n(t.no_artifact_min_calls)} tool calls, no edits, no artifacts, and cost at or above the median session in range.` },
  ];
}

export interface WasteOccurrence { call: number | null; turn: number | null; repeat: boolean }

/** GET /waste/session/{id}: computed on demand, never cached. */
export interface WasteExplain {
  rereads: Array<{ path: string; name: string; reads: number; repeats: number; edits: number; occurrences: WasteOccurrence[] }>;
  retries: Array<{ tool: string; path: string | null; call: number | null; turn: number | null; count: number }>;
  errors: { total: number; by_tool: Array<{ tool: string; count: number }>; turns: number[] };
}
