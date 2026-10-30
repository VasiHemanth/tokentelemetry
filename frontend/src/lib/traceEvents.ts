/**
 * Raw trace payload -> renderable events. Shared by the session page, its
 * subagent drill-in viewer, and the trace-tree adapters, so all of them filter
 * the same noise and see the same event indices.
 */

// Harnesses emit different event schemas. Keep that compatibility boundary
// explicit while the normalized Event shape remains intentionally permissive.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type TraceValue = any;

export interface Event {
  id?: string;
  type: string;
  role?: string;
  timestamp?: string;
  normalized_timestamp?: number;
  payload?: TraceValue;
  message?: TraceValue;
  attachment?: TraceValue;
  toolUseResult?: TraceValue;
  uuid?: string;
  content?: TraceValue;
  thoughts?: TraceValue[];
  toolCalls?: TraceValue[];
}

function codexVisibleSignatures(event: TraceValue): string[] {
  const payload = event?.payload;
  if (!payload || typeof payload !== "object") return [];

  const textSignature = (kind: string, value: unknown) => {
    const text = String(value ?? "").trim();
    return text ? `${kind}:${text}` : null;
  };

  if (event.type === "event_msg") {
    if (payload.type === "user_message") return [textSignature("user", payload.message)].filter(Boolean) as string[];
    if (payload.type === "agent_message") return [textSignature("assistant", payload.message)].filter(Boolean) as string[];
    if (payload.type === "agent_reasoning") return [textSignature("reasoning", payload.text)].filter(Boolean) as string[];
    return [];
  }

  if (event.type !== "response_item") return [];
  if (payload.type === "reasoning") {
    return (payload.summary || [])
      .filter((item: TraceValue) => item && typeof item === "object")
      .map((item: TraceValue) => textSignature("reasoning", item.text))
      .filter(Boolean) as string[];
  }
  if (payload.type !== "message" || !["user", "assistant"].includes(payload.role)) return [];

  const text = (payload.content || [])
    .filter((item: TraceValue) => item && ["input_text", "output_text"].includes(item.type))
    .map((item: TraceValue) => item.text || "")
    .join("");
  const signature = textSignature(payload.role, text);
  return signature ? [signature] : [];
}

function codexEventTimestamp(event: TraceValue): number | undefined {
  if (typeof event?.normalized_timestamp === "number") return event.normalized_timestamp;
  if (event?.timestamp) {
    const timestamp = Date.parse(event.timestamp);
    return Number.isNaN(timestamp) ? undefined : timestamp;
  }
  return undefined;
}

function dedupeCodexMirrors(events: TraceValue[]): TraceValue[] {
  const canonical = new Map<string, Array<{ index: number; timestamp?: number }>>();
  events.forEach((event, index) => {
    if (event.type !== "response_item") return;
    for (const signature of codexVisibleSignatures(event)) {
      const matches = canonical.get(signature) || [];
      matches.push({ index, timestamp: codexEventTimestamp(event) });
      canonical.set(signature, matches);
    }
  });

  return events.filter((event, index) => {
    if (event.type !== "event_msg") return true;
    const timestamp = codexEventTimestamp(event);
    const mirrored = codexVisibleSignatures(event).some((signature) =>
      (canonical.get(signature) || []).some((match) =>
        Math.abs(index - match.index) <= 4 &&
        (timestamp === undefined || match.timestamp === undefined || Math.abs(timestamp - match.timestamp) <= 100)
      )
    );
    return !mirrored;
  });
}

function collapseCodexReasoningSnapshots(events: TraceValue[]): TraceValue[] {
  const collapsed: TraceValue[] = [];
  for (const event of events) {
    const isReasoning = event?.type === "response_item" && event?.payload?.type === "reasoning";
    if (!isReasoning) {
      collapsed.push(event);
      continue;
    }

    const currentText = codexVisibleSignatures(event)
      .filter((signature) => signature.startsWith("reasoning:"))
      .map((signature) => signature.slice("reasoning:".length))
      .join("\n\n");
    if (!currentText) continue;

    let previousIndex = collapsed.length - 1;
    while (previousIndex >= 0 && collapsed[previousIndex]?.type === "event_msg" && collapsed[previousIndex]?.payload?.type === "token_count") {
      previousIndex -= 1;
    }

    const previous = previousIndex >= 0 ? collapsed[previousIndex] : null;
    if (previous?.type === "response_item" && previous?.payload?.type === "reasoning") {
      const previousText = codexVisibleSignatures(previous)
        .filter((signature) => signature.startsWith("reasoning:"))
        .map((signature) => signature.slice("reasoning:".length))
        .join("\n\n");
      if (previousText === currentText || previousText.startsWith(currentText) || currentText.startsWith(previousText)) {
        if (currentText.length >= previousText.length) collapsed[previousIndex] = event;
        continue;
      }
    }

    collapsed.push(event);
  }
  return collapsed;
}

/* Normalize a raw trace payload (session detail or subagent transcript) into
   renderable events — shared by the main trace fetch and the subagent
   drill-in viewer so both filter the same noise. */
export function normalizeTraceEvents(agent: string | null, data: TraceValue): Event[] {
  let evts: TraceValue[] = [];
  if (agent === "gemini" || agent === "antigravity") {
    evts = (data?.messages || []).map((m: TraceValue) => ({
      ...m,
      type: m.type === "gemini" ? "assistant" : m.type,
    }));
  } else {
    evts = Array.isArray(data) ? data : [];
  }
  if (data && typeof data === "object" && !Array.isArray(data) && data.error) {
    evts = [];
  }
  if (agent === "codex") {
    // Step-only enrichment must not modify the API records used by the event log.
    evts = evts.map((event: TraceValue) => ({ ...event }));
    // token_count events are filtered as noise, but they carry the turn's
    // usage — hand it to the preceding kept event for the per-step chip (#128).
    let lastKept: TraceValue = null;
    evts = evts.filter((e: TraceValue) => {
      if (e.type === "turn_context") return false;
      if (e.type === "event_msg" && e.payload?.type === "token_count") {
        const u = e.payload?.info?.last_token_usage;
        if (u && lastKept) lastKept._tt_tokens = u;
        return false;
      }
      lastKept = e;
      return true;
    });
    // Codex writes a canonical response_item and an event_msg projection for
    // the same visible turn. Keep the canonical event so the Step Index and
    // conversation cards are driven by one shared timeline.
    evts = collapseCodexReasoningSnapshots(dedupeCodexMirrors(evts));
  }
  if (agent === "claude" || agent === "cursor") {
    const NOISE_TYPES = new Set([
      "last-prompt", "permission-mode", "ai-title", "file-history-snapshot",
      "queue-operation", "attachment", "system",
    ]);
    evts = evts.filter((e: TraceValue) => {
      if (NOISE_TYPES.has(e.type)) return false;
      if (e.type === "user" && e.isMeta) return false;
      const c = e.message?.content;
      if (e.type === "user" && typeof c === "string" && c.startsWith("<local-command-")) return false;
      return true;
    });
  }
  return evts;
}
