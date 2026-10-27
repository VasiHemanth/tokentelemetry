/**
 * Qwen Code trace -> turn / llm / tool spans.
 *
 * Assistant events hold thought / text / functionCall parts and the token
 * usage; tool_result events carry their own timestamps and a toolCallResult
 * status. Each model response is preceded by a ui_telemetry api_response with
 * duration_ms, so matched llm spans get a real start. `agent` calls become
 * agent spans with no child trace (qwen does not store one), but the
 * subagent's own api_response / tool_call telemetry is tagged with a
 * "#<Type>-<hash>#n" prompt_id, which gives its token and tool totals.
 * Cancelled tools are not flagged as errors (the user declined them);
 * api_error events have no assistant message and are not shown.
 */
import type { Event, TraceValue } from "../../traceEvents";
import type { HarnessAdapter } from "../index";
import type { SpanTokens, TraceSpan } from "../types";
import { collapse, eventMs, partsText, toolLabel } from "./labelUtils";

/** promptTokenCount includes cached tokens; candidates already include thoughts. */
export function qwenTokens(u: TraceValue): SpanTokens | undefined {
  if (!u || typeof u !== "object") return undefined;
  const cached = u.cachedContentTokenCount || 0;
  return {
    input: Math.max(0, (u.promptTokenCount || 0) - cached),
    output: u.candidatesTokenCount || 0,
    cacheRead: cached,
    cacheWrite: 0,
  };
}

interface SubGroup {
  tokens: number;
  tools: number;
  errors: number;
  lastTs: number;
  model?: string;
  used: boolean;
}

function build(events: Event[]): TraceSpan[] {
  const ui = (e: Event): TraceValue => (e.type === "system" ? (e as TraceValue).systemPayload?.uiEvent : null);

  // Results by call id.
  const results = new Map<string, { ts: number; status: string }>();
  events.forEach((e) => {
    if (e.type !== "tool_result") return;
    const callId = (e as TraceValue).toolCallResult?.callId;
    const ts = eventMs(e);
    if (callId && ts !== undefined) results.set(callId, { ts, status: (e as TraceValue).toolCallResult?.status || "" });
  });

  // api_responses of the main conversation vs. subagent groups.
  const subGroups = new Map<string, SubGroup>();
  const mainResponses: Array<{ idx: number; ts: number; ui: TraceValue; used: boolean }> = [];
  events.forEach((e, i) => {
    const u = ui(e);
    if (!u) return;
    const ts = eventMs(e) ?? 0;
    const sub = String(u.prompt_id || "").match(/#([^#]+-[^#]+)#\d+$/)?.[1];
    if (sub) {
      const g = subGroups.get(sub) || { tokens: 0, tools: 0, errors: 0, lastTs: 0, used: false };
      if (u["event.name"] === "qwen-code.api_response") {
        g.tokens += (u.input_token_count || 0) + (u.output_token_count || 0);
        g.model = u.model || g.model;
      } else if (u["event.name"] === "qwen-code.tool_call") {
        g.tools += 1;
        if (u.success === false || u.status === "error") g.errors += 1;
      }
      g.lastTs = Math.max(g.lastTs, ts);
      subGroups.set(sub, g);
    } else if (u["event.name"] === "qwen-code.api_response") {
      mainResponses.push({ idx: i, ts, ui: u, used: false });
    }
  });

  const roots: TraceSpan[] = [];
  let turn: TraceSpan | null = null;
  let prompts = 0;
  let last = 0;
  let seq = 0;
  const id = (p: string) => `qwen-${p}-${seq++}`;

  events.forEach((e, i) => {
    const t = eventMs(e);
    if (t === undefined) return;
    if (e.type === "user") {
      turn = {
        id: id("turn"), kind: "turn", title: `User prompt ${++prompts}`, start: t, end: t, children: [],
        eventIndex: i, turnKind: "prompt",
      };
      const text = partsText((e.message as TraceValue)?.parts);
      if (text) turn.label = collapse(text);
      roots.push(turn);
      last = t;
      return;
    }
    if (e.type !== "assistant") return;
    if (!turn) {
      turn = {
        id: id("turn"), kind: "turn", title: "Agent turn", start: t, end: t, children: [],
        eventIndex: i, turnKind: "notification",
      };
      roots.push(turn);
    }
    const parts: TraceValue[] = (e.message as TraceValue)?.parts || [];
    const usage = (e as TraceValue).usageMetadata;

    // Match the api_response by token counts among the ones before this event.
    let start = last || t;
    let approx = true;
    const match = mainResponses.find(
      (r) => !r.used && r.idx < i && r.ui.input_token_count === usage?.promptTokenCount &&
        r.ui.output_token_count === usage?.candidatesTokenCount,
    );
    if (match) {
      match.used = true;
      if (typeof match.ui.duration_ms === "number") {
        start = Math.max(0, match.ts - match.ui.duration_ms);
        approx = false;
      }
    }
    start = Math.min(start, t);

    const llm: TraceSpan = {
      id: id("llm"), kind: "llm", title: (e as TraceValue).model || "qwen", start, end: t,
      children: [], tokens: qwenTokens(usage), eventIndex: i, ...(approx ? { approxStart: true } : {}),
    };
    const text = partsText(parts.filter((p) => !p.thought));
    if (text) llm.label = collapse(text);

    let latest = t;
    for (const p of parts) {
      const fc = p.functionCall;
      if (!fc) continue;
      const res = results.get(fc.id);
      const end = Math.max(t, res?.ts ?? t);
      const args = fc.args || {};
      const isAgent = fc.name === "agent";
      const span: TraceSpan = {
        id: id(isAgent ? "agent" : "tool"), kind: isAgent ? "agent" : "tool",
        title: isAgent ? String(args.subagent_type || "agent") : fc.name || "tool",
        start: t, end, children: [], eventIndex: i,
      };
      const label = toolLabel(args);
      if (label) span.label = label;
      if (res?.status === "error") span.error = true;
      if (isAgent) {
        span.agent = { agentType: span.title, callStart: t, callEnd: end, loaded: false };
        // Subagent telemetry that finished last before this call returned.
        let best: [string, SubGroup] | null = null;
        for (const [k, g] of subGroups) {
          if (!g.used && g.lastTs <= end + 1000 && (!best || g.lastTs > best[1].lastTs)) best = [k, g];
        }
        if (best) {
          best[1].used = true;
          span.agent.totalTokens = best[1].tokens;
          span.agent.toolCalls = best[1].tools;
          span.agent.toolErrors = best[1].errors;
          if (best[1].model) span.agent.model = best[1].model;
        }
      }
      llm.children.push(span);
      latest = Math.max(latest, end);
    }
    turn.children.push(llm);
    turn.end = Math.max(turn.end, latest);
    last = latest;
  });
  return roots;
}

export const qwenAdapter: HarnessAdapter = {
  timing: "real",
  build,
};
