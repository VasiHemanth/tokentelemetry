import { test } from "node:test";
import assert from "node:assert/strict";
import { markSkills } from "./skills";
import type { TraceSpan } from "./types";

const T = 1_700_000_000_000;
const tool = (id: string, title: string, input: unknown): TraceSpan => ({
  id, kind: "tool", title, start: T, end: T + 10, children: [], content: { input, output: "ok" },
});
const turn = (children: TraceSpan[]): TraceSpan => ({
  id: "turn-0", kind: "turn", title: "User prompt 1", start: T, end: T + 100,
  children: [{ id: "llm-0", kind: "llm", title: "model", start: T, end: T + 50, children }],
});

test("skill tools from each harness become skill spans named after the skill", () => {
  const [root] = markSkills([turn([
    tool("a", "Skill", { skill: "make-reel", args: "https://example.com/paper" }),
    tool("b", "skill_view", { name: "humanizer" }),
    tool("c", "activate_skill", { name: "docs" }),
    tool("d", "Bash", { command: "ls" }),
  ])]);
  const [a, b, c, d] = root.children[0].children;
  assert.equal(a.kind, "skill");
  assert.equal(a.title, "make-reel");
  assert.deepEqual(a.skill, { name: "make-reel", via: "tool" });
  assert.equal(a.content?.input, "https://example.com/paper");
  assert.equal(a.content?.output, "ok");
  assert.equal(a.label, "https://example.com/paper");
  assert.equal(b.title, "humanizer");
  assert.equal(c.title, "docs");
  assert.equal(d.kind, "tool");
});

test("spans without skill calls keep their identity", () => {
  const roots = [turn([tool("d", "Bash", { command: "ls" })])];
  const out = markSkills(roots);
  assert.equal(out[0], roots[0]);
});
