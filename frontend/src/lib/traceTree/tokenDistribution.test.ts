import { test } from "node:test";
import assert from "node:assert/strict";
import { tokenDistribution, formatTokenShare } from "./tokenDistribution";

test("stacked token shares preserve exact proportions for the recorded sample", () => {
  const d = tokenDistribution({ input: 2, cacheRead: 94630, cacheWrite: 1017, output: 240 });
  assert.ok(d);
  assert.equal(d.total, 95889);
  assert.ok(Math.abs(d.shares.cacheRead - 98.68702353763205) < 1e-10);
  assert.ok(Math.abs(Object.values(d.shares).reduce((a, b) => a + b, 0) - 100) < 1e-10);
  assert.equal(formatTokenShare(d.shares.input), "<0.01%");
  assert.equal(formatTokenShare(d.shares.cacheRead), "98.69%");
});

test("zero usage remains an empty chart instead of inventing equal segments", () => {
  assert.deepEqual(tokenDistribution({ input: 0, cacheRead: 0, cacheWrite: 0, output: 0 }), { total: 0, shares: { input: 0, cacheRead: 0, cacheWrite: 0, output: 0 } });
  assert.equal(formatTokenShare(0), "0%");
});

test("invalid usage cannot produce a misleading chart", () => {
  assert.equal(tokenDistribution({ input: -1, cacheRead: 0, cacheWrite: 0, output: 0 }), null);
  assert.equal(tokenDistribution({ input: NaN, cacheRead: 0, cacheWrite: 0, output: 0 }), null);
});
