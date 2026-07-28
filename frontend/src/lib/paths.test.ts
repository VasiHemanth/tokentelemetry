import { test } from "node:test";
import assert from "node:assert/strict";
import { projectBasename } from "./paths";

test("POSIX path yields its last segment", () => {
  assert.equal(projectBasename("/Users/me/Documents/signals-eda"), "signals-eda");
});

test("Windows path yields its last segment", () => {
  // The bug this fixes: split("/") alone returns the WHOLE string for a
  // Windows path, so the project name rendered as the full C:\... path.
  assert.equal(
    projectBasename("C:\\Users\\hemanva\\Documents\\signals-eda"),
    "signals-eda",
  );
});

test("UNC path yields its last segment", () => {
  assert.equal(projectBasename("\\\\server\\share\\proj"), "proj");
});

test("trailing separators are ignored", () => {
  assert.equal(projectBasename("C:\\Users\\me\\app\\"), "app");
  assert.equal(projectBasename("/Users/me/app/"), "app");
});

test("degenerate input never throws", () => {
  assert.equal(projectBasename("C:\\"), "C:");
  assert.equal(projectBasename(""), "");
  assert.equal(projectBasename(null), "");
  assert.equal(projectBasename(undefined), "");
});

test("a bare name with no separator is unchanged", () => {
  assert.equal(projectBasename("signals-eda"), "signals-eda");
});
