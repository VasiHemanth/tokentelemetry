import { test } from "node:test";
import assert from "node:assert/strict";
import { claudeShapeAdapter } from "./claudeShape";
import type { Event } from "../../traceEvents";

const T0 = 1_700_000_000_000;
const user = (t: number, content: unknown, extra: object = {}): Event =>
  ({ type: "user", normalized_timestamp: t, message: { role: "user", content }, ...extra }) as Event;
const asst = (t: number, content: unknown[], message: object = {}): Event =>
  ({ type: "assistant", normalized_timestamp: t, message: { role: "assistant", content, ...message } }) as Event;
const use = (id: string, name: string, input: object = {}) => ({ type: "tool_use", id, name, input });
const res = (id: string, content: unknown = "ok", is_error?: boolean) => ({
  type: "tool_result",
  tool_use_id: id,
  content,
  ...(is_error ? { is_error } : {}),
});

test("claude: blocks sharing message.id make one llm span, usage counted once", () => {
  const usage = { input_tokens: 5, output_tokens: 20, cache_read_input_tokens: 100, cache_creation_input_tokens: 7 };
  const events = [
    user(T0, "hello"),
    asst(T0 + 1000, [{ type: "thinking", thinking: "" }], { id: "m1", model: "m", usage }),
    asst(T0 + 1500, [use("t1", "Read", { file_path: "/home/dev/app/src/index.ts" })], { id: "m1", model: "m", usage }),
    user(T0 + 2000, [res("t1")]),
  ];
  const spans = claudeShapeAdapter("claude").build(events, null);
  assert.equal(spans.length, 1);
  const llm = spans[0].children[0];
  assert.equal(spans[0].children.length, 1);
  assert.deepEqual(llm.tokens, { input: 5, output: 20, cacheRead: 100, cacheWrite: 7 });
  assert.equal(llm.approxStart, true);
  assert.equal(llm.start, T0);
  assert.equal(llm.end, T0 + 1500);
  const tool = llm.children[0];
  assert.equal(tool.label, "index.ts");
  assert.equal(tool.start, T0 + 1500);
  assert.equal(tool.end, T0 + 2000);
  assert.equal(spans[0].end, T0 + 2000);
  assert.equal(tool.eventIndex, 2);
});

test("claude: tool errors are flagged and raw commands never become labels", () => {
  const events = [
    user(T0, "go"),
    asst(T0 + 10, [use("a", "Bash", { command: "cat ~/secret" }), use("b", "Bash", { command: "ls", description: "List files" })], { id: "m" }),
    user(T0 + 20, [res("a", "boom", true), res("b")]),
  ];
  const [turn] = claudeShapeAdapter("claude").build(events, null);
  const [a, b] = turn.children[0].children;
  assert.equal(a.error, true);
  assert.equal(a.label, undefined);
  assert.equal(b.label, "List files");
  assert.equal(b.error, undefined);
});

test("claude: turns, notifications, skipped wrappers and skill bodies", () => {
  const id = "a0123456789abcdef";
  const events = [
    user(T0, "first"),
    asst(T0 + 10, [{ type: "text", text: "hi" }], { id: "m1" }),
    user(T0 + 20, "<local-command-stdout>x</local-command-stdout>"),
    user(T0 + 30, [{ type: "text", text: "Base directory for this skill: /x" }]),
    user(T0 + 40, `<task-notification>\n<task-id>${id}</task-id>\n<summary>Agent "Scout" finished</summary>`, {
      origin: { kind: "task-notification" },
    }),
    asst(T0 + 50, [{ type: "text", text: "ok" }], { id: "m2" }),
    user(T0 + 60, "second"),
  ];
  const spans = claudeShapeAdapter("claude").build(events, null);
  assert.deepEqual(spans.map((s) => [s.title, s.turnKind]), [
    ["User prompt 1", "prompt"],
    ["Notification", "notification"],
    ["User prompt 2", "prompt"],
  ]);
  assert.equal(spans[0].end, T0 + 30);
  assert.equal(spans[1].notifiedBy, id);
  assert.equal(spans[1].label, 'Agent "Scout" finished');
});

