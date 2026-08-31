"use strict";

const path = require("node:path");
const { spawn } = require("node:child_process");
const { app, BrowserWindow, dialog, shell } = require("electron");
const { isSafeExternalUrl, startDesktopServices, stopDesktopServices, waitForHttp } = require("./runtime.cjs");

const rootDir = path.resolve(__dirname, "..");
const backendDir = path.join(rootDir, "backend");
const frontendDir = path.join(rootDir, "frontend");
const isWindows = process.platform === "win32";
const python = process.env.TOKENTELEMETRY_PYTHON || path.join(backendDir, "venv", isWindows ? "Scripts/python.exe" : "bin/python3");
const npm = isWindows ? "npm.cmd" : "npm";
let services;
let quitting = false;

function stopServices() {
  if (quitting) return;
  quitting = true;
  stopDesktopServices(services);
}

async function createWindow() {
  services = await startDesktopServices({ spawn, python, npm, backendDir, frontendDir, env: process.env, dataDir: process.env.TOKENTELEMETRY_DATA_DIR });
  if (!await waitForHttp(services.url)) throw new Error("The local TokenTelemetry dashboard did not start in time.");
  const window = new BrowserWindow({
    width: 1440, height: 920, minWidth: 960, minHeight: 640, show: false, title: "TokenTelemetry",
    webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true },
  });
  window.once("ready-to-show", () => window.show());
  window.webContents.setWindowOpenHandler(({ url }) => {
    // Never hand file:, javascript:, or arbitrary custom schemes to the OS.
    if (isSafeExternalUrl(url)) void shell.openExternal(url);
    return { action: "deny" };
  });
  await window.loadURL(services.url);
}

app.whenReady().then(createWindow).catch(async (error) => {
  stopServices();
  await dialog.showMessageBox({ type: "error", title: "TokenTelemetry could not start", message: error instanceof Error ? error.message : String(error) });
  app.exit(1);
});
app.on("before-quit", stopServices);
app.on("window-all-closed", () => app.quit());
