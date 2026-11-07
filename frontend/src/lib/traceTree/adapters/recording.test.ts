import { test } from "node:test";
import assert from "node:assert/strict";
import { recordingAdapter } from "./recording";
import { traceAdapter } from "../index";
import type { Event } from "../../traceEvents";

test("order-only recordings retain prompts, reasoning, identified calls, and exact results", () => {
  const input = { path: "file.ts" }, output = { ok: true };
  const events: Event[] = [
    { type: "user", message: { role: "user", content: [{ type: "text", text: "Read the file" }] } },
    { type: "assistant", message: { content: [{ type: "thinking", thinking: "Recorded explanation" }, { type: "tool_use", id: "call-a", name: "read_file", input }] } },
    { type: "user", message: { content: [{ type: "tool_result", tool_use_id: "call-a", content: output }] } },
    { type: "assistant", message: { content: [{ type: "text", text: "Read complete" }] } },
  ];
  const adapter = recordingAdapter("grok");
  const roots = adapter.build(events, null);
  assert.equal(adapter.timing, "order-only");
  assert.equal(roots.length, 1);
  const model = roots[0].children[0];
  assert.equal(model.recordOnly, true);
  assert.equal(model.content?.reasoning, "Recorded explanation");
  const tool = model.children[0];
  assert.equal(tool.content?.input, input);
  assert.equal(tool.content?.output, output);
  assert.equal(tool.tokens, undefined);
  assert.equal(roots[0].children[1].content?.output, "Read complete");
});

test("unidentified outputs stay separate; missing results are never fabricated", () => {
  const roots = recordingAdapter("antigravity").build([
    { type: "assistant", message: { content: [{ type: "tool_use", name: "read", input: {} }] } },
    { type: "user", message: { content: [{ type: "tool_result", content: "Unlinked evidence" }] } },
  ], null);
  assert.equal(roots[0].children[0].children[0].content?.output, undefined);
  assert.equal(roots[0].children[1].content?.output, "Unlinked evidence");
  assert.equal(roots[0].turnKind, "notification");
});

test("flat readers preserve OpenAI calls, result errors, and structured response payloads", () => {
  const roots = recordingAdapter("vibe").build([
    { type: "user", payload: { content: "Check files" } },
    { type: "assistant", payload: { content: "Checking", tool_calls: [{ id: "a", function: { name: "read", arguments: '{"path":"file.ts"}' } }] } },
    { type: "tool", payload: { tool_call_id: "a", content: "failed", is_error: true } },
    { type: "assistant", payload: [{ kind: "markdownContent", value: "Recorded response" }] },
  ], null);
  const tool = roots[0].children[0].children[0];
  assert.equal(tool.content?.input, '{"path":"file.ts"}');
  assert.equal(tool.content?.output, "failed");
  assert.equal(tool.error, true);
  assert.ok(Array.isArray(roots[0].children[1].content?.output));
});

test("delegations without a recorded handoff stay explicitly unplaced and load by recorded child id", () => {
  const adapter = recordingAdapter("grok");
  const roots = adapter.build([], { subagents: [{ agent_id: "spawn-a", child_session_id: "child-a", agent_type: "review", tokens: { total: 0 } }], tokens_recorded: false });
  assert.equal(roots[0].turnKind, "notification");
  assert.match(roots[0].title, /placement unavailable/i);
  const child = roots[0].children[0];
  assert.equal(child.agent?.totalTokens, undefined);
  assert.equal(adapter.childFetch?.("parent", child)?.path, "/sessions/child-a?agent=grok");
});

test("structured user evidence survives without a text block, and adjacent SmallCode results pair", () => {
  const parts = [{ type: "image", source: { type: "url", url: "https://example.test/image.png" } }];
  const roots = recordingAdapter("smallcode").build([
    { type: "user", content: parts },
    { type: "tool_call", payload: { tool: "read", args: { path: "file.ts" } } },
    { type: "tool_result", payload: { tool: "read", content: "" } },
  ], null);
  assert.deepEqual(roots[0].content?.input, parts);
  assert.equal(roots[0].children[0].content?.output, "");
});


test("every registered agent has a workspace adapter, including recording-only readers", () => {
  const agents = ["claude", "codex", "gemini", "antigravity", "qwen", "vibe", "cursor", "copilot", "opencode", "hermes", "grok", "openai_compat", "cline", "smallcode", "pi", "muse", "prime", "dsh", "qoder", "zcode", "kimi", "omp"];
  for (const agent of agents) assert.ok(traceAdapter(agent), `${agent} workspace adapter`);
});

test("SmallCode never guesses a result link across a message or different tool name", () => {
  for (const middle of [[], [{ type: "assistant", payload: { content: "Intervening response" } }]]) {
    const roots = recordingAdapter("smallcode").build([
      { type: "tool_call", payload: { tool: "read", args: {} } },
      ...middle,
      { type: "tool_result", payload: { tool: middle.length ? "read" : "write", content: "Result" } },
    ], null);
    assert.equal(roots[0].children[0].content?.output, undefined);
    assert.equal(roots[0].children.at(-1)?.content?.output, "Result");
  }
});

test("recorded null arguments and results stay null rather than becoming missing or payload objects", () => {
  const roots = recordingAdapter("copilot").build([
    { type: "tool_call", payload: { tool: "noop", callID: "a", arguments: null } },
    { type: "tool_result", payload: { callID: "a", content: null } },
  ], null);
  const tool = roots[0].children[0];
  assert.equal(tool.content?.input, null);
  assert.equal(tool.content?.output, null);
});
