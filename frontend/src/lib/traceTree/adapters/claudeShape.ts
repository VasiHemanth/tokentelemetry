/**
 * Adapter for the harnesses whose traces are Claude-shaped: assistant events
 * carry message.content[] blocks (thinking / text / tool_use) and user events
 * carry tool_result blocks. Claude Code, DSH, Pi and Qoder differ only in the
 * details below, so one builder takes a per-harness profile.
 *
 * - claude: one model response is split over several events sharing
 *   message.id, with the same usage copied onto each, so group by id and count
 *   usage once. Subagents link to the delegation record by tool_use_id.
 * - dsh: no ids or usage. Its "subagent" tool acknowledges with
 *   "started subagent <uuid>", which is the delegation agent_id and the id of
 *   a full child session.
 * - pi: no ids, usage, is_error or subagents.
 * - qoder: no ids or usage. Delegation has credits but no times or tokens, so
 *   Agent calls link by description and are never drilled into.
 */
import type { Event, TraceValue } from "../../traceEvents";
import type { HarnessAdapter, ChildFetch } from "../index";
import type { SpanTokens, TraceSpan } from "../types";

type Shape = "claude" | "dsh" | "pi" | "qoder";

interface BuildOpts {
  /** Child traces open with the task prompt rather than a user prompt. */
  child?: boolean;
}

const LABEL_MAX = 120;
const BACKGROUND_SLACK_MS = 5000;
const AGENT_ID_RE = /\ba[0-9a-f]{16}\b/g;

function clean(text: unknown, max = LABEL_MAX): string | undefined {
  if (typeof text !== "string") return undefined;
  const t = text.replace(/\s+/g, " ").trim();
  if (!t) return undefined;
  return t.length > max ? `${t.slice(0, max - 3)}...` : t;
}

function eventTime(e: Event): number | undefined {
  if (typeof e.normalized_timestamp === "number") return e.normalized_timestamp;
  if (e.timestamp) {
    const t = Date.parse(e.timestamp);
    if (!Number.isNaN(t)) return t;
  }
  return undefined;
}

function parseTime(value: unknown): number | undefined {
  if (typeof value !== "string") return undefined;
  const t = Date.parse(value);
  return Number.isNaN(t) ? undefined : t;
}

function baseName(p: string): string {
  const parts = p.split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] || p;
}

function hostName(u: string): string | undefined {
  try {
    return new URL(u).hostname || undefined;
  } catch {
    return undefined;
  }
}

/** Short description of a tool call. Never the raw command, which can hold paths and secrets. */
function toolLabel(input: TraceValue): string | undefined {
  if (!input || typeof input !== "object") return undefined;
  const desc = clean(input.description);
  if (desc) return desc;
  for (const key of ["file_path", "path", "notebook_path"]) {
    if (typeof input[key] === "string" && input[key]) return clean(baseName(input[key]));
  }
  for (const key of ["query", "pattern"]) {
    const v = clean(input[key]);
    if (v) return v;
  }
  if (typeof input.url === "string") return hostName(input.url);
  return undefined;
}

function blocks(e: Event): TraceValue[] {
  const c = e.message?.content;
  return Array.isArray(c) ? c : [];
}

function userText(e: Event): string | undefined {
  const c = e.message?.content;
  if (typeof c === "string") return c;
  if (!Array.isArray(c)) return undefined;
  const texts = c.filter((b: TraceValue) => b?.type === "text" && typeof b.text === "string");
  return texts.length ? texts.map((b: TraceValue) => b.text).join("\n") : undefined;
}

function usageTokens(usage: TraceValue): SpanTokens | undefined {
  if (!usage || typeof usage !== "object") return undefined;
  return {
    input: Number(usage.input_tokens) || 0,
    output: Number(usage.output_tokens) || 0,
    cacheRead: Number(usage.cache_read_input_tokens) || 0,
    cacheWrite: Number(usage.cache_creation_input_tokens) || 0,
  };
}

function resultText(content: TraceValue): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content.map((b: TraceValue) => (typeof b?.text === "string" ? b.text : "")).join("\n");
  }
  return "";
}

interface DelegationEntry {
  agent_id?: string;
  agent_type?: string;
  description?: string;
  tool_use_id?: string;
  model?: string;
  tokens?: { total?: number };
  cost?: number;
  started_at?: string;
  ended_at?: string;
  tool_calls?: number;
  tool_errors?: number;
}

