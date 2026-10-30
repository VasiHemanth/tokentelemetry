import type { TraceSpan } from "./types";

export type WorkspaceView = "conversation" | "execution" | "events";

export interface ConversationGroup {
  prompt: TraceSpan | null;
  notifications: TraceSpan[];
}

/** Reports are evidence within the conversation, not additional user requests. */
export function conversationGroups(roots: TraceSpan[]): ConversationGroup[] {
  const groups: ConversationGroup[] = [];
  for (const span of roots) {
    if (span.kind === "turn" && span.turnKind !== "notification") {
      groups.push({ prompt: span, notifications: [] });
    } else {
      if (!groups.length) groups.push({ prompt: null, notifications: [] });
      groups[groups.length - 1].notifications.push(span);
    }
  }
  return groups;
}

/** Keep the owner's narrative and handoffs; never inline a child's entire trace. */
export function conversationSignals(turn: TraceSpan) {
  const visible: TraceSpan[] = [];
  const tools: TraceSpan[] = [];
  const models: TraceSpan[] = [];
  const visit = (span: TraceSpan) => {
    if (span.kind === "agent" || span.kind === "skill") {
      visible.push(span);
      return;
    }
    if (span.kind === "llm") {
      models.push(span);
      if (span.content?.output != null && span.content.output !== "") visible.push(span);
    } else if (span.kind === "tool") {
      if (span.error) visible.push(span);
      else tools.push(span);
    }
    span.children.forEach(visit);
  };
  turn.children.forEach(visit);
  return { visible, tools, models, modelCalls: models.length };
}

/** Fixed-height execution rows keep DOM work proportional to viewport size. */
export function windowRows(count: number, scroll: number, height: number, rowHeight: number, overscan = 8) {
  if (!count) return { start: 0, end: 0 };
  const visible = Math.max(1, Math.ceil(height / rowHeight));
  const first = Math.min(Math.max(0, Math.floor(scroll / rowHeight)), Math.max(0, count - visible));
  return { start: Math.max(0, first - overscan), end: Math.min(count, first + visible + overscan) };
}

export function readWorkspaceLocation(params: Pick<URLSearchParams, "get">): { view: WorkspaceView; span: string | null } {
  const view = params.get("view");
  return {
    view: view === "execution" || view === "events" ? view : "conversation",
    span: params.get("span")?.slice(0, 1024) || null,
  };
}

export function updateWorkspaceLocation(params: { toString(): string }, patch: { view?: WorkspaceView; span?: string | null }): URLSearchParams {
  const next = new URLSearchParams(params.toString());
  if (patch.view !== undefined) next.set("view", patch.view);
  if (patch.span === null) next.delete("span");
  else if (patch.span !== undefined) next.set("span", patch.span);
  return next;
}
