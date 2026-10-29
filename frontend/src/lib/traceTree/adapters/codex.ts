/**
 * Codex trace -> turn / llm / tool spans.
 *
 * Audited on real rollouts: every event has its own wall-clock time, tool calls
 * (response_item function_call / custom_tool_call) pair with their outputs by
 * call_id, and each model response ends with one token_usage_record. The record
 * lands a few ms after the response's last item, so an llm span runs from the
 * latest tool output (or prompt) up to its record. Tool spans can outlive the
 * llm span that issued them, which is real.
 *
 * Most calls are `exec`, whose input is JavaScript that can embed shell
 * commands, so those are labelled from the item_completed events that ran
 * inside the call window (search query, file read, MCP tool), never the input.
 * Subagent links come from SubAgentActivity items, whose id is the spawning
 * call_id and whose agent_thread_id is the child session id.
 */
import type { Event, TraceValue } from "../../traceEvents";
import type { HarnessAdapter, ChildFetch } from "../index";
import type { SpanTokens, TraceSpan } from "../types";
import { baseName, collapse, eventMs, LABEL_MAX, partsText, toolLabel } from "./labelUtils";

type Usage = {
  input_tokens?: number;
  cached_input_tokens?: number;
  cache_write_input_tokens?: number;
  output_tokens?: number;
};

export function codexTokens(u: Usage | null | undefined): SpanTokens | undefined {
  if (!u) return undefined;
  const cached = u.cached_input_tokens || 0;
  return {
    input: Math.max(0, (u.input_tokens || 0) - cached),
    output: u.output_tokens || 0,
    cacheRead: cached,
    cacheWrite: u.cache_write_input_tokens || 0,
  };
}

function outputText(output: TraceValue): string {
  if (typeof output === "string") return output;
  if (Array.isArray(output)) return output.map((p: TraceValue) => (typeof p?.text === "string" ? p.text : "")).join("\n");
  return "";
}

function parseArgs(raw: TraceValue): TraceValue {
  if (raw && typeof raw === "object") return raw;
  try {
    return JSON.parse(String(raw));
  } catch {
    return {};
  }
}