function buildSpans(shape: Shape, events: Event[], delegation: TraceValue | null, opts: BuildOpts = {}): TraceSpan[] {
  const subs: DelegationEntry[] = Array.isArray(delegation?.subagents) ? delegation.subagents : [];
  const hasDelegation = delegation != null;
  const byToolUse = new Map<string, DelegationEntry>();
  const byAgentId = new Map<string, DelegationEntry>();
  for (const s of subs) {
    if (s.tool_use_id) byToolUse.set(s.tool_use_id, s);
    if (s.agent_id) byAgentId.set(s.agent_id, s);
  }
  const usedByDescription = new Set<DelegationEntry>();
  const linked = new Set<TraceSpan>();

  const turns: TraceSpan[] = [];
  const llmById = new Map<string, TraceSpan>();
  const pending = new Map<string, { span: TraceSpan; callTime: number }>();

  let turn: TraceSpan | null = null;
  let llm: TraceSpan | null = null;
  let llmTime: number | undefined;
  let prevWasAssistant = false;
  let prevTime: number | undefined;
  let promptCount = 0;

  const isSpawnTool = (name: string) =>
    shape === "dsh" ? name === "subagent" : shape === "pi" ? false : name === "Agent" || name === "Task";

  const startTurn = (index: number, t: number, kind: "prompt" | "notification", label?: string): TraceSpan => {
    const isTask = kind === "prompt" && opts.child && promptCount === 0;
    if (kind === "prompt") promptCount += 1;
    const span: TraceSpan = {
      id: `turn-${index}`,
      kind: "turn",
      title: kind === "notification" ? "Notification" : isTask ? "Task" : `User prompt ${promptCount}`,
      label,
      start: t,
      end: t,
      children: [],
      eventIndex: index,
      turnKind: kind,
    };
    turns.push(span);
    turn = span;
    llm = null;
    return span;
  };

  const touchTurn = (t: number) => {
    if (turn && t > turn.end) turn.end = t;
  };

  events.forEach((e, index) => {
    if (e.type !== "user" && e.type !== "assistant") return;
    const t = eventTime(e) ?? prevTime ?? 0;
    const content = blocks(e);

    if (e.type === "user") {
      const results = content.filter((b: TraceValue) => b?.type === "tool_result");
      if (results.length) {
        touchTurn(t);
        for (const r of results) {
          const hit = pending.get(r.tool_use_id);
          if (!hit) continue;
          pending.delete(r.tool_use_id);
          closeTool(hit.span, hit.callTime, t, r);
        }
        prevTime = t;
        prevWasAssistant = false;
        return;
      }

      const text = userText(e);
      prevTime = t;
      prevWasAssistant = false;
      if (text == null || !text.trim()) return;
      const trimmed = text.trimStart();
      if (trimmed.startsWith("<local-command-") || trimmed.startsWith("<command-name>")) return;
      // A skill body is injected as user text mid-turn; it is not a new prompt.
      if (trimmed.startsWith("Base directory for this skill")) {
        touchTurn(t);
        return;
      }
      const origin = (e as TraceValue).origin?.kind;
      const isNotice =
        trimmed.startsWith("<task-notification>") || origin === "task-notification" || origin === "peer";
      if (isNotice) {
        const span = startTurn(index, t, "notification", clean(summaryOf(trimmed)));
        const ids = trimmed.match(AGENT_ID_RE) || [];
        const known = ids.find((id) => byAgentId.has(id));
        const from = /\bfrom="(a[0-9a-f]{16})"/.exec(trimmed)?.[1];
        const id = from || known || ids[0];
        if (id) span.notifiedBy = id;
      } else {
        startTurn(index, t, "prompt", clean(text));
      }
      return;
    }

    // assistant
    if (!turn) startTurn(index, t, "prompt");
    const t0 = turn as TraceSpan;
    const msg = e.message || {};
    const id: string | undefined = typeof msg.id === "string" ? msg.id : undefined;

    let span: TraceSpan | undefined;
    if (id) span = llmById.get(id);
    else if (prevWasAssistant && llm && llmTime === t) span = llm;

    if (!span) {
      span = {
        id: `llm-${index}`,
        kind: "llm",
        title: clean(msg.model, 60) || "assistant",
        start: Math.min(prevTime ?? t, t),
        end: t,
        children: [],
        eventIndex: index,
        approxStart: true,
      };
      t0.children.push(span);
      if (id) llmById.set(id, span);
    }
    llm = span;
    llmTime = t;
    prevWasAssistant = true;
    if (t > span.end) span.end = t;
    touchTurn(t);

    // Usage is copied onto every event of one message; keep the fullest copy once.
    const tokens = shape === "claude" ? usageTokens(msg.usage) : undefined;
    if (tokens && (!span.tokens || tokens.output >= span.tokens.output)) span.tokens = tokens;

    content.forEach((b: TraceValue, bi: number) => {
      if (b?.type === "text" && !span!.label) span!.label = clean(b.text);
      if (b?.type !== "tool_use" || !b.id) return;
      const name = String(b.name || "tool");
      const input = b.input || {};
      let tool: TraceSpan;
      if (isSpawnTool(name)) {
        tool = spawnSpan(`agent-${index}-${bi}`, name, b, input, index, t);
      } else {
        tool = {
          id: `tool-${index}-${bi}`,
          kind: "tool",
          title: name,
          label: toolLabel(input),
          start: t,
          end: t,
          children: [],
          eventIndex: index,
        };
        if (name === "SendMessage") {
          const to = input.to ?? input.recipient;
          if (typeof to === "string" && to) tool.resumes = to;
        }
      }
      span!.children.push(tool);
      pending.set(b.id, { span: tool, callTime: t });
    });
    prevTime = t;
  });

  function summaryOf(text: string): string {
    const m = /<summary>([\s\S]*?)<\/summary>/.exec(text);
    return m ? m[1] : text.replace(/<[^>]+>/g, " ");
  }

  function spawnSpan(id: string, name: string, block: TraceValue, input: TraceValue, index: number, t: number): TraceSpan {
    let entry: DelegationEntry | undefined;
    if (shape === "claude") entry = byToolUse.get(block.id);
    else if (shape === "qoder") {
      entry = subs.find((s) => !usedByDescription.has(s) && s.description && s.description === input.description);
      if (entry) usedByDescription.add(entry);
    }
    const desc = clean(input.description);
    const span: TraceSpan = {
      id,
      kind: "agent",
      title: entry?.agent_type || input.subagent_type || name,
      label: desc,
      start: t,
      end: t,
      children: [],
      eventIndex: index,
      agent: { agentType: entry?.agent_type || input.subagent_type || name, callStart: t, loaded: false },
    };
    if (entry) {
      linked.add(span);
      fillFromEntry(span, entry);
    } else if (hasDelegation && shape === "claude") span.error = true;
    // dsh links once the acknowledgement reveals the child id.
    return span;
  }

  function fillFromEntry(span: TraceSpan, entry: DelegationEntry) {
    const a = span.agent!;
    if (entry.agent_type) {
      a.agentType = entry.agent_type;
      span.title = entry.agent_type;
    }
    if (entry.agent_id) a.childId = entry.agent_id;
    if (entry.model) a.model = entry.model;
    // Qoder reports credits instead of tokens and cost; zeros there mean unknown.
    const keepZero = shape !== "qoder";
    const total = entry.tokens?.total;
    if (typeof total === "number" && (keepZero || total > 0)) a.totalTokens = total;
    if (typeof entry.cost === "number" && (keepZero || entry.cost > 0)) a.cost = entry.cost;
    if (typeof entry.tool_calls === "number") a.toolCalls = entry.tool_calls;
    if (typeof entry.tool_errors === "number") a.toolErrors = entry.tool_errors;
    const s = parseTime(entry.started_at);
    const en = parseTime(entry.ended_at);
    if (s != null) span.start = s;
    if (en != null) span.end = Math.max(en, span.start);
  }

  function closeTool(span: TraceSpan, callTime: number, t: number, result: TraceValue) {
    if (result.is_error) span.error = true;
    if (span.kind !== "agent") {
      span.end = Math.max(t, callTime);
      return;
    }
    const a = span.agent!;
    a.callEnd = t;
    if (shape === "dsh") {
      const m = /started subagent (\S+)/.exec(resultText(result.content));
      const entry = m ? byAgentId.get(m[1]) : undefined;
      if (m) a.childId = m[1];
      span.start = callTime;
      span.end = t;
      if (entry) {
        linked.add(span);
        fillFromEntry(span, entry);
      }
      // The call returns within milliseconds while the child keeps running.
      a.background = true;
      if (span.end < span.start) span.end = span.start;
      return;
    }
    // Unlinked calls, and qoder (no times in its delegation), span the call window.
    if (!linked.has(span) || shape === "qoder") {
      span.start = callTime;
      span.end = Math.max(t, callTime);
      return;
    }
    const ended = parseTime(subs.find((s) => s.agent_id === a.childId)?.ended_at);
    if (ended != null) a.background = t < ended - BACKGROUND_SLACK_MS;
  }

  return turns;
}

function childFetchFor(shape: Shape) {
  return (sessionId: string, span: TraceSpan): ChildFetch | null => {
    const id = span.agent?.childId;
    if (!id) return null;
    if (shape === "claude") return { path: `/sessions/${sessionId}/subagents/${id}/trace?agent=claude`, agent: "claude" };
    if (shape === "dsh") return { path: `/sessions/${id}?agent=dsh`, agent: "dsh" };
    return null;
  };
}

export function claudeShapeAdapter(agent: Shape): HarnessAdapter {
  return {
    timing: "real",
    build: (events, delegation) => buildSpans(agent, events, delegation),
    childFetch: childFetchFor(agent),
    buildChild: (events) => buildSpans(agent, events, null, { child: true }),
  };
}