test("claude: Agent calls link to delegation by tool_use_id and flag background", () => {
  const delegation = {
    subagents: [
      {
        agent_id: "a0123456789abcdef",
        agent_type: "scout",
        tool_use_id: "toolu_1",
        model: "m",
        tokens: { total: 900 },
        cost: 0.5,
        started_at: new Date(T0 + 1000).toISOString(),
        ended_at: new Date(T0 + 60_000).toISOString(),
        tool_calls: 4,
        tool_errors: 1,
      },
    ],
  };
  const events = [
    user(T0, "go"),
    asst(T0 + 900, [use("toolu_1", "Agent", { description: "Look around", prompt: "secret prompt" }), use("toolu_2", "Agent", { description: "Orphan" })], { id: "m" }),
    user(T0 + 1100, [res("toolu_1"), res("toolu_2")]),
    asst(T0 + 1200, [use("toolu_3", "SendMessage", { to: "a0123456789abcdef", summary: "x" })], { id: "m2" }),
  ];
  const spans = claudeShapeAdapter("claude").build(events, delegation);
  const [linked, orphan] = spans[0].children[0].children;
  assert.equal(linked.kind, "agent");
  assert.equal(linked.title, "scout");
  assert.equal(linked.label, "Look around");
  assert.equal(linked.start, T0 + 1000);
  assert.equal(linked.end, T0 + 60_000);
  assert.deepEqual(linked.agent, {
    agentType: "scout", childId: "a0123456789abcdef", callStart: T0 + 900, callEnd: T0 + 1100,
    background: true, model: "m", totalTokens: 900, cost: 0.5, toolCalls: 4, toolErrors: 1, loaded: false,
  });
  assert.equal(orphan.kind, "agent");
  assert.equal(orphan.error, true);
  assert.equal(orphan.start, T0 + 900);
  assert.equal(orphan.end, T0 + 1100);
  const send = spans[0].children[1].children[0];
  assert.equal(send.kind, "tool");
  assert.equal(send.resumes, "a0123456789abcdef");
  const adapter = claudeShapeAdapter("claude");
  assert.deepEqual(adapter.childFetch!("sess", linked), {
    path: "/sessions/sess/subagents/a0123456789abcdef/trace?agent=claude", agent: "claude",
  });
});

test("claude child: the first prompt is the task, and unlinked Agent calls are not errors", () => {
  const events = [user(T0, "do the thing"), asst(T0 + 5, [use("x", "Agent", { description: "nested" })], { id: "m" })];
  const spans = claudeShapeAdapter("claude").buildChild!(events);
  assert.equal(spans[0].title, "Task");
  assert.equal(spans[0].children[0].children[0].error, undefined);
});

test("dsh: same-timestamp assistant events merge, subagent ack links the child", () => {
  const id = "11111111-2222-3333-4444-555555555555";
  const delegation = {
    subagents: [{ agent_id: id, agent_type: "dsh-subagent", model: "m", tokens: { total: 50 }, cost: 0.1, ended_at: new Date(T0 + 90_000).toISOString() }],
  };
  const events = [
    user(T0, [{ type: "text", text: "hi" }]),
    asst(T0 + 100, [{ type: "thinking", thinking: "t" }]),
    asst(T0 + 100, [use("s1", "subagent", { description: "Research" })]),
    user(T0 + 150, [res("s1", `started subagent ${id}`)]),
    asst(T0 + 200, [{ type: "text", text: "done" }]),
  ];
  const adapter = claudeShapeAdapter("dsh");
  const [turn] = adapter.build(events, delegation);
  assert.equal(turn.children.length, 2);
  const span = turn.children[0].children[0];
  assert.equal(span.kind, "agent");
  assert.equal(span.agent?.childId, id);
  assert.equal(span.agent?.background, true);
  assert.equal(span.agent?.totalTokens, 50);
  assert.equal(span.start, T0 + 100);
  assert.equal(span.end, T0 + 90_000);
  assert.deepEqual(adapter.childFetch!("p", span), { path: `/sessions/${id}?agent=dsh`, agent: "dsh" });
});

test("qoder: Agent calls link by description, span is the call window, no drill-in", () => {
  const delegation = {
    subagents: [
      { agent_id: "agent-1", agent_type: "general-purpose", description: "Map it", tokens: { total: 0 }, cost: 0 },
      { agent_id: "agent-2", agent_type: "general-purpose", description: "Map it", tokens: { total: 0 }, cost: 0 },
    ],
  };
  const events = [
    user(T0, [{ type: "text", text: "go" }]),
    asst(T0 + 10, [use("c1", "Agent", { description: "Map it" }), use("c2", "Agent", { description: "Map it" })]),
    user(T0 + 5000, [res("c1")]),
    user(T0 + 6000, [res("c2")]),
  ];
  const adapter = claudeShapeAdapter("qoder");
  const [turn] = adapter.build(events, delegation);
  const [a, b] = turn.children[0].children;
  assert.equal(a.agent?.childId, "agent-1");
  assert.equal(b.agent?.childId, "agent-2");
  assert.equal(a.agent?.totalTokens, undefined);
  assert.equal(a.start, T0 + 10);
  assert.equal(b.end, T0 + 6000);
  assert.equal(adapter.childFetch!("p", a), null);
});

