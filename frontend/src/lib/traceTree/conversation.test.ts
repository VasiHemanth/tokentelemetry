import { test } from "node:test";
import assert from "node:assert/strict";
import { conversationRows, conversationLayout, conversationRowAt } from "./conversation";
import type { TraceSpan } from "./types";
const span = (id: string, kind: TraceSpan["kind"], children: TraceSpan[] = []): TraceSpan => ({ id, kind, title: id, start: 0, end: 1, children });

test("continuous reading preserves owner order, routine calls, and notification records", () => {
  const child = span("child", "agent", [span("child-turn", "turn", [span("child-reply", "llm")])]);
  const roots = [span("prompt", "turn", [span("model", "llm", [span("read", "tool"), child])]), span("report", "turn")];
  assert.deepEqual(conversationRows(roots, new Set()).map(r => r.span.id), ["prompt", "model", "read", "child", "report"]);
  const open = conversationRows(roots, new Set(["child"]));
  assert.deepEqual(open.map(r => r.span.id), ["prompt", "model", "read", "child", "child-turn", "child-reply", "report"]);
  assert.equal(open.find(r => r.span.id === "child-reply")?.depth, 1);
});

test("measured conversation offsets retain zero-position and reach the last item in a huge trace", () => {
  const rows = conversationRows(Array.from({ length: 100_000 }, (_, i) => span(String(i), "turn")), new Set());
  const layout = conversationLayout(rows, new Map([["0", 500], ["1", 100]]));
  assert.equal(layout.offsets[0], 0);
  assert.equal(layout.offsets[1], 500);
  assert.equal(layout.offsets[2], 600);
  assert.equal(conversationRowAt(layout.offsets, 499), 0);
  assert.equal(conversationRowAt(layout.offsets, 500), 1);
  assert.equal(conversationRowAt(layout.offsets, layout.total - 1), 99_999);
  assert.equal(conversationRowAt([], 0), -1);
});
