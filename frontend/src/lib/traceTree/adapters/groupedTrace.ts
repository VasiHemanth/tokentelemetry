/**
 * Shared builder for harnesses whose trace is a flat list of user / assistant /
 * assistant_thinking / tool_call / tool_result events with no message ids and no
 * token counts (Hermes, Prime). One model response is the run of assistant,
 * thinking and tool_call events that share a timestamp; a result closes the tool
 * span of the call it answers.
 */
import type { Event, TraceValue } from "../../traceEvents";
import type { TraceSpan } from "../types";
import { clip, eventTime } from "./simpleLabels";

export interface GroupedOptions {
  /** How a result finds its call: by callID, or the oldest unpaired call of the same tool name. */
  pair: "callId" | "toolName";
  /** Injected user text (notifications, system notes) must not count as a prompt. */
  isNotification(text: string): boolean;
  describe(payload: TraceValue): { title: string; label?: string };
  isError(content: unknown): boolean;
}

export function buildGroupedTrace(events: Event[], options: GroupedOptions): TraceSpan[] {
  const firstTime = events.map(eventTime).find((t) => t !== undefined) ?? 0;
  const prefix = firstTime.toString(36);
  const spans: TraceSpan[] = [];
  const byId = new Map<string, TraceSpan>();
  const byName = new Map<string, TraceSpan[]>();

  let turn: TraceSpan | null = null;
  let llm: TraceSpan | null = null;
  let llmTime = -1;
  let promptCount = 0;
  let lastTime = firstTime;
  let text = "";
  let thought = "";

  const closeLlm = () => {
    if (llm) llm.label = clip(text || thought) || undefined;
    llm = null;
    text = "";
    thought = "";
  };

  const closeTurn = () => {
    closeLlm();
    if (!turn) return;
    for (const child of turn.children) turn.end = Math.max(turn.end, child.end, ...child.children.map((c) => c.end));
    turn = null;
  };

  const startTurn = (index: number, time: number, kind: "prompt" | "notification", body: string) => {
    closeTurn();
    if (kind === "prompt") promptCount += 1;
    turn = {
      id: `${prefix}:t${index}`,
      kind: "turn",
      title: kind === "prompt" ? `User prompt ${promptCount}` : "Notification",
      label: clip(body) || undefined,
      start: time,
      end: time,
      children: [],
      eventIndex: index,
      turnKind: kind,
    };
    spans.push(turn);
  };

  events.forEach((event, index) => {
    const time = eventTime(event) ?? lastTime;
    const payload = event.payload ?? {};

    if (event.type === "user") {
      const body = typeof payload.content === "string" ? payload.content : "";
      startTurn(index, time, options.isNotification(body) ? "notification" : "prompt", body);
    } else if (event.type === "assistant" || event.type === "assistant_thinking" || event.type === "tool_call") {
      if (!turn) startTurn(index, time, "notification", "");
      if (!llm || time !== llmTime) {
        closeLlm();
        llm = {
          id: `${prefix}:l${index}`,
          kind: "llm",
          title: "Model response",
          start: Math.min(lastTime, time),
          end: time,
          children: [],
          eventIndex: index,
          approxStart: true,
        };
        llmTime = time;
        turn!.children.push(llm);
      }
      if (event.type === "assistant") text = String(payload.content ?? "") || text;
      else if (event.type === "assistant_thinking") thought = String(payload.text ?? "") || thought;
      else {
        const { title, label } = options.describe(payload);
        const span: TraceSpan = {
          id: `${prefix}:x${index}`,
          kind: "tool",
          title,
          label,
          start: time,
          end: time,
          children: [],
          eventIndex: index,
        };
        llm.children.push(span);
        if (options.pair === "callId") {
          if (payload.callID) byId.set(String(payload.callID), span);
        } else {
          const queue = byName.get(String(payload.tool)) ?? [];
          queue.push(span);
          byName.set(String(payload.tool), queue);
        }
      }
    } else if (event.type === "tool_result") {
      const span = options.pair === "callId"
        ? byId.get(String(payload.callID))
        : byName.get(String(payload.tool))?.shift();
      if (span) {
        span.end = Math.max(span.start, time);
        if (options.isError(payload.content)) span.error = true;
      }
    }
    lastTime = time;
  });
  closeTurn();
  return spans;
}
