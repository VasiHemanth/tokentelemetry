"use strict";

/**
 * System-tray panel: the TokenTelemetry icon and the popover behind it.
 *
 * The panel is the app's own `/menubar` page in a frameless window, not a
 * natively drawn menu. That is what lets it reuse the dashboard's plan-limits
 * design and real agent logos on macOS, Windows and Linux from one
 * implementation, instead of a per-platform drawing layer.
 *
 * `popoverBounds` is deliberately pure so the positioning -- the part that puts
 * a window off the edge of a display when it is wrong -- is testable without
 * launching Electron or owning a tray.
 */

const path = require("node:path");
const fs = require("node:fs");

const PANEL_WIDTH = 340;
const PANEL_HEIGHT = 560;
// Gap between the tray icon and the panel, matching the offset a native menu
// leaves under a status item.
const PANEL_GAP = 6;

/**
 * Where to put the popover for a given tray icon.
 *
 * Centred under (or over) the icon, then clamped inside the display's work
 * area: a tray icon near the right-hand edge of the screen would otherwise
 * push half the panel off it, and on Windows and most Linux desktops the tray
 * sits at the BOTTOM, so the panel has to open upward instead.
 *
 * All inputs are plain rectangles, so this needs no Electron at all.
 */
function popoverBounds(tray, panel, workArea) {
  const width = panel.width;
  const height = panel.height;

  const centred = Math.round(tray.x + tray.width / 2 - width / 2);
  const minX = workArea.x;
  const maxX = workArea.x + workArea.width - width;
  const x = Math.round(Math.max(minX, Math.min(maxX, centred)));

  // A tray in the top half of the display opens downward; one in the bottom
  // half (Windows, most Linux panels) opens upward.
  const trayIsOnTop = tray.y + tray.height / 2 < workArea.y + workArea.height / 2;
  const below = tray.y + tray.height + PANEL_GAP;
  const above = tray.y - PANEL_GAP - height;
  let y = trayIsOnTop ? below : above;

  const minY = workArea.y;
  const maxY = workArea.y + workArea.height - height;
  y = Math.round(Math.max(minY, Math.min(maxY, y)));

  return { x, y, width, height };
}

/** The tray icon file, or null when the asset is missing from this build. */
function trayIconPath(assetsDir) {
  // 16pt@2x is the slice a tray/status item wants; the larger icons render
  // blurry when downscaled by the OS.
  const candidate = path.join(assetsDir, "icon.iconset", "icon_16x16@2x.png");
  if (fs.existsSync(candidate)) return candidate;
  const fallback = path.join(assetsDir, "icon.png");
  return fs.existsSync(fallback) ? fallback : null;
}

/**
 * Create the tray icon and its popover window.
 *
 * Returns `{ tray, window, destroy }`, or null when no icon asset exists --
 * a tray with no image is an invisible click target, which is worse than not
 * having one.
 */
function createTrayPanel({ electron, assetsDir, baseUrl, preloadPath, onOpenDashboard, platform }) {
  const { Tray, BrowserWindow, nativeImage, screen, ipcMain } = electron;
  const iconPath = trayIconPath(assetsDir);
  if (!iconPath) return null;

  const image = nativeImage.createFromPath(iconPath);
  // A template image is drawn as a silhouette and tinted by macOS for a light
  // or dark menu bar. Windows and Linux tray areas expect the real artwork.
  if (platform === "darwin") image.setTemplateImage(true);

  const tray = new Tray(image);
  tray.setToolTip("TokenTelemetry");

  const window = new BrowserWindow({
    width: PANEL_WIDTH,
    height: PANEL_HEIGHT,
    show: false,
    frame: false,
    resizable: false,
    movable: false,
    // Keeps the panel out of the taskbar/dock and off Mission Control, so it
    // behaves like a menu rather than a second app window.
    skipTaskbar: true,
    fullscreenable: false,
    backgroundColor: "#11141a",
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      preload: preloadPath,
    },
  });

  // Closing the panel must not quit the app: the tray icon is still there and
  // the window is reused every time it is opened.
  window.on("close", (event) => {
    if (!window.isDestroyed()) {
      event.preventDefault();
      window.hide();
    }
  });
  // Clicking anywhere else dismisses it, the way a menu does.
  window.on("blur", () => window.hide());

  const position = () => {
    const trayBounds = tray.getBounds();
    const display = screen.getDisplayNearestPoint({
      x: trayBounds.x + Math.round(trayBounds.width / 2),
      y: trayBounds.y + Math.round(trayBounds.height / 2),
    });
    const bounds = popoverBounds(trayBounds,
      { width: PANEL_WIDTH, height: PANEL_HEIGHT }, display.workArea);
    window.setBounds(bounds);
  };

  const toggle = () => {
    if (window.isVisible()) {
      window.hide();
      return;
    }
    position();
    window.show();
    window.focus();
  };

  tray.on("click", toggle);
  // Windows and Linux fire this for a right-click; treating it the same keeps
  // one behaviour everywhere rather than a context menu on some platforms.
  tray.on("right-click", toggle);

  const handleOpen = (_event, requested) => {
    window.hide();
    onOpenDashboard(typeof requested === "string" ? requested : "/");
  };
  ipcMain.on("tokentelemetry:open-dashboard", handleOpen);

  void window.loadURL(`${baseUrl.replace(/\/$/, "")}/menubar`);

  return {
    tray,
    window,
    destroy() {
      ipcMain.removeListener("tokentelemetry:open-dashboard", handleOpen);
      if (!window.isDestroyed()) window.destroy();
      tray.destroy();
    },
  };
}

module.exports = { PANEL_WIDTH, PANEL_HEIGHT, PANEL_GAP, popoverBounds, trayIconPath, createTrayPanel };
