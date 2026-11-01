import { test } from "node:test";
import assert from "node:assert/strict";
import type { TraceSpan } from "./types";
import {
  agentBursts,
  buildIndex,
  computeRollups,
  defaultExpanded,
  expandAllIds,
  flattenVisible,
  isLazyAgent,
  mainTokens,
  ownWork,
  peakConcurrency,
  skillLanes,
  matchesFilter,
} from "./tree";

const MIN = 60_000;
const tok = (n: number) => ({ input: n, output: 0, cacheRead: 0, cacheWrite: 0 });

function span(id: string, kind: TraceSpan["kind"], start: number, end: number, extra: Partial<TraceSpan> = {}): TraceSpan {
  return { id, kind, title: id, start, end, children: [], ...extra };
}

function fixture() {
  const t1 = span("t1", "turn", 0, 10 * MIN, { turnKind: "prompt" });
  const l1 = span("l1", "llm", 0, MIN, { tokens: tok(100) });
  const tool = span("tool1", "tool", MIN, 2 * MIN, { error: true });
  const l2 = span("l2", "llm", 2 * MIN, 3 * MIN, { tokens: tok(50) });
  const a1l = span("a1l1", "llm", 3 * MIN, 4 * MIN, { tokens: tok(1000) });
  const a1l2 = span("a1l2", "llm", 4.5 * MIN, 5 * MIN, { tokens: tok(2000) });
  const a1l3 = span("a1l3", "llm", 9 * MIN, 9.5 * MIN, { tokens: tok(500) });
  const inner = span("a1tool", "tool", 3.2 * MIN, 3.5 * MIN, { error: true });
  a1l.children.push(inner);
  const a1 = span("a1", "agent", 3 * MIN, 10 * MIN, {
    children: [a1l, a1l2, a1l3],
    agent: { agentType: "explore", childId: "c1", loaded: true, totalTokens: 9999, callStart: 3 * MIN, callEnd: 3.1 * MIN, background: true },
  });
  l2.children.push(a1);
  t1.children.push(l1, l2);
  l1.children.push(tool);
  const t2 = span("t2", "turn", 20 * MIN, 21 * MIN, { turnKind: "notification", notifiedBy: "c1" });
  const resume = span("rs", "tool", 22 * MIN, 22.1 * MIN, { resumes: "c1" });
  t2.children.push(span("l3", "llm", 20 * MIN, 21 * MIN, { children: [resume], tokens: tok(10) }));
  return [t1, t2];
}

test("rollup uses agent totalTokens instead of summing its children", () => {
  const roots = fixture();
  const r = computeRollups(roots);
  assert.equal(r.get("a1")!.tokens, 9999);
  assert.equal(r.get("t1")!.tokens, 100 + 50 + 9999);
  assert.equal(r.get("a1")!.llm, 3);
  assert.equal(r.get("t1")!.errs, 2);
  assert.equal(r.get("t1")!.agents, 1);
});

test("rollup without totalTokens sums children; unloaded agent borrows delegation counts", () => {
  const a = span("a", "agent", 0, 1, { children: [span("l", "llm", 0, 1, { tokens: tok(7) })], agent: { agentType: "x", loaded: true } });
  assert.equal(computeRollups([a]).get("a")!.tokens, 7);
  const u = span("u", "agent", 0, 1, { agent: { agentType: "x", loaded: false, toolCalls: 4, toolErrors: 1 } });
  const r = computeRollups([u]).get("u")!;
  assert.equal(r.tools, 4);
  assert.equal(r.errs, 1);
});

test("mainTokens and ownWork skip subagent calls", () => {
  const roots = fixture();
  assert.equal(mainTokens(roots), 100 + 50 + 10);
  assert.deepEqual(ownWork(roots[0]), { llm: 2, tools: 1, tokens: 150 });
});

test("index finds agents by childId and links reports and resumers", () => {
  const idx = buildIndex(fixture());
  assert.equal(idx.agentByChild.get("c1")?.id, "a1");
  assert.deepEqual(idx.reports.get("c1")!.map((s) => s.id), ["t2"]);
  assert.deepEqual(idx.resumers.get("c1")!.map((s) => s.id), ["rs"]);
  assert.equal(idx.depth.get("a1l1"), 3);
  assert.equal(idx.parent.get("a1")!.id, "l2");
});

test("default expansion opens prompt turns and llm spans holding an agent", () => {
  const open = defaultExpanded(fixture());
  assert.ok(open.has("t1") && open.has("l2"));
  assert.ok(!open.has("t2") && !open.has("l1") && !open.has("a1"));
});

