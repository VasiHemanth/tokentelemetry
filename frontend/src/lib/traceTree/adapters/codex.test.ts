import { test } from "node:test";
import assert from "node:assert/strict";
import { codexAdapter, codexOutputFailed } from "./codex";

let n = 0;
const ev = (type: string, payload: Record<string, unknown>, ms: number) => ({
  type, payload, normalized_timestamp: 1_000_000 + ms, _i: n++,
});
const started = (ms: number) => ev("event_msg", { type: "task_started" }, ms);
const prompt = (text: string, ms: number) =>
  ev("event_msg", { type: "item_completed", item: { type: "UserMessage", content: [{ type: "text", text }] } }, ms);
const call = (callId: string, name: string, args: unknown, ms: number) =>
  ev("response_item", { type: "function_call", name, call_id: callId, arguments: JSON.stringify(args) }, ms);
const exec = (callId: string, ms: number) =>
  ev("response_item", { type: "custom_tool_call", name: "exec", call_id: callId, input: "rm -rf /tmp/x" }, ms);
const out = (callId: string, output: unknown, ms: number) =>
  ev("response_item", { type: "function_call_output", call_id: callId, output }, ms);
const record = (input: number, cached: number, output: number, ms: number) =>
  ev("token_usage_record", { usage: { input_tokens: input, cached_input_tokens: cached, cache_write_input_tokens: 0, output_tokens: output } }, ms);
const done = (ms: number) => ev("event_msg", { type: "task_complete" }, ms);
const item = (it: Record<string, unknown>, ms: number) => ev("event_msg", { type: "item_completed", item: it }, ms);

test("one record closes one llm span that owns the call before it", () => {
  const events = [
    started(0), prompt("fix the build please", 10),
    exec("c1", 1000), record(500, 400, 20, 1004), item({ type: "Extension", kind: "web.search", query: "node test runner" }, 1500),
    out("c1", [{ text: "Script completed" }], 2000),
    record(700, 600, 30, 3000), done(3010),
  ];
  const [turn] = codexAdapter.build(events as never, null);
  assert.equal(turn.title, "User prompt 1");
  assert.equal(turn.end - turn.start, 3010);
  const [a, b] = turn.children;
  assert.equal(a.kind, "llm");
  assert.deepEqual(a.tokens, { input: 100, output: 20, cacheRead: 400, cacheWrite: 0 });
  assert.equal(a.start, 1_000_010, "starts at the prompt, not at its own record");
  assert.equal(a.end, 1_001_004);
  const tool = a.children[0];
  assert.equal(tool.end - tool.start, 1000, "tool runs to its output, past the llm end");
  assert.equal(tool.label, "web.search: node test runner");
  assert.ok(!tool.label?.includes("rm"), "never the raw input");
  assert.equal(b.start, 1_002_000, "second call starts at the tool output");
  assert.equal(b.children.length, 0);
});

test("spawn_agent links its child by call id; a failed spawn has no child", () => {
  const events = [
    started(0), prompt("go", 5),
    call("s1", "spawn_agent", { task_name: "scout" }, 100), record(10, 0, 1, 101),
    out("s1", '{"task_name":"/root/scout"}', 110),
    item({ type: "SubAgentActivity", id: "s1", kind: "started", agent_thread_id: "child-1", agent_path: "/root/scout" }, 120),
    call("m1", "send_message", { target: "scout", message: "enc" }, 200), record(10, 0, 1, 201),
    out("m1", '{"accepted":true}', 210),
    item({ type: "SubAgentActivity", id: "m1", kind: "interacted", agent_thread_id: "child-1", agent_path: "/root/scout" }, 211),
    item({ type: "SubAgentActivity", id: "x", kind: "completed", agent_thread_id: "child-1", agent_path: "/root/scout" }, 5000),
    call("s2", "spawn_agent", { task_name: "extra" }, 300), record(10, 0, 1, 301),
    out("s2", "collab spawn failed: agent thread limit reached", 310),
    done(5100),
  ];
  const [turn] = codexAdapter.build(events as never, null);
  const spans = turn.children.flatMap((l) => l.children);
  const [spawn, send, failed] = spans;
  assert.equal(spawn.kind, "agent");
  assert.equal(spawn.agent?.childId, "child-1");
  assert.equal(spawn.agent?.background, true);
  assert.equal(spawn.end, 1_005_000, "agent span runs until the child completed");
  assert.equal(send.kind, "tool");
  assert.equal(send.resumes, "child-1");
  assert.equal(failed.kind, "agent");
  assert.equal(failed.error, true);
  assert.equal(failed.agent?.childId, undefined);
  assert.equal(codexAdapter.childFetch?.("p", spawn)?.path, "/sessions/child-1?agent=codex");
  assert.equal(codexAdapter.childFetch?.("p", failed), null);
});

