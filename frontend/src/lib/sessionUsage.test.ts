import { test } from "node:test";
import assert from "node:assert/strict";
import { pluginOf, pluginUsage, sessionUsage } from "./sessionUsage";

test("pluginOf matches the backend's naming rules", () => {
  assert.equal(pluginOf("plugin_grok_grok"), "grok");
  assert.equal(pluginOf("plugin_my_tool_my_tool"), "my_tool");
  assert.equal(pluginOf("plugin_acme_search"), "acme");
  assert.equal(pluginOf("grok:grok-rescue"), "grok");
  for (const plain of ["chrome", "graphify", "Explore", "", null, undefined, "plugin_"]) {
    assert.equal(pluginOf(plain), null);
  }
});

test("a session whose plugin calls all failed surfaces the failures", () => {
  const u = sessionUsage({
    skills_used: [{ name: "graphify", count: 1 }, { name: "grok:search", count: 1, errors: 1 }],
    mcp_usage: { plugin_grok_grok: { grok_search: 2 }, chrome: { navigate: 3 } },
    mcp_errors: { plugin_grok_grok: { grok_search: 2 } },
    tool_errors: { mcp__plugin_grok_grok__grok_search: 2, Skill: 1, Bash: 1 },
    delegation: { by_type: { "grok:grok-rescue": { count: 1, failed: 1, tool_errors: 1 }, Explore: { count: 2, tool_errors: 3 } } },
  });
  assert.ok(u);
  // Failing rows sort first.
  assert.deepEqual(u.mcp.map((r) => [r.name, r.plugin, r.calls, r.errors]),
    [["plugin_grok_grok", "grok", 2, 2], ["chrome", null, 3, 0]]);
  assert.deepEqual(u.skills.map((r) => [r.name, r.errors]), [["grok:search", 1], ["graphify", 0]]);
  assert.deepEqual(u.subagents.map((r) => [r.name, r.failed]), [["grok:grok-rescue", 1], ["Explore", 0]]);
  // MCP and Skill failures are already on their own rows; only the rest lands here.
  assert.deepEqual(u.otherToolErrors, [{ name: "Bash", errors: 1 }]);
  assert.equal(u.totalErrors, 4);
});

test("pluginUsage groups MCP, skill and subagent calls under their plugin", () => {
  const u = sessionUsage({
    skills_used: [{ name: "grok:search", count: 1, errors: 1 }, { name: "codex:rescue", count: 2 }, { name: "graphify", count: 4 }],
    mcp_usage: { plugin_grok_grok: { grok_search: 2 }, chrome: { navigate: 3 } },
    mcp_errors: { plugin_grok_grok: { grok_search: 2 } },
    tool_errors: { mcp__plugin_grok_grok__grok_search: 2, Skill: 1 },
    delegation: { by_type: { "grok:grok-rescue": { count: 1, failed: 1, tool_errors: 1 } } },
  });
  const p = pluginUsage(u);
  // Non-plugin pieces (chrome, graphify) are left out; failing plugin first.
  assert.deepEqual(p.map((g) => [g.plugin, g.calls, g.failed]), [["grok", 4, 4], ["codex", 2, 0]]);
  assert.deepEqual(p[0].items.map((i) => [i.kind, i.name, i.calls, i.failed]), [
    ["mcp", "grok_search", 2, 2],
    ["skill", "grok:search", 1, 1],
    ["subagent", "grok:grok-rescue", 1, 1],
  ]);
  assert.deepEqual(pluginUsage(null), []);
});

test("no usage signal returns null so the panel stays hidden", () => {
  assert.equal(sessionUsage({}), null);
  assert.equal(sessionUsage(null), null);
  assert.equal(sessionUsage({ tool_counts: { Bash: 3 } }), null);
});