test("expand all skips llm rows inside subagents", () => {
  const open = expandAllIds(fixture());
  assert.ok(open.has("t1") && open.has("l1") && open.has("a1"));
  assert.ok(!open.has("a1l1"), "llm inside an agent stays collapsed");
});

test("flatten follows the expansion set", () => {
  const roots = fixture();
  const rows = flattenVisible(roots, new Set(["t1"]), "all");
  assert.deepEqual(rows.map((r) => r.span.id), ["t1", "l1", "l2", "t2"]);
  assert.deepEqual(rows.map((r) => r.depth), [0, 1, 1, 0]);
});

test("agents filter shows the path to agents and forces ancestors open", () => {
  const rows = flattenVisible(fixture(), new Set(), "agents");
  assert.deepEqual(rows.map((r) => r.span.id), ["t1", "l2", "a1"]);
});

test("errors filter reaches nested errors through collapsed parents", () => {
  const rows = flattenVisible(fixture(), new Set(), "errors");
  const ids = rows.map((r) => r.span.id);
  assert.ok(ids.includes("tool1") && ids.includes("a1tool"));
  assert.ok(!ids.includes("t2"));
});

test("bursts merge calls within two minutes and leave idle between", () => {
  const roots = fixture();
  const a1 = buildIndex(roots).byId.get("a1")!;
  const b = agentBursts(a1);
  assert.equal(b.length, 2);
  assert.deepEqual(b[0], [3 * MIN, 5 * MIN]);
  assert.deepEqual(b[1], [9 * MIN, 10 * MIN], "last burst extends to span end");
});

test("agent with no loaded calls is a single burst", () => {
  assert.deepEqual(agentBursts(span("a", "agent", 5, 50)), [[5, 50]]);
});

test("peak concurrency counts overlap, not back-to-back runs", () => {
  const mk = (s: number, e: number) => span(`a${s}`, "agent", s, e);
  assert.equal(peakConcurrency([mk(0, 10), mk(5, 15), mk(8, 9)]), 3);
  assert.equal(peakConcurrency([mk(0, 10), mk(10, 20)]), 1);
  assert.equal(peakConcurrency([]), 0);
});

test("lazy agent needs a loader, unloaded flag and no children", () => {
  const a = span("a", "agent", 0, 1, { agent: { agentType: "x", loaded: false } });
  assert.equal(isLazyAgent(a, true), true);
  assert.equal(isLazyAgent(a, false), false);
  a.agent!.loaded = true;
  assert.equal(isLazyAgent(a, true), false);
});

function skillFixture() {
  const turn = span("t", "turn", 0, 10 * MIN, { turnKind: "prompt" });
  const typed = span("s0", "skill", 0, 0, { skill: { name: "make-reel", via: "command" }, content: { input: "args" } });
  const llm = span("l", "llm", MIN, 2 * MIN, { tokens: tok(5) });
  const called = span("s1", "skill", 1.5 * MIN, 1.6 * MIN, { skill: { name: "make-reel", via: "tool" } });
  const other = span("s2", "skill", 5 * MIN, 5.1 * MIN, { skill: { name: "plan", via: "tool" } });
  llm.children.push(called);
  turn.children.push(typed, llm, other);
  return [turn];
}

test("skills are indexed, counted and grouped into lanes by name", () => {
  const roots = skillFixture();
  const idx = buildIndex(roots);
  assert.deepEqual(idx.skills.map((s) => s.id), ["s0", "s1", "s2"]);
  assert.equal(computeRollups(roots).get("t")!.skills, 3);
  const lanes = skillLanes(idx);
  assert.deepEqual(lanes.map((l) => [l.name, l.spans.length]), [["make-reel", 2], ["plan", 1]]);
});

test("skills do not count as tools or model calls, and keep their parents' tokens", () => {
  const roots = skillFixture();
  assert.deepEqual(ownWork(roots[0]), { llm: 1, tools: 0, tokens: 5 });
});

test("llm rows containing a skill open by default", () => {
  assert.ok(defaultExpanded(skillFixture()).has("l"));
});

test("the agents filter matches skills too", () => {
  const roots = skillFixture();
  assert.equal(matchesFilter(roots[0].children[0], "agents"), true);
  const rows = flattenVisible(roots, new Set(), "agents").map((r) => r.span.id);
  assert.deepEqual(rows, ["t", "s0", "l", "s1", "s2"]);
});
