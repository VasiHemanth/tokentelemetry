import { test } from "node:test";
import assert from "node:assert/strict";
import { splitSubagents, subagentSummary } from "./subagents";

const row = (id: string, parent?: string | null) => ({ id, parent_session_id: parent });

test("a child whose parent is in the list is hidden and counted against it", () => {
  const split = splitSubagents([row("p"), row("c1", "p"), row("c2", "p")]);
  assert.deepEqual(split.parents.map((s) => s.id), ["p"]);
  assert.equal(split.hiddenCount, 2);
  assert.equal(split.childCounts.get("p"), 2);
  assert.equal(split.all.length, 3, "all[] must stay untouched for totals");
});

test("a child whose parent is missing stays visible and counts against nobody", () => {
  // The branch live data never exercises: parent pruned, or predating the
  // store. Hiding these would drop the run from the feed entirely.
  const split = splitSubagents([row("a"), row("orphan", "gone")]);
  assert.deepEqual(split.parents.map((s) => s.id), ["a", "orphan"]);
  assert.equal(split.hiddenCount, 0);
  assert.equal(split.childCounts.get("gone"), undefined);
  assert.equal(split.childCounts.size, 0);
});

test("sessions with no parent are always visible", () => {
  const split = splitSubagents([row("a"), row("b", null), row("c", undefined)]);
  assert.equal(split.parents.length, 3);
  assert.equal(split.hiddenCount, 0);
});

test("input order is preserved so the caller keeps its own sort", () => {
  const split = splitSubagents([row("z"), row("kid", "z"), row("y"), row("x")]);
  assert.deepEqual(split.parents.map((s) => s.id), ["z", "y", "x"]);
});

test("a parent that is itself a child still counts its own children", () => {
  // depth >= 2: mid is hidden as a child of top, but still reports its own kid.
  const split = splitSubagents([row("top"), row("mid", "top"), row("leaf", "mid")]);
  assert.deepEqual(split.parents.map((s) => s.id), ["top"]);
  assert.equal(split.hiddenCount, 2);
  assert.equal(split.childCounts.get("top"), 1);
  assert.equal(split.childCounts.get("mid"), 1);
});

test("summary reads as total/real/delegated, and is absent when there are none", () => {
  assert.equal(subagentSummary(268, 225), "268 · 43 real · 225 delegated");
  assert.equal(subagentSummary(2, 1), "2 · 1 real · 1 delegated");
  assert.equal(subagentSummary(43, 0), null);
  assert.equal(subagentSummary(0, 0), null);
  // Never says "subagents": the project header's Subagents stat is a
  // different metric and must keep sole claim on the word.
  assert.ok(!subagentSummary(268, 225)!.includes("subagent"));
});
