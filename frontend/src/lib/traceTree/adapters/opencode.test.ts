import { test } from "node:test";
import assert from "node:assert/strict";
import { opencodeAdapter } from "./opencode";
import type { TraceSpan } from "../types";

const T = 1_700_000_000_000;
const user = (t: number, content: string) => ({ type: "user", payload: { content }, normalized_timestamp: t });
const think = (t: number, text: string) => ({ type: "assistant_thinking", payload: { text }, normalized_timestamp: t });
const say = (t: number, content: string, tokens?: object) => ({ type: "assistant", payload: { content }, normalized_timestamp: t, ...(tokens ? { tokens } : {}) });
const tool = (t: number, name: string, state: object, tokens?: object) => ({
  type: "tool_call",
  payload: { tool: name, callID: `c${t}`, state },
  normalized_timestamp: t,
  ...(tokens ? { tokens } : {}),
});
// ZCode folds cache reads into input, so its total leaves them out.
const tokFolded = (input: number, output: number, read: number) => ({ total: input + output, input, output, reasoning: 0, cache: { read, write: 0 } });
const tok = (input: number, output: number, read = 0) => ({ total: input + output + read, input, output, reasoning: 0, cache: { read, write: 0 } });

test("events up to the one carrying tokens form one llm span", () => {
  const events = [
    user(T, "fix the bug"),
    think(T + 100, "look first"),
    tool(T + 200, "read", { status: "completed", input: { filePath: "/home/dev/app/main.py" }, time: { start: T + 210, end: T + 230 } }),
    tool(T + 240, "bash", { status: "completed", input: { command: "ls -la", description: "List files" }, time: { start: T + 250, end: T + 300 } }, tok(100, 20, 500)),
    say(T + 900, "done", tok(120, 30, 500)),
  ];
  const [turn] = opencodeAdapter("opencode").build(events, null);
  assert.equal(turn.title, "User prompt 1");
  assert.equal(turn.children.length, 2);
  const [first, second] = turn.children;
  assert.equal(first.children.length, 2);
  assert.deepEqual(first.tokens, { input: 100, output: 20, cacheRead: 500, cacheWrite: 0 });
  assert.equal(first.children[0].label, "main.py");
  assert.equal(first.children[1].label, "List files");
  assert.equal(first.start, T, "llm starts at the previous event");
  assert.equal(second.start, T + 300, "second step starts once the tools returned");
  assert.equal(second.label, "done");
  assert.equal(turn.end, T + 900);
});

test("task calls become agent spans with the child session id", () => {
  const events = [
    user(T, "go"),
    tool(T + 10, "task", {
      status: "completed",
      input: { description: "Map schema", prompt: "x", subagent_type: "explore" },
      metadata: { sessionId: "ses_child1" },
      time: { start: T + 20, end: T + 5000 },
    }, tok(10, 5)),
  ];
  const adapter = opencodeAdapter("opencode");
  const [turn] = adapter.build(events, null);
  const span = turn.children[0].children[0];
  assert.equal(span.kind, "agent");
  assert.equal(span.title, "explore");
  assert.equal(span.agent?.childId, "ses_child1");
  assert.equal(span.agent?.loaded, false);
  assert.deepEqual(adapter.childFetch?.("parent", span), { path: "/sessions/ses_child1?agent=opencode", agent: "opencode" });
});

test("error status flags the tool span", () => {
  const events = [user(T, "go"), tool(T + 5, "edit", { status: "error", input: { filePath: "a.ts" }, error: "no match", time: { start: T + 6, end: T + 7 } }, tok(1, 1))];
  const [turn] = opencodeAdapter("opencode").build(events, null);
  assert.equal(turn.children[0].children[0].error, true);
});

test("zcode: child id comes from the output, injected user text is not a prompt", () => {
  const output = "report\nagentId: agent_abc-123 (use SendMessage)\n<usage>x</usage>";
  const events = [
    user(T, "real prompt"),
    tool(T + 10, "Agent", { status: "completed", input: { description: "d", subagent_type: "Explore" }, output, time: { start: T + 11, end: T + 900 } }, tokFolded(100, 5, 80)),
    tool(T + 20, "Agent", { status: "error", input: { description: "d2", subagent_type: "Explore" }, error: "limit", output: "", time: { start: T + 21, end: T + 21 } }),
    user(T + 1000, "The TodoWrite tool hasn't been used recently. Consider it."),
    say(T + 1100, "ok", tokFolded(200, 10, 150)),
    user(T + 2000, "<task-notification>\n<summary>Background command done</summary>\n</task-notification>"),
    say(T + 2100, "noted"),
  ];
  const adapter = opencodeAdapter("zcode");
  const turns = adapter.build(events, null);
  assert.deepEqual(turns.map((t) => t.turnKind), ["prompt", "notification"]);
  const spans = turns[0].children.flatMap((l) => l.children);
  assert.equal(spans[0].agent?.childId, "sess_subagent_agent_abc-123");
  assert.equal(spans[1].error, true);
  assert.equal(spans[1].agent?.childId, undefined);
  assert.equal(adapter.childFetch?.("p", spans[1]), null);
  // zcode folds cache into input: input 100 with 80 cached is 20 fresh
  assert.equal(turns[0].children[0].tokens?.input, 20);
  assert.equal(turns[0].children.length, 2, "reminder did not split the turn");
});

test("span ids are unique", () => {
  const events = [user(T, "a"), tool(T + 1, "read", { status: "completed", input: {}, time: { start: T + 2, end: T + 3 } }, tok(1, 1)), user(T + 10, "b"), say(T + 11, "x", tok(1, 1))];
  const seen = new Set<string>();
  const walk = (s: TraceSpan) => { assert.ok(!seen.has(s.id)); seen.add(s.id); s.children.forEach(walk); };
  opencodeAdapter("opencode").build(events, null).forEach(walk);
});

test("content: prompt, reasoning, reply, tool args/result, agent task/output, error text", () => {
  const input = { filePath: "a.ts" };
  const events = [
    user(T, "the prompt"),
    think(T + 1, "hmm"),
    think(T + 2, "ok"),
    say(T + 3, "reply text"),
    tool(T + 4, "read", { status: "completed", input, output: "file body", time: { start: T + 5, end: T + 6 } }),
    tool(T + 7, "edit", { status: "error", input, error: "no match", output: "ignored", time: { start: T + 8, end: T + 9 } }),
    tool(T + 10, "task", { status: "completed", input: { description: "d", prompt: "do the thing", subagent_type: "explore" }, output: "found it", metadata: { sessionId: "ses_c" }, time: { start: T + 11, end: T + 12 } }, tok(1, 1)),
  ];
  const [turn] = opencodeAdapter("opencode").build(events, null);
  assert.deepEqual(turn.content, { input: "the prompt" });
  const llm = turn.children[0];
  assert.deepEqual(llm.content, { output: "reply text", reasoning: "hmm\n\nok" });
  const [read, edit, agent] = llm.children;
  assert.equal(read.content?.input, input, "arguments are referenced, not copied");
  assert.equal(read.content?.output, "file body");
  assert.equal(edit.content?.output, "no match");
  assert.deepEqual(agent.content, { input: "do the thing", output: "found it" });
});
