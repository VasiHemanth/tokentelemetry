import { test } from "node:test";
import assert from "node:assert/strict";
import { conversationRows, conversationLayout, conversationRowAt, conversationWindow } from "./conversation";
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


test("pixel overscan covers several viewports even when rows are short", () => {
  const offsets = Array.from({ length: 100_000 }, (_, i) => i * 80);
  const window = conversationWindow(offsets, 40_000, 800);
  assert.ok(offsets[window.first] <= 38_400);
  assert.ok(offsets[window.last - 1] >= 42_400);
  assert.ok(window.last - window.first < 70, "DOM window remains bounded");
  const jumped = conversationWindow(offsets, 7_999_500, 800);
  assert.equal(jumped.last, offsets.length);
  assert.ok(offsets[jumped.first] <= 7_999_500);
  assert.deepEqual(conversationWindow([], 0, 800), { first: 0, last: 0 });
});
