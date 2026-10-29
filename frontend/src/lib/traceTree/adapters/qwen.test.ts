import { test } from "node:test";
import assert from "node:assert/strict";
import { qwenAdapter } from "./qwen";

const T = (ms: number) => 1_000_000 + ms;
const base = (type: string, ms: number) => ({ type, normalized_timestamp: T(ms), timestamp: new Date(T(ms)).toISOString() });
const user = (ms: number, text: string) => ({ ...base("user", ms), message: { role: "user", parts: [{ text }] } });
const api = (ms: number, input: number, output: number, duration: number, promptId = "s########1") => ({
  ...base("system", ms),
  systemPayload: { uiEvent: { "event.name": "qwen-code.api_response", input_token_count: input, output_token_count: output, duration_ms: duration, prompt_id: promptId, model: "m" } },
});
const toolEvt = (ms: number, promptId: string, ok = true) => ({
  ...base("system", ms),
  systemPayload: { uiEvent: { "event.name": "qwen-code.tool_call", prompt_id: promptId, success: ok } },
});
const assistant = (ms: number, parts: unknown[], prompt: number, out: number, cached = 0) => ({
  ...base("assistant", ms), model: "coder",
  message: { role: "model", parts },
  usageMetadata: { promptTokenCount: prompt, candidatesTokenCount: out, thoughtsTokenCount: 3, cachedContentTokenCount: cached },
});
const fc = (id: string, name: string, args: unknown) => ({ functionCall: { id, name, args } });
const result = (ms: number, id: string, status: string) => ({
  ...base("tool_result", ms), message: { role: "user", parts: [{ functionResponse: { id } }] }, toolCallResult: { callId: id, status },
});

test("api_response duration gives the llm span a real start; parallel calls pair by id", () => {
  const events = [
    user(0, "read two files"),
    api(2000, 900, 40, 1500),
    assistant(2030, [{ text: "hmm", thought: true }, { text: "Reading." }, fc("a", "read_file", { absolute_path: "/home/dev/x/a.ts" }), fc("b", "edit", { file_path: "/home/dev/x/b.ts" })], 900, 40, 800),
    result(2100, "a", "success"),
    result(2400, "b", "error"),
  ];
  const [turn] = qwenAdapter.build(events as never, null);
  const llm = turn.children[0];
  assert.equal(llm.approxStart, undefined);
  assert.equal(llm.start, T(500));
  assert.deepEqual(llm.tokens, { input: 100, output: 40, cacheRead: 800, cacheWrite: 0 });
  assert.equal(llm.label, "Reading.");
  const [a, b] = llm.children;
  assert.equal(a.label, "a.ts");
  assert.equal(a.end, T(2100));
  assert.equal(b.error, true);
  assert.equal(turn.end, T(2400));
});

test("cancelled tools are not errors; agent calls carry their telemetry totals", () => {
  const events = [
    user(0, "explore"),
    api(1000, 100, 10, 500),
    assistant(1010, [fc("g", "agent", { description: "Look around", subagent_type: "Explore", prompt: "long" }), fc("c", "web_fetch", { url: "https://example.com/a" })], 100, 10),
    api(1500, 300, 30, 400, "s#Explore-abc123#0"),
    toolEvt(1600, "s#Explore-abc123#0"),
    toolEvt(1700, "s#Explore-abc123#0", false),
    result(1800, "c", "cancelled"),
    result(2000, "g", "success"),
  ];
  const [turn] = qwenAdapter.build(events as never, null);
  const [agent, fetch] = turn.children[0].children;
  assert.equal(fetch.error, undefined);
  assert.equal(fetch.label, "example.com");
  assert.equal(agent.kind, "agent");
  assert.equal(agent.title, "Explore");
  assert.equal(agent.label, "Look around");
  assert.equal(agent.agent?.loaded, false);
  assert.equal(agent.agent?.totalTokens, 330);
  assert.equal(agent.agent?.toolCalls, 2);
  assert.equal(agent.agent?.toolErrors, 1);
  assert.equal(qwenAdapter.childFetch, undefined);
});

test("content: prompt, thought and reply parts, tool args and response, agent task and result", () => {
  const args = { absolute_path: "/home/dev/x/a.ts" };
  const agentArgs = { description: "Look", subagent_type: "Explore", prompt: "find it" };
  const response = { output: "file body" };
  const events = [
    user(0, "go"),
    api(1000, 10, 5, 100),
    assistant(1010, [{ text: "thinking", thought: true }, { text: "Reading." }, fc("a", "read_file", args), fc("g", "agent", agentArgs)], 10, 5),
    { ...result(1100, "a", "success"), message: { role: "user", parts: [{ functionResponse: { id: "a", response } }] } },
    { ...result(1200, "g", "success"), message: { role: "user", parts: [{ functionResponse: { id: "g", response: { output: "report" } } }] } },
  ];
  const [turn] = qwenAdapter.build(events as never, null);
  assert.deepEqual(turn.content?.input, [{ text: "go" }]);
  const llm = turn.children[0];
  assert.deepEqual(llm.content?.reasoning, [{ text: "thinking", thought: true }]);
  assert.deepEqual(llm.content?.output, [{ text: "Reading." }]);
  const [tool, agent] = llm.children;
  assert.equal(tool.content?.input, args);
  assert.equal(tool.content?.output, response);
  assert.equal(agent.content?.input, agentArgs);
  assert.deepEqual(agent.content?.output, { output: "report" });
});
