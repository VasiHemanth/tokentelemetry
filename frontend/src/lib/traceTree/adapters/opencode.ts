/**
 * OpenCode and ZCode trace -> span tree. Both write the same shape: user /
 * assistant / assistant_thinking events plus tool_call events that already merge
 * the call and its result (state.time has the real start and end).
 *
 * There are no message ids. Instead one event per model step carries a top-level
 * `tokens` object, so the run of events up to and including that event is one
 * llm span. ZCode also injects text as user events (task notifications, todo
 * reminders); only real prompts start a "prompt" turn.
 */
import type { Event, TraceValue } from "../../traceEvents";
import type { HarnessAdapter, ChildFetch } from "../index";
import type { SpanTokens, TraceSpan } from "../types";
import { clip, contentOf, eventTime, joinText, toolLabel } from "./simpleLabels";

type Harness = "opencode" | "zcode";

const AGENT_TOOLS = new Set(["task", "agent"]);
const ZCODE_CHILD_ID = /agentId: (agent_[0-9a-f-]+)/;

type UserKind = "prompt" | "notification" | "fold";

function classifyUser(text: string): UserKind {
  if (text.startsWith("<task-notification>")) return "notification";
  if (text.startsWith("The TodoWrite tool hasn't been used recently") || text.startsWith("<system-reminder>")) return "fold";
  return "prompt";
}

function userText(event: Event): string {
  const content = event.payload?.content;
  return typeof content === "string" ? content : "";
}

function toTokens(raw: TraceValue): SpanTokens | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const reasoning = Number(raw.reasoning) || 0;
  const output = (Number(raw.output) || 0) + reasoning; // reasoning is billed as output
  const cacheRead = Number(raw.cache?.read) || 0;
  const cacheWrite = Number(raw.cache?.write) || 0;
  let input = Number(raw.input) || 0;
  // OpenCode keeps cache apart from input, ZCode folds it in. `total` shows which.
  const total = Number(raw.total);
  if (total > 0 && Math.abs(total - (input + output + cacheRead + cacheWrite)) > Math.abs(total - (input + output))) {
    input = Math.max(0, input - cacheRead - cacheWrite);
  }
  return { input, output, cacheRead, cacheWrite };
}

/** Child session ids from a delegation payload that list a first-event time, for the ZCode fallback. */
function delegationStarts(delegation: TraceValue | null): Array<{ id: string; start: number }> {
  const rows = delegation?.children;
  if (!Array.isArray(rows)) return [];
  const out: Array<{ id: string; start: number }> = [];
  for (const row of rows) {
    const id = row?.child_session_id ?? row?.id;
    const raw = row?.first_event_ts ?? row?.started_at ?? row?.start;
    const start = typeof raw === "number" ? raw : Date.parse(raw);
    if (typeof id === "string" && Number.isFinite(start)) out.push({ id, start });
  }
  return out;
}

