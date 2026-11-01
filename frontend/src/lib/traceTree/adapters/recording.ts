/**
 * Conservative projection for readers without verified model-call boundaries.
 * Keep file order and recorded message/tool evidence; never infer clock time,
 * per-call usage, or tool-result pairing from proximity (except SmallCode's
 * explicit adjacent call/result contract).
 */
import type { Event, TraceValue } from "../../traceEvents";
import type { HarnessAdapter } from "../index";
import type { TraceSpan } from "../types";
import { collapse, toolLabel } from "./labelUtils";

function blocksOf(value: TraceValue): TraceValue[] | null {
  if (Array.isArray(value)) return value;
  // Cline's VS Code reader serializes its native content blocks as JSON.
  if (typeof value === "string" && value.length < 2_000_000 && value.trimStart().startsWith("[")) {
    try { const parsed = JSON.parse(value); if (Array.isArray(parsed)) return parsed; } catch { /* ordinary text */ }
  }
  return null;
}

function bodyOf(parts: TraceValue[], type: "text" | "thinking"): unknown {
  const values = parts.filter(p => p && (type === "text" ? ["text", "input_text", "output_text"].includes(p.type) : ["thinking", "think"].includes(p.type)))
    .map(p => type === "text" ? p.text : p.thinking ?? p.text).filter(v => typeof v === "string");
  return values.length ? values.join("\n\n") : undefined;
}

