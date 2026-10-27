/**
 * Which harnesses get the trace tree, and the adapter that builds it.
 *
 * A harness is listed only when its trace has real per-event times and tool
 * calls that pair with their results, checked against real sessions. Harnesses
 * left out (synthetic timestamps, no tool results, no tool events at all) keep
 * the old step view; see the audit notes on each adapter for why.
 */
import type { Event, TraceValue } from "../traceEvents";
import type { TraceSpan, TraceTiming } from "./types";
import { claudeShapeAdapter } from "./adapters/claudeShape";
import { codexAdapter } from "./adapters/codex";
import { geminiAdapter } from "./adapters/gemini";
import { qwenAdapter } from "./adapters/qwen";
import { opencodeAdapter } from "./adapters/opencode";
import { hermesAdapter } from "./adapters/hermes";
import { primeAdapter } from "./adapters/prime";

export interface ChildFetch {
  /** apiFetch path for the child's raw trace, e.g. `/sessions/<child>?agent=opencode`. */
  path: string;
  /** Agent name to pass to normalizeTraceEvents for the child payload. */
  agent: string;
}

export interface HarnessAdapter {
  timing: TraceTiming;
  /**
   * Build turn -> llm -> tool spans from the page's normalized events (the same
   * array the step cards render, so `eventIndex` lines up). Calls that spawned a
   * subagent become kind "agent" spans with `agent.loaded = false`, enriched from
   * `delegation` (the /sessions/{id}/delegation payload, or null) where it links.
   */
  build(events: Event[], delegation: TraceValue | null): TraceSpan[];
  /** Where to fetch an agent span's child trace, or null when the harness has none. */
  childFetch?(sessionId: string, agentSpan: TraceSpan): ChildFetch | null;
  /** Spans for a fetched child, from its normalized events. Defaults to `build(events, null)`. */
  buildChild?(events: Event[]): TraceSpan[];
}

const ADAPTERS: Record<string, HarnessAdapter> = {
  claude: claudeShapeAdapter("claude"),
  dsh: claudeShapeAdapter("dsh"),
  pi: claudeShapeAdapter("pi"),
  qoder: claudeShapeAdapter("qoder"),
  codex: codexAdapter,
  gemini: geminiAdapter,
  qwen: qwenAdapter,
  opencode: opencodeAdapter("opencode"),
  zcode: opencodeAdapter("zcode"),
  hermes: hermesAdapter,
  prime: primeAdapter,
};

export function traceAdapter(agent: string | null | undefined): HarnessAdapter | null {
  return (agent && ADAPTERS[agent]) || null;
}

export type { TraceSpan, TraceTiming, TraceTree, SpanKind, SpanTokens, AgentInfo } from "./types";
