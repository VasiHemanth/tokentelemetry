import { test } from "node:test";
import assert from "node:assert/strict";
import { embeddedWithText, resolveRecallProject, sameRecallProject } from "./recallPure";

// Paths are placeholders on purpose.

test("api provider says it embeds through the API, not locally", () => {
  const t = embeddedWithText({ provider: "api", model: "stale-ollama", api: { model: "embed-x" }, ollama: { model: "nomic" } });
  assert.equal(t, "Embedded through the embedding API with embed-x");
});

test("ollama provider says it embeds locally with the ollama model", () => {
  const t = embeddedWithText({ provider: "ollama", model: "nomic", ollama: { model: "nomic" } });
  assert.equal(t, "Embedded locally with nomic");
});

test("a worktree path resolves to its canonical project key", () => {
  const projects = [{ key: "/Users/dev/code/app" }, { key: "/Users/dev/code" }];
  assert.equal(resolveRecallProject(projects, "/Users/dev/code/app/sub/wt")?.key, "/Users/dev/code/app");
  assert.equal(resolveRecallProject(projects, "/Users/dev/other"), null);
});

test("a running index matches by canonical key, not only the raw path", () => {
  assert.equal(sameRecallProject("/Users/dev/code/app", "/Users/dev/code/app", "/Users/dev/code/app/wt"), true);
  assert.equal(sameRecallProject("/Users/dev/code/other", "/Users/dev/code/app", "/Users/dev/code/app/wt"), false);
  assert.equal(sameRecallProject(null, "/a", "/a"), false);
});