test("errors come from the output text and nested command exit codes", () => {
  assert.equal(codexOutputFailed("Script failed\nWall time 0.0 seconds"), true);
  assert.equal(codexOutputFailed('{"exit_code":2,"output":""}'), true);
  assert.equal(codexOutputFailed('{"exit_code":0}'), false);
  const events = [
    started(0), prompt("p", 1),
    exec("c1", 10), item({ type: "CommandExecution", parsed_cmd: [{ type: "unknown" }], exit_code: 1, status: "failed" }, 20),
    out("c1", [{ text: "Script completed" }], 30), record(5, 0, 1, 40), done(50),
  ];
  const [turn] = codexAdapter.build(events as never, null);
  assert.equal(turn.children[0].children[0].error, true);
});

test("a call with no usage record still lands in the turn", () => {
  const events = [started(0), prompt("p", 1), call("c1", "wait_agent", {}, 10), out("c1", "{}", 20), done(30)];
  const [turn] = codexAdapter.build(events as never, null);
  assert.equal(turn.children.length, 1);
  assert.equal(turn.children[0].children.length, 1);
  assert.equal(turn.children[0].tokens, undefined);
});

test("older rollouts without records use the _tt_tokens the normalizer attaches", () => {
  const first = call("c1", "shell", { command: ["ls"] }, 10) as Record<string, unknown>;
  first._tt_tokens = { input_tokens: 50, cached_input_tokens: 10, output_tokens: 5 };
  const events = [started(0), ev("response_item", { type: "message", role: "user", content: [{ type: "input_text", text: "<environment_context>x</environment_context>" }] }, 1),
    ev("response_item", { type: "message", role: "user", content: [{ type: "input_text", text: "real ask" }] }, 2), first, out("c1", "ok", 20), done(30)];
  const [turn] = codexAdapter.build(events as never, null);
  assert.equal(turn.label, "real ask");
  assert.deepEqual(turn.children[0].tokens, { input: 40, output: 5, cacheRead: 10, cacheWrite: 0 });
});

test("content: prompt, reply, readable reasoning, tool args and outputs are the trace's own values", () => {
  const msg = [{ type: "output_text", text: "All done." }];
  const cipher = "gAAAAAB" + "x".repeat(60);
  const outputList = [{ type: "input_text", text: "Script completed" }];
  const events = [
    started(0), prompt("hello", 1),
    item({ type: "Reasoning", summary_text: ["**Plan**"] }, 5),
    item({ type: "Reasoning", summary_text: [] }, 6),
    exec("c1", 10), record(5, 0, 1, 11), out("c1", outputList, 20),
    call("s1", "spawn_agent", { task_name: "scout", message: cipher }, 30),
    item({ type: "AgentMessage", content: [{ type: "Text", text: "dup" }] }, 35),
    ev("response_item", { type: "message", role: "assistant", content: msg }, 36),
    record(5, 0, 1, 37), out("s1", '{"task_name":"/root/scout"}', 40), done(50),
  ];
  const [turn] = codexAdapter.build(events as never, null);
  assert.deepEqual(turn.content?.input, [{ type: "text", text: "hello" }]);
  const [first, second] = turn.children;
  assert.deepEqual(first.content?.reasoning, [["**Plan**"]].flat());
  assert.equal(first.children[0].content?.input, "rm -rf /tmp/x");
  assert.equal(first.children[0].content?.output, outputList, "same reference, not a copy");
  assert.equal(second.content?.output, msg, "response_item wins over its AgentMessage mirror");
  const agent = second.children[0];
  assert.deepEqual(agent.content?.input, { task_name: "scout" }, "ciphertext dropped");
  assert.equal(agent.content?.output, '{"task_name":"/root/scout"}');
});


test("native reasoning summaries are canonical over mirrored desktop items", () => {
  const summary = [{ type: "summary_text", text: "Recorded plan" }];
  const events = [started(0), prompt("hello", 1),
    item({ type: "Reasoning", summary_text: ["Recorded plan"] }, 2),
    ev("response_item", { type: "reasoning", summary, encrypted_content: "opaque" }, 3),
    record(5, 0, 1, 4),
    ev("response_item", { type: "reasoning", summary: [], encrypted_content: "opaque" }, 5),
    record(5, 0, 1, 6), done(7)];
  const [turn] = codexAdapter.build(events as never, null);
  assert.deepEqual(turn.children[0].content?.reasoning, summary);
  assert.equal(turn.children[1].content?.reasoning, undefined);
});
