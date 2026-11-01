import { test } from "node:test";
import assert from "node:assert/strict";
import { CONTENT_CAP, formatContent, formatReasoningContent } from "./content";

test("empty values", () => {
  for (const v of [undefined, null, "", "   ", [], {}]) assert.equal(formatContent(v).kind, "empty");
});

test("plain strings pass through", () => {
  assert.deepEqual(formatContent("hello"), { kind: "text", text: "hello", truncated: false, fullLength: 5 });
});

test("text blocks are joined", () => {
  const f = formatContent([{ type: "text", text: "a" }, { type: "text", text: "b" }]);
  assert.equal(f.kind, "text");
  assert.equal(f.text, "a\n\nb");
});

test("tool_result content (string and nested blocks) is unwrapped", () => {
  assert.equal(formatContent([{ type: "tool_result", content: "ok" }]).text, "ok");
  assert.equal(formatContent([{ type: "tool_result", content: [{ type: "text", text: "inner" }] }]).text, "inner");
});

test("images and unknown blocks become placeholders", () => {
  const f = formatContent([{ type: "text", text: "see" }, { type: "image", source: { data: "x".repeat(1000) } }, { type: "mystery" }]);
  assert.equal(f.text, "see\n\n[image]\n\n[mystery block]");
});

test("functionResponse unwraps to its response", () => {
  assert.equal(formatContent([{ functionResponse: { name: "f", response: { output: "done" } } }]).kind, "text");
  assert.match(formatContent([{ functionResponse: { response: "plain" } }]).text, /^plain$/);
});

test("objects pretty-print as json", () => {
  const f = formatContent({ a: 1, b: [true, null], c: { d: "x" } });
  assert.equal(f.kind, "json");
  assert.deepEqual(JSON.parse(f.text), { a: 1, b: [true, null], c: { d: "x" } });
  assert.equal(f.text, JSON.stringify({ a: 1, b: [true, null], c: { d: "x" } }, null, 2));
});

test("JSON strings that parse are pretty-printed; broken ones stay text", () => {
  assert.equal(formatContent('{"a":1}').kind, "json");
  assert.equal(formatContent('{"a":').kind, "text");
  assert.equal(formatContent("[1,2").text, "[1,2");
});

test("long strings are cut at the cap and report full length", () => {
  const f = formatContent("x".repeat(CONTENT_CAP + 500));
  assert.equal(f.truncated, true);
  assert.equal(f.text.length, CONTENT_CAP);
  assert.equal(f.fullLength, CONTENT_CAP + 500);
  assert.equal(formatContent("x".repeat(CONTENT_CAP + 500), 100_000).truncated, false);
});

test("a huge object is cut quickly without serializing all of it", () => {
  const big = { rows: Array.from({ length: 400_000 }, (_, i) => ({ i, s: "payload-" + i })) };
  const t0 = performance.now();
  const f = formatContent(big);
  const ms = performance.now() - t0;
  assert.equal(f.truncated, true);
  assert.ok(f.text.length <= CONTENT_CAP);
  assert.ok(ms < 50, `took ${ms}ms`);
});

test("a multi-MB string inside an object is not fully stringified", () => {
  const f = formatContent({ blob: "y".repeat(5_000_000) });
  assert.equal(f.truncated, true);
  assert.ok(f.text.length <= CONTENT_CAP);
});

test("deeply nested input terminates", () => {
  let o: unknown = "leaf";
  for (let i = 0; i < 5000; i++) o = { n: o };
  assert.doesNotThrow(() => formatContent(o));
});


test("reasoning previews read structured summaries without exposing encrypted fields", () => {
  const value = { summary: [{ type: "summary_text", text: "**Plan**" }, { thinking: "Verify the result" }], encrypted_content: "private blob" };
  assert.equal(formatReasoningContent(value).text, "**Plan**\n\nVerify the result");
  assert.equal(formatReasoningContent({ encrypted_content: "private blob" }).kind, "empty");
  assert.equal(formatReasoningContent("gAAAAAB" + "x".repeat(60)).kind, "empty");
  assert.equal(formatReasoningContent({ type: "redacted_thinking", text: "not readable" }).kind, "empty");
  assert.equal(formatReasoningContent([{ text: "" }, null]).kind, "empty");
  const bounded = formatReasoningContent(["a".repeat(5000), { text: "later" }], 600);
  assert.equal(bounded.text.length, 600);
  assert.equal(bounded.truncated, true);
  assert.equal(formatContent([{ type: "summary_text", text: "summary" }]).text, "summary");
});
