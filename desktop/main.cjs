"use strict";

const path = require("node:path");
const fs = require("node:fs");
const { spawn } = require("node:child_process");
const electron = require("electron");
const { app, BrowserWindow, Menu, dialog, shell } = electron;
const { isSafeExternalUrl, startDesktopServices, stopDesktopServices, waitForHttp } = require("./runtime.cjs");
const { createTrayPanel } = require("./tray.cjs");

// Name the app before it's ready so the About panel and app.name read
// "TokenTelemetry". The macOS menu bar title is set explicitly below (it derives
// from the bundle name otherwise, which for an unpackaged dev run is "Electron").
app.setName("TokenTelemetry");

// Windows taskbar/Alt-Tab identity: groups the window and names it properly for
// an unpackaged dev run (packaged apps get it from the build's appId/productName).
if (process.platform === "win32") {
  app.setAppUserModelId("com.tokentelemetry.desktop");
}

// Build a custom application menu so the top-left macOS menu (and the in-window
// menus) show "TokenTelemetry" rather than Electron's default. Packaged builds
// get the same title from productName.
function buildApplicationMenu() {
  const template = [
    {
      label: app.name,
      submenu: [
        { role: "about" }, { type: "separator" },
        { role: "services" }, { type: "separator" },
        { role: "hide" }, { role: "hideOthers" }, { role: "unhide" }, { type: "separator" },
        { role: "quit" },
      ],
    },
    {
      label: "Edit",
      submenu: [
        { role: "undo" }, { role: "redo" }, { type: "separator" },
        { role: "cut" }, { role: "copy" }, { role: "paste" }, { role: "selectAll" },
      ],
    },
    {
      label: "View",
      submenu: [
        { role: "reload" }, { role: "toggleDevTools" }, { type: "separator" },
        { role: "resetZoom" }, { role: "zoomIn" }, { role: "zoomOut" }, { type: "separator" },
        { role: "togglefullscreen" },
      ],
    },
    {
      label: "Window",
      submenu: [
        { role: "minimize" }, { role: "zoom" }, { role: "close" },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

const rootDir = path.resolve(__dirname, "..");
const backendDir = path.join(rootDir, "backend");
const frontendDir = path.join(rootDir, "frontend");
const isWindows = process.platform === "win32";
const isMac = process.platform === "darwin";
const isLinux = process.platform === "linux";
const python = process.env.TOKENTELEMETRY_PYTHON || path.join(backendDir, "venv", isWindows ? "Scripts/python.exe" : "bin/python3");
const npm = isWindows ? "npm.cmd" : "npm";
// The app icon, generated for every OS. Windows/Linux read the window `icon`;
// macOS uses the bundle's .icns once packaged, and `app.dock.setIcon` so an
// unpackaged dev run isn't the generic Electron logo.
const appIcon = path.join(__dirname, "assets", "icon.png");
let services;
let mainWindow;
let trayPanel;
let quitting = false;

function stopServices() {
  if (quitting) return;
  quitting = true;
  if (trayPanel) { trayPanel.destroy(); trayPanel = undefined; }
  stopDesktopServices(services);
}

async function createWindow() {
  services = await startDesktopServices({ spawn, python, npm, backendDir, frontendDir, env: process.env, dataDir: process.env.TOKENTELEMETRY_DATA_DIR });
  if (!await waitForHttp(services.url)) throw new Error("The local TokenTelemetry dashboard did not start in time.");
  const window = new BrowserWindow({
    width: 1440, height: 920, minWidth: 960, minHeight: 640, show: false, title: "TokenTelemetry",
    // Keep the OS-native title bar (draggable everywhere, all content clickable
    // below it). A frameless/hidden title bar over full-bleed web content makes
    // drag-vs-click a hard trade-off, so we stay reliable and let the window move
    // via the native title bar. Window background matches the dark canvas.
    backgroundColor: "#0a0c10",
    ...((isWindows || isLinux) && fs.existsSync(appIcon) ? { icon: appIcon } : {}),
    webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true },
  });
  window.once("ready-to-show", () => window.show());
  window.webContents.setWindowOpenHandler(({ url }) => {
    // Never hand file:, javascript:, or arbitrary custom schemes to the OS.
    if (isSafeExternalUrl(url)) void shell.openExternal(url);
    return { action: "deny" };
  });
  mainWindow = window;
  await window.loadURL(services.url);
}

// Surface the dashboard when the tray panel asks for it. The window is only
// created once, so this re-shows the existing one rather than opening a second.
function showDashboard(routePath) {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  const target = `${services.url.replace(/\/$/, "")}${routePath}`;
  void mainWindow.loadURL(target);
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
}

app.whenReady().then(() => {
  buildApplicationMenu();
  // macOS dock icon for an unpackaged (dev) run; packaged apps get the .icns.
  if (isMac && app.dock && fs.existsSync(appIcon)) {
    app.dock.setIcon(appIcon);
  }
  return createWindow().then(() => {
    // Best-effort: a tray is a convenience, and a desktop environment without
    // a working tray (some Linux sessions) must not stop the app from running.
    try {
      trayPanel = createTrayPanel({
        electron,
        assetsDir: path.join(__dirname, "assets"),
        baseUrl: services.url,
        preloadPath: path.join(__dirname, "preload.cjs"),
        onOpenDashboard: showDashboard,
        platform: process.platform,
      });
    } catch (error) {
      console.warn("TokenTelemetry: tray unavailable —", error instanceof Error ? error.message : error);
    }
  });
}).catch(async (error) => {
  stopServices();
  await dialog.showMessageBox({ type: "error", title: "TokenTelemetry could not start", message: error instanceof Error ? error.message : String(error) });
  app.exit(1);
});
app.on("before-quit", stopServices);
app.on("window-all-closed", () => { if (!trayPanel) app.quit(); });
