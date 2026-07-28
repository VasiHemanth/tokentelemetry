import { test } from "node:test";
import assert from "node:assert/strict";
import { projectBasename } from "./paths";

// Paths here are placeholders on purpose. Never paste a real path from a bug
// report into a fixture — the user segment is someone's account name.

test("POSIX path yields its last segment", () => {
  assert.equal(projectBasename("/Users/dev/Documents/my-project"), "my-project");
});

test("Windows path yields its last segment", () => {
  // The bug this fixes: split("/") alone returns the WHOLE string for a
  // Windows path, so the project name rendered as the full C:\... path.
  assert.equal(
    projectBasename("C:\\Users\\dev\\Documents\\my-project"),
    "my-project",
  );
});

test("UNC path yields its last segment", () => {
  assert.equal(projectBasename("\\\\server\\share\\proj"), "proj");
});

test("trailing separators are ignored", () => {
  assert.equal(projectBasename("C:\\Users\\dev\\app\\"), "app");
  assert.equal(projectBasename("/Users/dev/app/"), "app");
});

test("degenerate input never throws", () => {
  assert.equal(projectBasename("C:\\"), "C:");
  assert.equal(projectBasename(""), "");
  assert.equal(projectBasename(null), "");
  assert.equal(projectBasename(undefined), "");
});

test("a bare name with no separator is unchanged", () => {
  assert.equal(projectBasename("my-project"), "my-project");
});
