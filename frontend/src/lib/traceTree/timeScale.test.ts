import { test } from "node:test";
import assert from "node:assert/strict";

// Set before any Date is built so local-day behaviour is checked in a zone
// where local midnight and UTC midnight differ.
process.env.TZ = "Asia/Kolkata";

import { axisMarks, buildScale, fmtDur, IDLE_GAP_MS } from "./timeScale";

const MIN = 60_000;

test("idle gaps over ten minutes become one fixed-weight piece", () => {
  const s = buildScale([[0, 5 * MIN], [60 * MIN, 65 * MIN]]);
  assert.equal(s.pieces.length, 3);
  assert.equal(s.pieces[1].gap, true);
  assert.equal(s.busyMs, 10 * MIN);
  const gapWidth = s.pieces[1].u1 - s.pieces[1].u0;
  assert.ok(Math.abs(gapWidth - 0.5 / 10.5) < 1e-9, "gap weighs 5% of busy time");
});

test("gaps under the threshold merge into busy time", () => {
  const s = buildScale([[0, MIN], [MIN + IDLE_GAP_MS - 1, MIN + IDLE_GAP_MS + 5000]]);
  assert.equal(s.pieces.length, 1);
});

test("u and tOf round-trip and clamp", () => {
  const s = buildScale([[1000, 61000], [3_000_000, 3_060_000]]);
  assert.equal(s.u(0), 0);
  assert.equal(s.u(9e12), 1);
  for (const t of [1000, 30000, 61000, 3_000_000, 3_030_000]) {
    assert.ok(Math.abs(s.tOf(s.u(t)) - t) < 2, `round trip ${t}`);
  }
  assert.ok(s.u(30000) < s.u(3_030_000));
});

test("empty and zero-length inputs do not break the scale", () => {
  assert.equal(buildScale([]).pieces.length, 0);
  const s = buildScale([[500, 500]]);
  assert.equal(s.pieces.length, 1);
  assert.ok(s.u(500) >= 0 && s.u(500) <= 1);
});

test("many gaps cannot take more than 30% of the axis", () => {
  const iv: Array<[number, number]> = [];
  for (let i = 0; i < 20; i++) iv.push([i * 60 * MIN, i * 60 * MIN + MIN]);
  const s = buildScale(iv);
  const gaps = s.pieces.filter((p) => p.gap).reduce((a, p) => a + p.u1 - p.u0, 0);
  assert.ok(gaps <= 0.3 + 1e-9);
});

test("a day mark lands on local midnight, not UTC midnight", () => {
  // 23:30 IST on the 14th to 00:30 IST on the 15th (18:00 to 19:00 UTC).
  const start = new Date(2026, 5, 14, 23, 30).getTime();
  const end = new Date(2026, 5, 15, 0, 30).getTime();
  const s = buildScale([[start, end]]);
  const marks = axisMarks(s, 0, 1, 900);
  const day = marks.find((m) => m.kind === "day");
  assert.ok(day, "expected a day mark");
  assert.equal(day.label, "Jun 15");
  const at = s.tOf(day.x);
  assert.ok(Math.abs(at - new Date(2026, 5, 15).getTime()) < 5000, "mark sits at local 00:00");
  assert.notEqual(new Date(at).getUTCHours(), 0, "and not at UTC 00:00");
  assert.ok(!marks.some((m) => m.kind === "tick" && m.label === "00:00"), "no duplicate tick at midnight");
});

test("ticks align to local clock boundaries", () => {
  const start = new Date(2026, 5, 14, 10, 3, 17).getTime();
  const s = buildScale([[start, start + 30 * MIN]]);
  const ticks = axisMarks(s, 0, 1, 900).filter((m) => m.kind === "tick");
  assert.ok(ticks.length >= 2);
  for (const t of ticks) assert.match(t.label, /^\d\d:\d\d$/);
  const secs = ticks.map((t) => new Date(s.tOf(t.x)).getSeconds());
  assert.ok(secs.every((x) => x === 0), "minute-level ticks fall on whole minutes");
});

test("idle gap gets a labelled mark when wide enough", () => {
  const s = buildScale([[0, 30 * MIN], [3 * 60 * MIN, 3 * 60 * MIN + 30 * MIN]]);
  const idle = axisMarks(s, 0, 1, 1200).find((m) => m.kind === "idle");
  assert.ok(idle);
  assert.equal(idle.label, "2h 30m idle");
});

test("fmtDur formats seconds, minutes and hours", () => {
  assert.equal(fmtDur(400), "0.4s");
  assert.equal(fmtDur(42_000), "42s");
  assert.equal(fmtDur(125_000), "2m 05s");
  assert.equal(fmtDur(3_900_000), "1h 05m");
});
