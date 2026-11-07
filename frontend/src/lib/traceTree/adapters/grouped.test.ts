import { test } from "node:test";
import assert from "node:assert/strict";
import { hermesAdapter } from "./hermes";
import { primeAdapter } from "./prime";

const T = 1_700_000_000_000;
const user = (t: number, content: string) => ({ type: "user", payload: { content }, normalized_timestamp: t });
const think = (t: number, text: string) => ({ type: "assistant_thinking", payload: { text }, normalized_timestamp: t });
const say = (t: number, content: string) => ({ type: "assistant", payload: { content }, normalized_timestamp: t });

test("hermes pairs by callID and unwraps MCP calls", () => {
  const events = [
    user(T, "do it"),
    think(T + 100, "plan"),
    { type: "tool_call", payload: { tool: "read_file", callID: "a", args: { path: "/home/dev/x/notes.md" } }, normalized_timestamp: T + 100 },
    { type: "tool_call", payload: { tool: "tool_call", callID: "b", args: { name: "mcp__web__fetch", arguments: { url: "https://example.com/a?b=1" } } }, normalized_timestamp: T + 100 },
    { type: "tool_result", payload: { tool: "mcp__web__fetch", callID: "b", content: "{\"error\": \"boom\"}" }, normalized_timestamp: T + 400 },
    { type: "tool_result", payload: { tool: "read_file", callID: "a", content: "{\"content\": \"text\", \"error\": null}" }, normalized_timestamp: T + 150 },
    think(T + 900, "next"),
    say(T + 900, "all done"),
  ];
  const [turn] = hermesAdapter.build(events, null);
  assert.equal(turn.children.length, 2);
  const [a, b] = turn.children[0].children;
  assert.equal(a.title, "read_file");
  assert.equal(a.label, "notes.md");
  assert.equal(a.end, T + 150);
  assert.equal(a.error, undefined);
  assert.equal(b.title, "mcp__web__fetch");
  assert.equal(b.label, "example.com");
  assert.equal(b.error, true);
  assert.equal(turn.children[1].start, T + 150, "starts at the previous event in the log");
  assert.equal(turn.children[1].label, "all done");
});

test("hermes injected user text becomes a notification turn", () => {
  const events = [
    user(T, "[Note: model was just switched from a to b]"),
    user(T + 1, "real"),
    user(T + 2, "[ASYNC DELEGATION COMPLETE - deleg_1]\nresult"),
    say(T + 3, "ok"),
  ];
  const turns = hermesAdapter.build(events, null);
  assert.deepEqual(turns.map((t) => t.turnKind), ["notification", "prompt", "notification"]);
  assert.equal(turns[1].title, "User prompt 1");
});

test("prime pairs a result with the oldest unpaired call of the same tool", () => {
  const call = (t: number, code: string) => ({ type: "tool_call", payload: { tool: "ipython", args: { code } }, normalized_timestamp: t });
  const result = (t: number) => ({ type: "tool_result", payload: { tool: "ipython", content: "ok" }, normalized_timestamp: t });
  const events = [user(T, "q"), call(T + 10, "print(1)"), call(T + 10, "print(2)"), result(T + 50), result(T + 80), say(T + 100, "a")];
  const [turn] = primeAdapter.build(events, null);
  const [one, two] = turn.children[0].children;
  assert.equal(one.end, T + 50);
  assert.equal(two.end, T + 80);
  assert.equal(one.label, undefined, "code is not used as a label");
  assert.equal(primeAdapter.timing, "real");
});

test("content: hermes and prime fill turn, llm and tool content", () => {
  const args = { name: "mcp__x__y", arguments: { q: "z" } };
  const hermes = [
    user(T, "hi"),
    think(T + 1, "plan"),
    say(T + 1, "calling"),
    { type: "tool_call", payload: { tool: "tool_call", callID: "a", args }, normalized_timestamp: T + 1 },
    { type: "tool_result", payload: { tool: "x", callID: "a", content: "res" }, normalized_timestamp: T + 2 },
  ];
  const [turn] = hermesAdapter.build(hermes, null);
  assert.deepEqual(turn.content, { input: "hi" });
  assert.deepEqual(turn.children[0].content, { output: "calling", reasoning: "plan" });
  const tool = turn.children[0].children[0];
  assert.equal(tool.content?.input, args.arguments);
  assert.equal(tool.content?.output, "res");

  const pargs = { code: "1" };
  const prime = [
    user(T, "q"),
    { type: "tool_call", payload: { tool: "ipython", args: pargs }, normalized_timestamp: T + 1 },
    { type: "tool_result", payload: { tool: "ipython", content: "out" }, normalized_timestamp: T + 2 },
  ];
  const ptool = primeAdapter.build(prime, null)[0].children[0].children[0];
  assert.equal(ptool.content?.input, pargs);
  assert.equal(ptool.content?.output, "out");
});

test("prime pairs same-name calls by id, retains usage, and marks failures", () => {
  const events = [user(T, "q"),
    { type: "tool_call", payload: { tool: "run", callID: "a" }, normalized_timestamp: T + 10 },
    { type: "tool_call", payload: { tool: "run", callID: "b" }, usage: { input: 10, output: 3, cacheRead: 5, cacheWrite: 2 }, model: "test-model", normalized_timestamp: T + 10 },
    { type: "tool_result", payload: { tool: "run", callID: "b", content: "failed", is_error: true }, normalized_timestamp: T + 20 },
    { type: "tool_result", payload: { tool: "run", callID: "a", content: "ok" }, normalized_timestamp: T + 30 }];
  const llm = primeAdapter.build(events, null)[0].children[0];
  assert.equal(llm.title, "test-model");
  assert.deepEqual(llm.tokens, { input: 10, output: 3, cacheRead: 5, cacheWrite: 2 });
  assert.equal(llm.children[0].content?.output, "ok");
  assert.equal(llm.children[1].content?.output, "failed");
  assert.equal(llm.children[1].error, true);
});

test("prime keeps distinct same-timestamp messages and usage separate", () => {
  const events = [user(T, "q"),
    { type: "assistant", payload: { content: "one" }, messageID: "m1", usage: { input: 10, output: 1 }, normalized_timestamp: T + 1 },
    { type: "assistant", payload: { content: "two" }, messageID: "m2", usage: { input: 20, output: 2 }, normalized_timestamp: T + 1 }];
  const llms = primeAdapter.build(events, null)[0].children;
  assert.equal(llms.length, 2);
  assert.deepEqual(llms.map(s => s.tokens?.input), [10, 20]);
});
