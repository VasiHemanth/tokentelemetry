import { test } from "node:test";
import assert from "node:assert/strict";
import type { TraceSpan } from "./types";
import { readWorkspaceLocation, updateWorkspaceLocation, windowRows } from "./workspace";
import { computeRollups } from "./tree";

function span(id: string, kind: TraceSpan["kind"], children: TraceSpan[] = [], extra: Partial<TraceSpan> = {}): TraceSpan {
  return { id, kind, title: id, start: 0, end: 1, children, ...extra };
}

test("row windows stay bounded on huge recordings, and reach the final row", () => {
  const first = windowRows(100_000, 0, 600, 36, 8);
  assert.ok(first.end - first.start <= 34);
  const last = windowRows(100_000, 100_000 * 36, 600, 36, 8);
  assert.equal(last.end, 100_000);
  assert.ok(last.start >= 99_970);
  assert.deepEqual(windowRows(0, 100, 600, 36), { start: 0, end: 0 });
});

test("workspace URLs preserve harness and back navigation, validate views, and encode child selection", () => {
  const query = new URLSearchParams("agent=codex&from=%2Fprojects&view=invalid");
  assert.deepEqual(readWorkspaceLocation(query), { view: "conversation", span: null });
  const next = updateWorkspaceLocation(query, { view: "execution", span: "agent-2/llm-1" });
  assert.equal(next.get("agent"), "codex");
  assert.equal(next.get("from"), "/projects");
  assert.deepEqual(readWorkspaceLocation(next), { view: "execution", span: "agent-2/llm-1" });
  assert.equal(updateWorkspaceLocation(next, { span: null }).has("span"), false);
  assert.equal(query.get("view"), "invalid");
});

test("unknown usage is distinct from recorded zero and mixed coverage", () => {
  const missing = span("missing", "llm");
  const zero = span("zero", "llm", [], { tokens: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } });
  const partial = span("partial", "turn", [missing, zero]);
  const rollups = computeRollups([partial]);
  assert.equal(rollups.get("missing")?.tokenState, "unavailable");
  assert.equal(rollups.get("zero")?.tokenState, "recorded");
  assert.equal(rollups.get("partial")?.tokenState, "partial");
});
