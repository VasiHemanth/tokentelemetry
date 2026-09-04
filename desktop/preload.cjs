"use strict";

/**
 * Preload for the tray panel.
 *
 * The panel runs with contextIsolation and sandbox on, so the page cannot reach
 * Electron directly. This exposes exactly one capability: ask the shell to
 * surface the main dashboard window. Nothing is returned to the page and no
 * general IPC channel is handed over, so a compromised page gains the ability
 * to open a local window the user could already open from the tray, and
 * nothing else.
 */

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("tokentelemetry", {
  openDashboard(routePath) {
    // Internal absolute paths only. A caller that passes "https://evil.example"
    // or "//evil.example" must not be able to steer the main window off the
    // local dashboard.
    const safe = typeof routePath === "string"
      && routePath.startsWith("/")
      && !routePath.startsWith("//")
      ? routePath
      : "/";
    ipcRenderer.send("tokentelemetry:open-dashboard", safe);
  },
});