function build(agent: string, events: Event[], delegation: TraceValue): TraceSpan[] {
  const roots: TraceSpan[] = [];
  const pending = new Map<string, TraceSpan>();
  let turn: TraceSpan | null = null;
  let prompts = 0;
  let adjacent: TraceSpan | undefined;
  const ensureTurn = (i: number) => {
    if (!turn) {
      turn = { id: `record-turn-${i}`, kind: "turn", title: "Recorded activity", start: i, end: i, children: [], turnKind: "notification", recordOnly: true };
      roots.push(turn);
    }
    return turn;
  };
  events.forEach((event, i) => {
    if (agent === "smallcode" && event.type !== "tool_call" && event.type !== "tool_result") adjacent = undefined;
    const payload = event.payload;
    const message = event.message ?? (payload && !Array.isArray(payload) && typeof payload === "object" ? payload : {});
    const value = Object.prototype.hasOwnProperty.call(message, "content") ? message.content : event.content !== undefined ? event.content : payload;
    const parts = blocksOf(value);
    const role = event.role ?? message.role ?? event.type;
    const result = (id: unknown, value: unknown, error: boolean, title?: string) => {
      const call = typeof id === "string" ? pending.get(id) : agent === "smallcode" && adjacent?.title === title ? adjacent : undefined;
      if (call) {
        call.content = { ...call.content, output: value };
        call.end = i;
        if (error) call.error = true;
        if (typeof id === "string") pending.delete(id);
      } else {
        ensureTurn(i).children.push({ id: `record-result-${i}-${ensureTurn(i).children.length}`, kind: "tool", title: title || "Unlinked tool result", label: "Result record · call association unavailable", start: i, end: i, children: [], eventIndex: i, content: { output: value }, error: error || undefined });
      }
      adjacent = undefined;
    };
    const call = (parent: TraceSpan, item: TraceValue, j: number) => {
      const fn = item.function ?? item;
      const input = fn.arguments !== undefined ? fn.arguments : fn.input !== undefined ? fn.input : fn.args;
      const span: TraceSpan = { id: `record-tool-${i}-${j}`, kind: "tool", title: fn.name || item.tool || "Tool call", label: toolLabel(input) || undefined, start: i, end: i, children: [], eventIndex: i, content: { input } };
      parent.children.push(span);
      const id = item.id ?? item.callID;
      if (typeof id === "string" && id) pending.set(id, span);
      adjacent = span;
    };
    if (event.type === "tool_result" || role === "tool") {
      result(message.callID ?? message.tool_call_id, value, !!message.is_error || message.success === false, message.tool);
    } else if (event.type === "tool_call") {
      call(ensureTurn(i), { ...message, name: message.tool, id: message.callID }, 0);
    } else if (role === "user" || role === "human") {
      const text = parts ? bodyOf(parts, "text") ?? (parts.some(p => p?.type !== "tool_result") ? parts.filter(p => p?.type !== "tool_result") : undefined) : value;
      const results = parts?.filter(p => p?.type === "tool_result") ?? [];
      if (text !== undefined && text !== "" && text !== null) {
        turn = { id: `record-turn-${i}`, kind: "turn", title: `User entry ${++prompts}`, label: typeof text === "string" ? collapse(text) : undefined, content: { input: text }, start: i, end: i, children: [], eventIndex: i, turnKind: "prompt", recordOnly: true };
        roots.push(turn);
        adjacent = undefined;
      }
      results.forEach(p => result(p.tool_use_id, p.content, !!p.is_error));
    } else if (["assistant", "gemini", "assistant_thinking"].includes(role)) {
      const parent = ensureTurn(i);
      const thinking = event.type === "assistant_thinking" ? message.text ?? message.content ?? payload : parts ? bodyOf(parts, "thinking") : undefined;
      const knownBlocks = parts?.every(p => p && ["text", "input_text", "output_text", "thinking", "think", "tool_use"].includes(p.type));
      const output = event.type === "assistant_thinking" ? undefined : parts && knownBlocks ? bodyOf(parts, "text") : value;
      const span: TraceSpan = { id: `record-assistant-${i}`, kind: "llm", title: message.model || "Assistant record", start: i, end: i, children: [], eventIndex: i, content: { output, reasoning: thinking }, label: typeof output === "string" ? collapse(output) : undefined, recordOnly: true };
      parent.children.push(span);
      (parts?.filter(p => p?.type === "tool_use") ?? []).forEach((item, j) => call(span, item, j));
      (Array.isArray(message.tool_calls) ? message.tool_calls : []).forEach((item: TraceValue, j: number) => call(span, item, j + (parts?.length ?? 0)));
    }
    if (turn) turn.end = i;
  });
  // Delegation metadata cannot be placed at a dialogue call unless the reader
  // supplies a join key. Keep it visible, explicitly outside conversation order.
  const subs = Array.isArray(delegation?.subagents) ? delegation.subagents : [];
  if (subs.length) {
    const root: TraceSpan = { id: "record-delegations", kind: "turn", title: "Delegation metadata · placement unavailable", content: { input: "These child recordings are linked by harness metadata. Their handoff position in the conversation was not recorded by this reader." }, turnKind: "notification", start: events.length, end: events.length + subs.length, children: [], recordOnly: true };
    subs.forEach((entry: TraceValue, i: number) => {
      const childId = agent === "grok" ? entry.child_session_id : entry.agent_id;
      root.children.push({ id: `record-agent-${i}`, kind: "agent", title: entry.agent_type || "Subagent", label: entry.description, start: events.length + i, end: events.length + i, children: [], content: { input: entry.prompt ?? entry.description }, agent: { agentType: entry.agent_type || "Subagent", childId, loaded: false, model: entry.model,
        totalTokens: delegation.tokens_recorded === true && typeof entry.tokens?.total === "number" ? entry.tokens.total : undefined,
        toolCalls: entry.tool_calls } });
    });
    roots.push(root);
  }
  return roots;
}

export function recordingAdapter(agent: string): HarnessAdapter {
  return {
    timing: "order-only",
    notice: "Recording order · exact timing and model-call boundaries are unavailable for this reader. Results and per-call usage may be absent from the available trace; linked delegation metadata is shown separately from the dialogue.",
    build: (events, delegation) => build(agent, events, delegation),
    childFetch: (sessionId, span) => {
      const child = span.agent?.childId;
      if (!child) return null;
      if (agent === "grok") return { path: `/sessions/${encodeURIComponent(child)}?agent=grok`, agent };
      if (agent === "cursor" || agent === "muse") return { path: `/sessions/${encodeURIComponent(sessionId)}/subagents/${encodeURIComponent(child)}/trace?agent=${agent}`, agent };
      return null;
    },
  };
}
