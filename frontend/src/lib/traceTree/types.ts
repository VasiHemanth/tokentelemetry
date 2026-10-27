/**
 * Span model for the session trace tree.
 *
 * Every harness's trace is turned into the same shape: turns hold model calls,
 * model calls hold the tool calls they made, and a call that spawned a subagent
 * holds that subagent's own model calls. The UI only ever reads this shape, so
 * adding a harness means writing an adapter, not touching the components.
 */

export type SpanKind = "turn" | "llm" | "tool" | "agent";

export interface SpanTokens {
  input: number;
  output: number;
  cacheRead: number;
  cacheWrite: number;
}

export interface AgentInfo {
  /** Subagent type or name as the harness reports it ("reel-producer", "explore"). */
  agentType: string;
  /** Id the child trace is fetched by (Claude agent id, child session id). */
  childId?: string;
  /** When the spawning call was made and when it returned to the parent. */
  callStart?: number;
  callEnd?: number;
  /** The spawning call returned while the child kept working. */
  background?: boolean;
  model?: string;
  /** Totals from the harness's own delegation record, not summed from children. */
  totalTokens?: number;
  cost?: number;
  toolCalls?: number;
  toolErrors?: number;
  /** False until the child's own trace has been fetched and attached. */
  loaded: boolean;
}

export interface TraceSpan {
  /** Stable within one tree; used as a React key and for selection. */
  id: string;
  kind: SpanKind;
  /** Model name, tool name, agent type, or "User prompt N". */
  title: string;
  /** Short secondary text: tool description, prompt excerpt, response excerpt. */
  label?: string;
  /** Epoch ms. */
  start: number;
  end: number;
  children: TraceSpan[];
  tokens?: SpanTokens;
  error?: boolean;
  /** Index into the page's normalized events[], for jumping to the step card. */
  eventIndex?: number;
  /** The transcript only records when a response arrived; start is the previous event's time. */
  approxStart?: boolean;
  /** turn only: a user prompt, or a harness notification such as a subagent reporting back. */
  turnKind?: "prompt" | "notification";
  /** turn only: childId of the subagent whose completion started this turn. */
  notifiedBy?: string;
  /** tool only: childId of an existing subagent this call resumed (Claude SendMessage). */
  resumes?: string;
  /** agent only. */
  agent?: AgentInfo;
}

/**
 * "real": every event has its own wall-clock time, so bars and durations are true.
 * "order-only": timestamps are synthetic (e.g. Grok's chat_history), so the tree
 * renders without a time axis.
 */
export type TraceTiming = "real" | "order-only";

export interface TraceTree {
  roots: TraceSpan[];
  timing: TraceTiming;
}
