import { test } from "node:test";
import assert from "node:assert/strict";
import { geminiAdapter } from "./gemini";

const T = (s: number) => new Date(Date.UTC(2026, 0, 1, 0, 0, s)).toISOString();
const user = (s: number, text: string) => ({ type: "user", timestamp: T(s), content: [{ text }] });
const reply = (s: number, toolCalls: unknown[], tokens = { input: 100, output: 10, cached: 60, thoughts: 5, tool: 0, total: 115 }) => ({
  type: "assistant", timestamp: T(s), model: "gemini-test", content: "working on it", tokens, toolCalls,
});

test("messages become llm spans with nested tools, tokens split cache and thoughts", () => {
  const events = [
    { type: "info", timestamp: T(0), content: "update available" },
    user(1, "list the files"),
    reply(3, [
      { id: "a", name: "list_directory", args: { dir_path: "/home/dev/app/src" }, status: "success", timestamp: T(4) },
      { id: "b", name: "run_shell_command", args: { command: "rm -rf x", description: "Clean up" }, status: "error", timestamp: T(10) },
    ]),
    reply(12, []),
  ];
  const turns = geminiAdapter.build(events as never, null);
  assert.equal(turns.length, 1);
  const [first, second] = turns[0].children;
  assert.deepEqual(first.tokens, { input: 40, output: 15, cacheRead: 60, cacheWrite: 0 });
  assert.equal(first.start, Date.parse(T(1)));
  assert.equal(first.children[0].label, "src");
  assert.equal(first.children[1].label, "Clean up");
  assert.equal(first.children[1].error, true);
  assert.equal(second.start, Date.parse(T(10)), "next llm starts after the slowest tool");
  assert.equal(turns[0].end, Date.parse(T(12)));
  assert.equal(turns[0].label, "list the files");
});

test("a second user message starts a second turn", () => {
  const events = [user(1, "a"), reply(2, []), user(5, "b"), reply(6, [])];
  const turns = geminiAdapter.build(events as never, null);
  assert.deepEqual(turns.map((t) => t.title), ["User prompt 1", "User prompt 2"]);
});
