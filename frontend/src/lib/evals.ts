/**
 * Always-on agent eval events (GET /evals/events, /evals/summary, /config/evals).
 *
 * Rows carry ids, timings, enums and labels only — never prompt text or paths.
 * `evalRecordOnly` (default true) means events are recorded but never feed
 * notifications or scoring. Not to be confused with `TraceSpan.recordOnly`.
 */

export type EvalKind = "wake_decision" | "schedule_fire" | "agent_call";
export type EvalSource = "derived" | "recorded" | "human_label";

interface EvalBase {
  id: string;
  agent: string;
  session_id: string;
  ts: string;
  kind: EvalKind;
  source: EvalSource;
  schema_version: 1;
}

export interface WakeDecisionEvent extends EvalBase {
  kind: "wake_decision";
  decision: "wake" | "silence";
  trigger: "cron" | "event" | "peer" | "user";
  reason?: string;
  confidence?: number;
  label?: "should_wake" | "should_silence";
  turn_event_index?: number;
  job_id?: string;
}

export interface ScheduleFireEvent extends EvalBase {
  kind: "schedule_fire";
  loop_id?: string;
  job_id?: string;
  cadence?: string;
  expected_at?: string;
  actual_at?: string;
  drift_s?: number;
  missed: boolean;
  human_present: boolean;
}

export interface AgentCallEvent extends EvalBase {
  kind: "agent_call";
  parent_session_id?: string;
  parent_span_id?: string;
  child_session_id?: string;
  msg_id?: string;
  channel: "subagent" | "peer" | "a2a";
  resolved: boolean;
  latency_ms?: number;
}

export type EvalEvent = WakeDecisionEvent | ScheduleFireEvent | AgentCallEvent;

export interface EvalSummary {
  record_only: boolean;
  wake: { labeled: number; tp: number; fp: number; fn: number; precision: number | null; recall: number | null };
  schedule: { fires: number; missed: number; drift_p50_s: number | null; drift_p95_s: number | null };
  agent_calls: { total: number; unresolved: number };
}

export interface EvalConfig {
  evalRecordOnly: boolean;
}
