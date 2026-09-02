/* eslint-disable @typescript-eslint/no-require-imports -- `node --test` strips
   types at runtime and needs the explicit `.ts` specifier, but tsc rejects a
   `.ts` import path unless allowImportingTsExtensions is on (it isn't, and
   turning it on affects the whole app build). require() satisfies both: the
   runtime gets the extension, the type position stays extensionless. */
const assert: typeof import("node:assert/strict") = require("node:assert/strict");
const { test }: typeof import("node:test") = require("node:test");
const {
  buildDelegationTopology,
  getVisibleDelegationNodes,
} = require("./delegationTopology.ts") as typeof import("./delegationTopology");
import type { DelegationNode } from "./delegationTopology";

function child(id: string, overrides: Partial<DelegationNode> = {}): DelegationNode {
  return { id, label: `Agent ${id}`, ...overrides };
}

test("groups a large delegation into a compact visible set without losing the total", () => {
  const entries = Array.from({ length: 63 }, (_, index) => child(String(index + 1)));

  const topology = buildDelegationTopology(entries, { maxVisible: 8 });

  assert.equal(topology.total, 63);
  assert.equal(topology.visible.length, 8);
  assert.equal(topology.hiddenCount, 55);
  assert.equal(topology.hasOverflow, true);
});

test("prioritizes entries with recorded failures and meaningful metrics in the compact view", () => {
  const entries = [
    child("quiet"),
    child("costly", { tokens: { total: 1_000_000 }, cost: 4.5 }),
    child("failed", { status: "failed" }),
    child("short", { durationMs: 14_000 }),
  ];

  const visible = getVisibleDelegationNodes(entries, 3);

  assert.deepEqual(visible.map((entry) => entry.id), ["failed", "costly", "short"]);
});

test("uses stable source order as the tiebreaker and permits all entries when space allows", () => {
  const entries = [child("first"), child("second"), child("third")];

  const topology = buildDelegationTopology(entries, { maxVisible: 6 });

  assert.deepEqual(topology.visible.map((entry) => entry.id), ["first", "second", "third"]);
  assert.equal(topology.hiddenCount, 0);
});
