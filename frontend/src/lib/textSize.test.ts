import { test } from "node:test";
import assert from "node:assert/strict";
import { runInNewContext } from "node:vm";
import { normalizeTextSize, TEXT_SIZE_INIT_SCRIPT } from "./textSize";

test("text size accepts bounded five-percent steps and normalizes persisted values", () => {
  for (const size of [85, 100, 115, 130, 150]) assert.equal(normalizeTextSize(size), size);
  assert.equal(normalizeTextSize("115"), 115);
  assert.equal(normalizeTextSize(117), 115);
  assert.equal(normalizeTextSize(118), 120);
  assert.equal(normalizeTextSize(0), 85);
  assert.equal(normalizeTextSize(999), 150);
});

test("corrupt storage cannot create invalid CSS text sizes", () => {
  for (const value of [undefined, null, "", "115px", "invalid", NaN, Infinity, false, {}, "100;alert(1)"]) assert.equal(normalizeTextSize(value), 100);
});

function initialize(stored: unknown, denied = false) {
  const attributes: Record<string, string> = {}, style: Record<string, string> = {};
  runInNewContext(TEXT_SIZE_INIT_SCRIPT, {
    localStorage: { getItem: () => { if (denied) throw new Error("unavailable"); return stored; } },
    document: { documentElement: { setAttribute: (key: string, value: string) => { attributes[key] = value; }, style: { setProperty: (key: string, value: string) => { style[key] = value; } } } },
  });
  return { attributes, style };
}

test("before-paint initialization agrees with runtime normalization", () => {
  for (const value of ["85", "100", "115", "150", "117", "999", "0", "NaN", "", null, "115px"]) {
    const result = initialize(value);
    assert.equal(result.attributes["data-text-size"], String(normalizeTextSize(value)));
    assert.equal(result.style["--tt-text-scale"], String(normalizeTextSize(value) / 100));
  }
});

test("denied storage still applies the default text size before paint", () => {
  assert.deepEqual(initialize("130", true), { attributes: { "data-text-size": "100" }, style: { "--tt-text-scale": "1" } });
});