/** Codex has no error flag on tool results, so read it off the output text. */
export function codexOutputFailed(text: string): boolean {
  if (/^(Script failed|collab spawn failed)/.test(text)) return true;
  const code = text.match(/exit_code\\?"?\s*:\s*(-?\d+)/) || text.match(/exited with code (-?\d+)/i);
  return !!code && Number(code[1]) !== 0;
}

// Encrypted blobs (spawn/send messages, hidden reasoning) are not readable content.
const CIPHER = /^gAAAAA[\w-]{40,}/;
const isCipher = (v: unknown) => typeof v === "string" && CIPHER.test(v);

/** The args object itself, or a shallow copy without ciphertext fields. */
function readableArgs(args: TraceValue): TraceValue {
  if (!args || typeof args !== "object") return args;
  const bad = Object.keys(args).filter((k) => isCipher(args[k]));
  if (!bad.length) return args;
  return Object.fromEntries(Object.entries(args).filter(([k]) => !bad.includes(k)));
}

/** Content blocks of several messages in one array (block objects are shared, not copied). */
function joinBlocks(parts: TraceValue[]): unknown {
  if (!parts.length) return undefined;
  return parts.length === 1 ? parts[0] : parts.flat();
}

interface Nested {
  label: string;
  error: boolean;
}

/** One item_completed that ran inside an exec window, as a short label. */
function nestedItem(item: TraceValue): Nested | null {
  switch (item?.type) {
    case "Extension": {
      const q = item.query || item.action?.queries?.[0] || item.action?.query;
      return { label: collapse(q ? `${item.kind || "extension"}: ${q}` : item.kind || "extension"), error: false };
    }
    case "McpToolCall":
      return {
        label: collapse(`${item.server || "mcp"}.${item.tool || "tool"}`),
        error: item.status === "failed" || item.result?.isError === true,
      };
    case "CommandExecution": {
      const cmds: TraceValue[] = Array.isArray(item.parsed_cmd) ? item.parsed_cmd : [];
      const first = cmds[0];
      let label = "shell";
      if (first?.type === "read") label = `read ${baseName(first.name || first.path)}`;
      else if (first?.type === "search") label = `search ${first.query || ""}`.trim();
      else if (first?.type === "list_files") label = `list ${baseName(first.path) || "files"}`;
      const code = typeof item.exit_code === "number" ? item.exit_code : 0;
      return { label: collapse(label), error: code !== 0 || item.status === "failed" };
    }
    case "ImageView":
      return { label: collapse(`view ${baseName(item.path)}`), error: false };
    case "FileChange": {
      const files = Object.keys(item.changes || {});
      if (!files.length) return null;
      const more = files.length > 1 ? ` +${files.length - 1}` : "";
      return { label: collapse(`edit ${baseName(files[0])}${more}`), error: false };
    }
    default:
      return null;
  }
}

function delegationEntries(delegation: TraceValue): TraceValue[] {
  return Array.isArray(delegation?.subagents) ? delegation.subagents : [];
}

function build(events: Event[], delegation: TraceValue | null): TraceSpan[] {
  const ts = (i: number) => eventMs(events[i]) ?? 0;
  const hasRecords = events.some((e) => e.type === "token_usage_record");
  const hasPromptItems = events.some((e) => e.payload?.item?.type === "UserMessage");
  const kids = delegationEntries(delegation);

  // First pass: outputs by call id, and the subagent link items.
  const outputs = new Map<string, number>();
  const started = new Map<string, { thread: string; path?: string }>();
  const interacted = new Map<string, string>();
  const completedAt = new Map<string, number>();
  events.forEach((e, i) => {
    const p = e.payload;
    if (p?.type === "function_call_output" || p?.type === "custom_tool_call_output") outputs.set(p.call_id, i);
    const item = p?.item;
    if (item?.type !== "SubAgentActivity") return;
    if (item.kind === "started") started.set(item.id, { thread: item.agent_thread_id, path: item.agent_path });
    else if (item.kind === "interacted") interacted.set(item.id, item.agent_thread_id);
    else if (item.kind === "completed") completedAt.set(item.agent_thread_id, Math.max(completedAt.get(item.agent_thread_id) ?? 0, ts(i)));
  });

  const roots: TraceSpan[] = [];
  let seq = 0;
  const nextId = (prefix: string) => `codex-${prefix}-${seq++}`;

  let turn: TraceSpan | null = null;
  let promptCount = 0;
  let model = "";
  let boundary = 0; // latest prompt / tool output / turn start
  let lastRecord = 0;
  let pending: TraceSpan[] = [];
  let text = "";
  // Per-response content: response_item messages are canonical, AgentMessage items mirror them.
  let respMsgs: TraceValue[] = [];
  let itemMsgs: TraceValue[] = [];
  let thoughts: TraceValue[] = [];
  let lastEventTs = 0;
  const nested = new Map<string, Nested[]>(); // exec span id -> items run inside it
  const execSpans: Array<{ span: TraceSpan; callIdx: number; outIdx: number }> = [];

  const closeTurn = (end: number) => {
    if (!turn) return;
    flushOrphans(end);
    turn.end = Math.max(end, turn.start);
    turn = null;
  };

  const ensureTurn = (i: number): TraceSpan => {
    if (turn) return turn;
    const t = ts(i);
    turn = {
      id: nextId("turn"), kind: "turn", title: "Agent turn", start: t, end: t, children: [],
      eventIndex: i, turnKind: "notification",
    };
    roots.push(turn);
    boundary = t;
    return turn;
  };

  const llmSpan = (i: number, end: number, tokens: SpanTokens | undefined): TraceSpan => {
    const start = Math.min(end, Math.max(lastRecord, boundary));
    const span: TraceSpan = {
      id: nextId("llm"), kind: "llm", title: model || "model", start, end,
      children: pending, tokens, eventIndex: i, approxStart: true,
    };
    if (text) span.label = collapse(text);
    const output = joinBlocks(respMsgs.length ? respMsgs : itemMsgs);
    const reasoning = joinBlocks(thoughts);
    if (output !== undefined || reasoning !== undefined) {
      span.content = {};
      if (reasoning !== undefined) span.content.reasoning = reasoning;
      if (output !== undefined) span.content.output = output;
    }
    return span;
  };

  // Tool calls or text that never got a usage record (aborted turn).
  const flushOrphans = (end: number) => {
    if (!turn || (!pending.length && !text && !respMsgs.length && !itemMsgs.length && !thoughts.length)) return;
    const first = pending[0]?.start ?? end;
    turn.children.push(llmSpan(pending[0]?.eventIndex ?? turn.eventIndex ?? 0, Math.max(first, end), undefined));
    pending = [];
    text = "";
    respMsgs = [];
    itemMsgs = [];
    thoughts = [];
  };

  const closeLlm = (i: number, tokens: SpanTokens | undefined) => {
    const t = ensureTurn(i);
    const end = ts(i);
    t.children.push(llmSpan(i, end, tokens));
    lastRecord = end;
    pending = [];
    text = "";
    respMsgs = [];
    itemMsgs = [];
    thoughts = [];
  };

  const toolSpan = (e: Event, i: number): TraceSpan => {
    const p = e.payload;
    const args = parseArgs(p.arguments ?? p.input);
    const start = ts(i);
    const outIdx = outputs.get(p.call_id);
    const end = outIdx !== undefined ? ts(outIdx) : start;
    const name: string = p.name || "tool";
    const out = outIdx !== undefined ? outputText(events[outIdx].payload?.output) : "";
    const failed = outIdx !== undefined && codexOutputFailed(out);
    const base: TraceSpan = {
      id: nextId(name === "spawn_agent" ? "agent" : "tool"), kind: "tool", title: name,
      start, end: Math.max(start, end), children: [], eventIndex: i,
    };
    if (failed) base.error = true;
    const rawInput = p.type === "custom_tool_call" ? p.input : readableArgs(args);
    const content: NonNullable<TraceSpan["content"]> = {};
    if (rawInput && (typeof rawInput === "string" || Object.keys(rawInput).length)) content.input = rawInput;
    if (outIdx !== undefined) content.output = events[outIdx].payload?.output;
    if (content.input !== undefined || content.output !== undefined) base.content = content;

    if (name === "spawn_agent") {
      const taskName = String(args.task_name || "");
      const link = started.get(p.call_id);
      let childId = link?.thread;
      if (!childId && outIdx !== undefined) {
        // Older rollouts: match the returned agent path against the delegation list.
        const path = parseArgs(out).task_name;
        childId = kids.find((k) => path && k.agent_path === path)?.child_session_id;
      }
      const entry = kids.find((k) => k.child_session_id === childId);
      const finished = childId ? completedAt.get(childId) : undefined;
      base.kind = "agent";
      base.title = String(entry?.agent_role || taskName || "subagent");
      if (taskName) base.label = collapse(taskName);
      base.end = Math.max(base.end, finished ?? 0);
      base.agent = {
        agentType: base.title, childId, callStart: start, callEnd: Math.max(start, end),
        background: true, loaded: false,
      };
      return base;
    }

    if (name === "send_message" || name === "followup_task") {
      if (args.target) base.label = collapse(`to ${args.target}`);
      const resumed = interacted.get(p.call_id);
      if (resumed) base.resumes = resumed;
      return base;
    }

    if (name === "exec") {
      if (outIdx !== undefined) execSpans.push({ span: base, callIdx: i, outIdx });
      return base;
    }
    const label = toolLabel(args);
    if (label) base.label = label;
    return base;
  };

  events.forEach((e, i) => {
    const p = e.payload;
    const t = ts(i);
    if (t) lastEventTs = t;

    if (p?.type === "thread_settings_applied") {
      model = p.thread_settings?.model || model;
      return;
    }
    if (p?.type === "task_started") {
      closeTurn(lastEventTs);
      turn = {
        id: nextId("turn"), kind: "turn", title: "Agent turn", start: t, end: t, children: [],
        eventIndex: i, turnKind: "notification",
      };
      roots.push(turn);
      boundary = t;
      return;
    }
    if (p?.type === "task_complete" || p?.type === "turn_aborted") {
      if (turn) closeTurn(t);
      return;
    }

    // Prompts. Newer rollouts carry UserMessage items; older ones only have
    // role=user response_items, which also hold injected context ("<...>").
    let prompt: string | null = null;
    if (p?.item?.type === "UserMessage") prompt = partsText(p.item.content);
    else if (!hasPromptItems && e.type === "response_item" && p?.type === "message" && p.role === "user") {
      const body = partsText(p.content).trim();
      if (body && !body.startsWith("<") && !body.startsWith("# AGENTS.md")) prompt = body;
    }
    if (prompt !== null) {
      const cur = ensureTurn(i);
      if (cur.turnKind !== "prompt") {
        cur.turnKind = "prompt";
        cur.title = `User prompt ${++promptCount}`;
        cur.label = collapse(prompt);
        cur.content = { input: p?.item?.content ?? p.content };
      }
      boundary = t;
      return;
    }

    if (p?.type === "function_call" || p?.type === "custom_tool_call") {
      ensureTurn(i);
      const span = toolSpan(e, i);
      pending.push(span);
    } else if (p?.type === "function_call_output" || p?.type === "custom_tool_call_output") {
      boundary = Math.max(boundary, t);
    } else if (p?.item && p.item.type !== "UserMessage") {
      // Items that ran inside an exec call's window label that call.
      const open = execSpans.find((x) => x.callIdx < i && i < x.outIdx);
      const n = open ? nestedItem(p.item) : null;
      if (open && n) nested.set(open.span.id, [...(nested.get(open.span.id) || []), n]);
      if (p.item.type === "AgentMessage") {
        if (!text) text = partsText(p.item.content);
        if (!isCipher(partsText(p.item.content))) itemMsgs.push(p.item.content);
      } else if (p.item.type === "Reasoning" && Array.isArray(p.item.summary_text) && p.item.summary_text.length) {
        thoughts.push(p.item.summary_text);
      }
    } else if (e.type === "response_item" && p?.type === "message" && p.role === "assistant") {
      text = partsText(p.content) || text;
      if (!isCipher(partsText(p.content))) respMsgs.push(p.content);
    }

    if (e.type === "token_usage_record") {
      closeLlm(i, codexTokens(p?.usage));
    } else if (!hasRecords && (e as TraceValue)._tt_tokens) {
      closeLlm(i, codexTokens((e as TraceValue)._tt_tokens));
    }
  });
  closeTurn(lastEventTs);

  // Label exec calls from what ran inside them.
  for (const { span } of execSpans) {
    const items = nested.get(span.id);
    if (!items?.length) continue;
    const uniq = [...new Set(items.map((x) => x.label))];
    span.label = collapse(uniq.slice(0, 3).join("; ") + (uniq.length > 3 ? ` +${uniq.length - 3}` : ""), LABEL_MAX);
    if (items.some((x) => x.error)) span.error = true;
  }
  return roots;
}

export const codexAdapter: HarnessAdapter = {
  timing: "real",
  build,
  childFetch(_sessionId: string, span: TraceSpan): ChildFetch | null {
    const id = span.agent?.childId;
    return id ? { path: `/sessions/${id}?agent=codex`, agent: "codex" } : null;
  },
};
