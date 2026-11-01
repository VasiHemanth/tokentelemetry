import type { TraceSpan } from "./types";

export interface ConversationRow { span: TraceSpan; depth: number }

/** Preserve trace order; child recordings enter the reader only when expanded. */
export function conversationRows(roots: TraceSpan[], expanded: ReadonlySet<string>): ConversationRow[] {
  const rows: ConversationRow[] = [];
  const visit = (span: TraceSpan, depth: number) => {
    rows.push({ span, depth });
    if (span.kind === "agent" && !expanded.has(span.id)) return;
    span.children.forEach(child => visit(child, depth + (span.kind === "agent" ? 1 : 0)));
  };
  roots.forEach(span => visit(span, 0));
  return rows;
}

export function conversationLayout(rows: ConversationRow[], heights: ReadonlyMap<string, number>) {
  const offsets: number[] = [];
  let total = 0;
  for (const { span } of rows) {
    offsets.push(total);
    total += heights.get(span.id) ?? (span.kind === "turn" ? 180 : span.kind === "llm" ? 240 : span.kind === "agent" ? 260 : 440);
  }
  return { offsets, total };
}

/** Binary search is independent of payload size and handles estimated heights. */
export function conversationRowAt(offsets: number[], position: number): number {
  if (!offsets.length) return -1;
  let lo = 0, hi = offsets.length - 1;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    if (offsets[mid] <= position) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}


/** Pixel overscan remains useful even when a recording has many compact rows. */
export function conversationWindow(offsets: number[], top: number, height: number) {
  if (!offsets.length) return { first: 0, last: 0 };
  const overscan = Math.max(1000, height * 2);
  return {
    first: Math.max(0, conversationRowAt(offsets, top - overscan) - 1),
    last: Math.min(offsets.length, conversationRowAt(offsets, top + height + overscan) + 2),
  };
}