test("pi: plain tool calls pair without ids or usage", () => {
  const events = [
    user(T0, [{ type: "text", text: "hi" }]),
    asst(T0 + 10, [{ type: "thinking", thinking: "x" }, use("c|1", "LS", { path: "/home/dev/app" })]),
    user(T0 + 30, [res("c|1")]),
  ];
  const [turn] = claudeShapeAdapter("pi").build(events, null);
  assert.equal(turn.children[0].tokens, undefined);
  assert.equal(turn.children[0].children[0].label, "app");
  assert.equal(turn.children[0].children[0].end, T0 + 30);
});

test("content: turn, llm, tool and agent spans reference the trace's own values", () => {
  const input = { file_path: "/home/dev/a.ts" };
  const toolOut = [{ type: "text", text: "file body" }];
  const events = [
    user(T0, "do it"),
    asst(T0 + 10, [{ type: "thinking", thinking: "plan A" }], { id: "m" }),
    asst(T0 + 20, [{ type: "thinking", thinking: "plan B" }, { type: "text", text: "reply 1" }, { type: "text", text: "reply 2" }, use("r", "Read", input), use("g", "Agent", { description: "d", prompt: "task body" })], { id: "m" }),
    user(T0 + 30, [res("r", toolOut), res("g", "agent report")]),
    asst(T0 + 40, [use("h", "Bash", { command: "ls" })], { id: "m2" }),
    user(T0 + 50, "<task-notification>\n<summary>done</summary>", { origin: { kind: "task-notification" } }),
    user(T0 + 60, "Another Claude session sent a message:\n<agent-message from=\"a0123456789abcdef\">\nreport body\n</agent-message>", { origin: { kind: "peer" } }),
  ];
  const spans = claudeShapeAdapter("claude").build(events, null);
  assert.equal(spans[0].content?.input, "do it");
  const llm = spans[0].children[0];
  assert.equal(llm.content?.reasoning, "plan A\n\nplan B");
  assert.equal(llm.content?.output, "reply 1\n\nreply 2");
  const [read, agent] = llm.children;
  assert.equal(read.content?.input, input);
  assert.equal(read.content?.output, toolOut);
  assert.equal(agent.content?.input, "task body");
  assert.equal(agent.content?.output, "agent report");
  const second = spans[0].children[1];
  assert.equal(second.content, undefined, "no text or thinking leaves the llm content unset");
  assert.equal(second.children[0].content?.output, undefined);
  assert.equal(spans[1].content?.input, "<task-notification>\n<summary>done</summary>");
  assert.equal(spans[2].content?.input, "report body");
});

test("content: dsh, pi and qoder fill tool and agent content too", () => {
  const events = [
    user(T0, [{ type: "text", text: "hi" }]),
    asst(T0 + 10, [use("s", "subagent", { description: "x", prompt: "do x" })]),
    user(T0 + 20, [res("s", "started subagent 11111111-2222-3333-4444-555555555555")]),
  ];
  for (const shape of ["dsh", "pi", "qoder"] as const) {
    const [turn] = claudeShapeAdapter(shape).build(events, null);
    assert.equal(turn.content?.input, "hi");
    const tool = turn.children[0].children[0];
    assert.equal(tool.content?.output, "started subagent 11111111-2222-3333-4444-555555555555");
    assert.equal(tool.content?.input, shape === "dsh" ? "do x" : events[1].message.content[0].input);
  }
});

test("claude: a typed /skill starts a turn holding a skill span; built-in commands do not", () => {
  const events = [
    user(T0, "<command-name>/make-reel</command-name>\n<command-message>make-reel</command-message>\n<command-args>https://example.com/p</command-args>"),
    asst(T0 + 10, [{ type: "text", text: "on it" }], { id: "m1" }),
    user(T0 + 20, "<command-name>/clear</command-name>\n<command-message>clear</command-message>\n<command-args></command-args>"),
  ];
  const spans = claudeShapeAdapter("claude").build(events, null);
  assert.equal(spans.length, 2);
  assert.equal(spans[0].label, "/make-reel https://example.com/p");
  const [skill, llm] = spans[0].children;
  assert.equal(skill.kind, "skill");
  assert.deepEqual(skill.skill, { name: "make-reel", via: "command" });
  assert.equal(skill.content?.input, "https://example.com/p");
  assert.equal(llm.kind, "llm");
  assert.equal(spans[1].label, "/clear");
  assert.equal(spans[1].children.length, 0);
});
