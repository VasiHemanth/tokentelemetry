import { test } from "node:test";
import assert from "node:assert/strict";
import { resolveSessionBackTarget } from "./navigation";

test("internal project path is honored (came from a project -> back to project, not dashboard)", () => {
  assert.equal(
    resolveSessionBackTarget("/projects/abc/activity", "claude"),
    "/projects/abc/activity",
  );
  // Same for hermes agent: explicit internal `from` wins over the per-agent fallback.
  assert.equal(
    resolveSessionBackTarget("/projects/abc/activity", "hermes"),
    "/projects/abc/activity",
  );
});

test('from="/" with agent="claude" returns "/"', () => {
  assert.equal(resolveSessionBackTarget("/", "claude"), "/");
});

test('from=null falls back per-agent', () => {
  assert.equal(resolveSessionBackTarget(null, "hermes"), "/hermes");
  assert.equal(resolveSessionBackTarget(null, "claude"), "/");
});

test("from=undefined falls back per-agent", () => {
  assert.equal(resolveSessionBackTarget(undefined, "hermes"), "/hermes");
  assert.equal(resolveSessionBackTarget(undefined, "claude"), "/");
});

test('from="" (empty string) falls back per-agent', () => {
  assert.equal(resolveSessionBackTarget("", "hermes"), "/hermes");
  assert.equal(resolveSessionBackTarget("", "claude"), "/");
});

test("open-redirect guard: protocol-relative //evil.com falls back, never the external host", () => {
  assert.equal(resolveSessionBackTarget("//evil.com", "claude"), "/");
  assert.equal(resolveSessionBackTarget("//evil.com", "hermes"), "/hermes");
  // Also guard the path-style protocol-relative with a trailing path.
  assert.equal(resolveSessionBackTarget("//evil.com/projects/x", "claude"), "/");
});

test("open-redirect guard: absolute external URL falls back", () => {
  assert.equal(resolveSessionBackTarget("https://evil.com", "claude"), "/");
  assert.equal(resolveSessionBackTarget("https://evil.com", "hermes"), "/hermes");
  assert.equal(resolveSessionBackTarget("http://evil.com", "claude"), "/");
});

test("open-redirect guard: javascript: scheme falls back", () => {
  assert.equal(resolveSessionBackTarget("javascript:alert(1)", "claude"), "/");
  assert.equal(resolveSessionBackTarget("javascript:alert(1)", "hermes"), "/hermes");
});

test('from="/hermes" with agent=null returns "/hermes"', () => {
  // Agent is null, but an internal absolute `from` is still honored.
  assert.equal(resolveSessionBackTarget("/hermes", null), "/hermes");
});

test("agent=null/undefined with no usable from defaults to dashboard", () => {
  assert.equal(resolveSessionBackTarget(null, null), "/");
  assert.equal(resolveSessionBackTarget(null, undefined), "/");
});