export function opencodeAdapter(agent: Harness): HarnessAdapter {
  function childIdOf(state: TraceValue): string | undefined {
    const direct = state?.metadata?.sessionId;
    if (typeof direct === "string" && direct) return direct;
    if (agent === "zcode") {
      const match = typeof state?.output === "string" ? ZCODE_CHILD_ID.exec(state.output) : null;
      if (match) return `sess_subagent_${match[1]}`;
    }
    return undefined;
  }

  function build(events: Event[], delegation: TraceValue | null): TraceSpan[] {
    const firstTime = events.map(eventTime).find((t) => t !== undefined) ?? 0;
    const prefix = firstTime.toString(36);
    const spans: TraceSpan[] = [];
    const claimed = new Set<string>();
    const unmatched: Array<{ span: TraceSpan; callStart: number }> = [];

    let turn: TraceSpan | null = null;
    let promptCount = 0;
    let run: number[] = [];
    let runPrev = firstTime;
    let lastTime = firstTime;
    let toolFloor = 0;

    const endTurn = () => {
      if (!turn) return;
      for (const child of turn.children) turn.end = Math.max(turn.end, child.end, ...child.children.map((c) => c.end));
      turn = null;
    };

    const startTurn = (index: number, time: number, kind: "prompt" | "notification", text: string) => {
      endTurn();
      if (kind === "prompt") promptCount += 1;
      turn = {
        id: `${prefix}:t${index}`,
        kind: "turn",
        title: kind === "prompt" ? `User prompt ${promptCount}` : "Notification",
        label: clip(text) || undefined,
        content: contentOf(text),
        start: time,
        end: time,
        children: [],
        eventIndex: index,
        turnKind: kind,
      };
      spans.push(turn);
      toolFloor = 0;
    };

    const toolSpan = (index: number, event: Event, fallbackTime: number): TraceSpan => {
      const payload = event.payload ?? {};
      const state = payload.state ?? {};
      const name = String(payload.tool ?? "tool");
      const start = Number(state.time?.start) || fallbackTime;
      const end = Math.max(start, Number(state.time?.end) || start);
      const error = state.status === "error";
      const input = state.input;
      const base: TraceSpan = {
        id: `${prefix}:x${index}`,
        kind: "tool",
        title: name,
        start,
        end,
        children: [],
        eventIndex: index,
        content: contentOf(input, error ? state.error : state.output),
        ...(error ? { error: true } : {}),
      };
      if (AGENT_TOOLS.has(name.toLowerCase())) {
        const description = typeof input?.description === "string" ? input.description : "";
        const type = String(input?.subagent_type || description || name);
        const childId = childIdOf(state);
        const model = state.metadata?.model?.modelID;
        const span: TraceSpan = {
          ...base,
          kind: "agent",
          title: type,
          content: contentOf(input?.prompt ?? input, error ? state.error : state.output),
          label: description && description !== type ? clip(description) : undefined,
          agent: {
            agentType: type,
            childId,
            callStart: start,
            callEnd: end,
            background: false,
            ...(typeof model === "string" ? { model } : {}),
            loaded: false,
          },
        };
        if (childId) claimed.add(childId);
        else if (!error) unmatched.push({ span, callStart: start });
        return span;
      }
      const label = toolLabel(input) ?? (name === "bash" ? undefined : clip(state.title) || undefined);
      return { ...base, label };
    };

    const flushRun = (tokens: TraceValue) => {
      if (!turn || run.length === 0) {
        run = [];
        return;
      }
      const children: TraceSpan[] = [];
      let end = runPrev;
      let toolEnd = 0;
      const texts: string[] = [];
      const thoughts: string[] = [];
      for (const index of run) {
        const event = events[index];
        const time = eventTime(event) ?? end;
        end = Math.max(end, time);
        if (event.type === "tool_call") {
          const span = toolSpan(index, event, time);
          toolEnd = Math.max(toolEnd, span.end);
          children.push(span);
        } else if (event.type === "assistant") {
          texts.push(String(event.payload?.content ?? ""));
        } else if (event.type === "assistant_thinking") {
          thoughts.push(String(event.payload?.text ?? ""));
        }
      }
      // The model starts after the previous step's tools returned, not when they were requested.
      const start = Math.min(Math.max(runPrev, toolFloor), end);
      const llm: TraceSpan = {
        id: `${prefix}:l${run[0]}`,
        kind: "llm",
        title: "Model response",
        label: clip(texts.filter(Boolean).pop() || thoughts.filter(Boolean).pop()) || undefined,
        content: contentOf(undefined, joinText(texts), joinText(thoughts)),
        start,
        end,
        children,
        eventIndex: run[0],
        approxStart: true,
        tokens: toTokens(tokens),
      };
      turn.children.push(llm);
      toolFloor = Math.max(toolFloor, toolEnd);
      run = [];
    };

    events.forEach((event, index) => {
      const time = eventTime(event) ?? lastTime;
      if (event.type === "user") {
        const text = userText(event);
        const kind = classifyUser(text);
        if (kind !== "fold") {
          flushRun((event as TraceValue).tokens);
          startTurn(index, time, kind, text);
        }
        lastTime = time;
        return;
      }
      if (event.type !== "assistant" && event.type !== "assistant_thinking" && event.type !== "tool_call") {
        lastTime = time;
        return;
      }
      if (!turn) startTurn(index, time, "notification", "");
      if (run.length === 0) runPrev = lastTime;
      run.push(index);
      lastTime = time;
      if ((event as TraceValue).tokens) flushRun((event as TraceValue).tokens);
    });
    flushRun(undefined);
    endTurn();

    // ZCode only: an Agent call whose output named no child, matched by start time.
    const starts = delegationStarts(delegation).filter((row) => !claimed.has(row.id));
    for (const { span, callStart } of unmatched) {
      const hit = starts.find((row) => !claimed.has(row.id) && row.start >= callStart && row.start - callStart <= 2000);
      if (hit && span.agent) {
        span.agent.childId = hit.id;
        claimed.add(hit.id);
      }
    }
    return spans;
  }

  function childFetch(_sessionId: string, span: TraceSpan): ChildFetch | null {
    const id = span.agent?.childId;
    return id ? { path: `/sessions/${encodeURIComponent(id)}?agent=${agent}`, agent } : null;
  }

  return { timing: "real", build, childFetch };
}
