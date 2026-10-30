/**
 * Shared builder for harnesses whose trace is a flat list of user / assistant /
 * assistant_thinking / tool_call / tool_result events with no message ids and no
 * token counts (Hermes, Prime). One model response is the run of assistant,
 * thinking and tool_call events that share a timestamp; a result closes the tool
 * span of the call it answers.
 */
import type { Event, TraceValue } from "../../traceEvents";
import type { TraceSpan } from "../types";
import { clip, contentOf, eventTime, joinText } from "./simpleLabels";

export interface GroupedOptions {
  /** How a result finds its call: by callID, or the oldest unpaired call of the same tool name. */
  pair: "callId" | "toolName" | "callIdOrName";
  /** Injected user text (notifications, system notes) must not count as a prompt. */
  isNotification(text: string): boolean;
  describe(payload: TraceValue): { title: string; label?: string; input?: unknown };
  isError(content: unknown, payload: TraceValue): boolean;
  tokens?(usage: TraceValue): TraceSpan["tokens"];
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
  let llmMessageId: string | undefined;
  let promptCount = 0;
  let lastTime = firstTime;
  let texts: string[] = [];
  let thoughts: string[] = [];

  const closeLlm = () => {
    if (llm) {
      llm.label = clip(texts.filter(Boolean).pop() || thoughts.filter(Boolean).pop()) || undefined;
      llm.content = contentOf(undefined, joinText(texts), joinText(thoughts));
    }
    llm = null;
    texts = [];
    thoughts = [];
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
      content: contentOf(body),
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
      const messageId = typeof (event as TraceValue).messageID === "string" ? (event as TraceValue).messageID : undefined;
      if (!llm || time !== llmTime || (messageId !== undefined && llmMessageId !== undefined && messageId !== llmMessageId)) {
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
        llmMessageId = messageId;
        turn!.children.push(llm);
      }
      const meta = event as TraceValue;
      if (typeof meta.model === "string" && meta.model) llm.title = meta.model;
      if (options.tokens && meta.usage && typeof meta.usage === "object") llm.tokens = options.tokens(meta.usage);
      if (event.type === "assistant") texts.push(String(payload.content ?? ""));
      else if (event.type === "assistant_thinking") thoughts.push(String(payload.text ?? ""));
      else {
        const { title, label, input } = options.describe(payload);
        const span: TraceSpan = {
          id: `${prefix}:x${index}`,
          kind: "tool",
          title,
          label,
          content: contentOf(input),
          start: time,
          end: time,
          children: [],
          eventIndex: index,
        };
        llm.children.push(span);
        if (options.pair !== "toolName" && payload.callID) byId.set(String(payload.callID), span);
        if (options.pair !== "callId") {
          const queue = byName.get(String(payload.tool)) ?? [];
          queue.push(span);
          byName.set(String(payload.tool), queue);
        }
      }
    } else if (event.type === "tool_result") {
      const queue = byName.get(String(payload.tool));
      const span = options.pair === "callId" ? byId.get(String(payload.callID))
        : options.pair === "callIdOrName" && payload.callID ? byId.get(String(payload.callID))
        : queue?.shift();
      if (span && payload.callID) byId.delete(String(payload.callID));
      if (span && queue) { const i = queue.indexOf(span); if (i >= 0) queue.splice(i, 1); }
      if (span) {
        span.end = Math.max(span.start, time);
        span.content = contentOf(span.content?.input, payload.content);
        if (options.isError(payload.content, payload)) span.error = true;
      }
    }
    lastTime = time;
  });
  closeTurn();
  return spans;
}
