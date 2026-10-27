/**
 * Gemini CLI trace -> turn / llm / tool spans.
 *
 * Each assistant message (type "gemini", renamed by the normalizer) is one
 * model response with its token counts and the tool calls it made nested
 * inside. The message timestamp is when the response was written, so an llm
 * span starts at the latest earlier activity (previous message or its tools),
 * which keeps it clear of long approval waits on the previous tools. Tool calls
 * carry only their completion time, so a tool runs from the message to that.
 * No subagents.
 */
import type { Event, TraceValue } from "../../traceEvents";
import type { HarnessAdapter } from "../index";
import type { SpanTokens, TraceSpan } from "../types";
import { collapse, eventMs, partsText, toolLabel } from "./labelUtils";

/** Gemini's input includes cached tokens; thoughts are billed as output. */
export function geminiTokens(t: TraceValue): SpanTokens | undefined {
  if (!t || typeof t !== "object") return undefined;
  const cached = t.cached || 0;
  return {
    input: Math.max(0, (t.input || 0) - cached) + (t.tool || 0),
    output: (t.output || 0) + (t.thoughts || 0),
    cacheRead: cached,
    cacheWrite: 0,
  };
}

function build(events: Event[]): TraceSpan[] {
  const roots: TraceSpan[] = [];
  let turn: TraceSpan | null = null;
  let prompts = 0;
  let last = 0; // latest activity seen
  let seq = 0;
  const id = (p: string) => `gemini-${p}-${seq++}`;

  events.forEach((e, i) => {
    const t = eventMs(e);
    if (t === undefined) return;
    if (e.type === "user") {
      turn = {
        id: id("turn"), kind: "turn", title: `User prompt ${++prompts}`, start: t, end: t, children: [],
        eventIndex: i, turnKind: "prompt",
      };
      const text = partsText(e.content);
      if (text) turn.label = collapse(text);
      roots.push(turn);
      last = t;
      return;
    }
    if (e.type !== "assistant") return; // info / warning lines are system noise
    if (!turn) {
      turn = {
        id: id("turn"), kind: "turn", title: "Agent turn", start: last || t, end: t, children: [],
        eventIndex: i, turnKind: "notification",
      };
      roots.push(turn);
    }
    const llm: TraceSpan = {
      id: id("llm"), kind: "llm", title: (e as TraceValue).model || "gemini", start: Math.min(last || t, t), end: t,
      children: [], tokens: geminiTokens((e as TraceValue).tokens), eventIndex: i, approxStart: true,
    };
    const text = partsText(e.content);
    if (text) llm.label = collapse(text);
    let latest = t;
    for (const call of e.toolCalls || []) {
      const end = Math.max(t, eventMs(call.timestamp) ?? t);
      const tool: TraceSpan = {
        id: id("tool"), kind: "tool", title: call.name || "tool", start: t, end,
        children: [], eventIndex: i,
      };
      const label = toolLabel(call.args);
      if (label) tool.label = label;
      if (call.status === "error") tool.error = true;
      llm.children.push(tool);
      latest = Math.max(latest, end);
    }
    turn.children.push(llm);
    turn.end = latest;
    last = latest;
  });
  return roots;
}

export const geminiAdapter: HarnessAdapter = {
  timing: "real",
  build,
};
