import { test } from "node:test";
import assert from "node:assert/strict";
import { coerceReasoningText } from "./reasoning";

test("plain string passes through", () => {
  assert.equal(coerceReasoningText("Planning the client"), "Planning the client");
});

// Regression for issue #181: Codex Desktop reasoning summaries arrive as an
// array of { type, text } objects. Passing that array to React as a child
// crashes the whole session detail page ("Objects are not valid as a React
// child"). It must be flattened to the joined text instead.
test("structured Codex summary array is flattened to text", () => {
  const summary = [
    { type: "summary_text", text: "Planning custom HTTP client logging handler" },
    { type: "summary_text", text: "Wiring the retry path" },
  ];
  assert.equal(
    coerceReasoningText(summary),
    "Planning custom HTTP client logging handler\n\nWiring the retry path",
  );
});

test("single-element summary array yields just its text", () => {
  assert.equal(
    coerceReasoningText([{ type: "summary_text", text: "one step" }]),
    "one step",
  );
});

test("nested object with a text field is unwrapped", () => {
  assert.equal(coerceReasoningText({ type: "reasoning", text: "hi" }), "hi");
});

test("alternate text-bearing keys are honored", () => {
  assert.equal(coerceReasoningText({ thinking: "t" }), "t");
  assert.equal(coerceReasoningText({ content: "c" }), "c");
  assert.equal(coerceReasoningText({ value: "v" }), "v");
});

test("empty/unknown shapes degrade to empty string, never throw", () => {
  assert.equal(coerceReasoningText(null), "");
  assert.equal(coerceReasoningText(undefined), "");
  assert.equal(coerceReasoningText([]), "");
  assert.equal(coerceReasoningText({}), "");
  assert.equal(coerceReasoningText({ type: "summary_text" }), "");
});

test("mixed string and object array items both render", () => {
  assert.equal(
    coerceReasoningText(["raw", { text: "obj" }]),
    "raw\n\nobj",
  );
});
