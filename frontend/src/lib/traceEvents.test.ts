import { test } from "node:test";
import assert from "node:assert/strict";
import { normalizeTraceEvents } from "./traceEvents";

test("Codex step usage enrichment leaves API records untouched for the event log", () => {
  const response = { type: "response_item", payload: { type: "message", role: "assistant", content: [{ type: "output_text", text: "Done" }] } };
  const raw = [response, { type: "event_msg", payload: { type: "token_count", info: { last_token_usage: { input_tokens: 7, output_tokens: 2 } } } }];
  const before = JSON.stringify(raw);
  const normalized = normalizeTraceEvents("codex", raw);
  assert.equal(JSON.stringify(raw), before);
  assert.equal(normalized.length, 1);
  assert.notEqual(normalized[0], response);
  assert.equal((normalized[0] as unknown as { _tt_tokens: { output_tokens: number } })._tt_tokens.output_tokens, 2);
});
