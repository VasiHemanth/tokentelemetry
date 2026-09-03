"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const tray = require("./tray.cjs");

const PANEL = { width: tray.PANEL_WIDTH, height: tray.PANEL_HEIGHT };
// A 1512x982 work area, the usable part of a 14" laptop display below the menu bar.
const MAC_AREA = { x: 0, y: 38, width: 1512, height: 944 };

test("the panel hangs under a menu bar icon", () => {
  const icon = { x: 700, y: 0, width: 24, height: 24 };
  const bounds = tray.popoverBounds(icon, PANEL, MAC_AREA);

  // Centred on the icon.
  assert.equal(bounds.x, Math.round(700 + 12 - tray.PANEL_WIDTH / 2));
  // Below the icon, but never over the menu bar: the macOS work area starts at
  // 38, so the panel sits there rather than at the raw icon-plus-gap of 30.
  assert.equal(bounds.y, MAC_AREA.y);
  assert.equal(bounds.width, tray.PANEL_WIDTH);
  assert.equal(bounds.height, tray.PANEL_HEIGHT);
});

test("an icon near the right edge does not push the panel off screen", () => {
  // macOS status items sit at the far right, which is the common case, not an
  // edge case: centring naively would place most of the panel past the display.
  const icon = { x: 1490, y: 0, width: 22, height: 24 };
  const bounds = tray.popoverBounds(icon, PANEL, MAC_AREA);

  assert.ok(bounds.x + bounds.width <= MAC_AREA.x + MAC_AREA.width,
    `panel right edge ${bounds.x + bounds.width} exceeds ${MAC_AREA.x + MAC_AREA.width}`);
  assert.equal(bounds.x, MAC_AREA.width - tray.PANEL_WIDTH);
});

test("an icon near the left edge stays inside the display", () => {
  const icon = { x: 2, y: 0, width: 22, height: 24 };
  const bounds = tray.popoverBounds(icon, PANEL, MAC_AREA);
  assert.equal(bounds.x, MAC_AREA.x);
});

test("a bottom taskbar opens the panel upward", () => {
  // Windows and most Linux panels put the tray at the BOTTOM. Opening downward
  // there would push the whole panel off the bottom of the screen.
  const area = { x: 0, y: 0, width: 1920, height: 1032 };
  const icon = { x: 1700, y: 1032, width: 24, height: 24 };
  const bounds = tray.popoverBounds(icon, PANEL, area);

  assert.ok(bounds.y + bounds.height <= area.y + area.height);
  assert.equal(bounds.y, 1032 - tray.PANEL_GAP - tray.PANEL_HEIGHT);
});

test("a panel taller than the work area is clamped, never negative", () => {
  const area = { x: 0, y: 0, width: 1280, height: 400 };
  const icon = { x: 600, y: 0, width: 24, height: 24 };
  const bounds = tray.popoverBounds(icon, PANEL, area);

  assert.ok(bounds.y >= area.y, `y ${bounds.y} is above the work area`);
  assert.equal(bounds.y, area.y);
});

test("a second display's offset is respected", () => {
  // An external display to the right has a non-zero origin; positions are
  // absolute across the desktop, so ignoring x would land the panel on the
  // wrong screen entirely.
  const area = { x: 1512, y: 0, width: 2560, height: 1440 };
  const icon = { x: 4000, y: 0, width: 24, height: 24 };
  const bounds = tray.popoverBounds(icon, PANEL, area);

  assert.ok(bounds.x >= area.x);
  assert.ok(bounds.x + bounds.width <= area.x + area.width);
});

test("the tray icon comes from the 16pt@2x slice", () => {
  // Larger slices render blurry when the OS scales them down to tray size.
  const found = tray.trayIconPath(path.join(__dirname, "assets"));
  assert.ok(found, "no tray icon asset found");
  assert.ok(found.endsWith(path.join("icon.iconset", "icon_16x16@2x.png")), found);
});

test("a build with no icon asset reports none rather than an invisible tray", () => {
  assert.equal(tray.trayIconPath(path.join(__dirname, "does-not-exist")), null);
});
