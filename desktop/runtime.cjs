"use strict";

// Process management deliberately independent of Electron, so the launch
// contract is testable without starting Chromium.
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");

const LOCAL_HOST = "localhost";

function localUrl(port, pathname = "/") {
  return `http://${LOCAL_HOST}:${port}${pathname}`;
}

function isSafeExternalUrl(rawUrl) {
  try {
    return new URL(rawUrl).protocol === "https:";
  } catch (_) {
    return false;
  }
}

function findAvailablePort(host = "127.0.0.1") {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.once("error", reject);
    server.listen(0, host, () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : null;
      server.close((error) => error ? reject(error) : resolve(port));
    });
  });
}

function waitForHttp(url, timeoutMs = 45_000) {
  const startedAt = Date.now();
  return new Promise((resolve) => {
    const retry = () => {
      if (Date.now() - startedAt >= timeoutMs) return resolve(false);
      setTimeout(probe, 250);
    };
    const probe = () => {
      const request = http.get(url, (response) => {
        response.resume();
        if (response.statusCode && response.statusCode < 500) return resolve(true);
        retry();
      });
      request.once("error", retry);
      request.setTimeout(1_500, () => { request.destroy(); retry(); });
    };
    probe();
  });
}

function desktopEnvironment(baseEnvironment, backendDir, dataDir, apiPort) {
  const pythonPath = [backendDir, baseEnvironment.PYTHONPATH].filter(Boolean).join(path.delimiter);
  return {
    ...baseEnvironment,
    PYTHONPATH: pythonPath,
    ...(dataDir ? { TOKENTELEMETRY_DATA_DIR: dataDir } : {}),
    NEXT_PUBLIC_API_BASE: localUrl(apiPort),
    NEXT_PUBLIC_API_PORT: String(apiPort),
    TT_NEXT_DIST_DIR: ".next-desktop",
    TT_HOST: LOCAL_HOST,
    TT_API_PORT: String(apiPort),
  };
}

async function startDesktopServices({ spawn, python, npm, backendDir, frontendDir, env, dataDir }) {
  const [apiPort, frontendPort] = await Promise.all([findAvailablePort(), findAvailablePort()]);
  const childEnv = desktopEnvironment(env, backendDir, dataDir, apiPort);
  const detached = process.platform !== "win32";
  const backend = spawn(python, ["main.py", "--host", LOCAL_HOST, "--port", String(apiPort)], {
    cwd: backendDir, detached, env: childEnv, stdio: "inherit",
  });
  const frontend = spawn(npm, ["run", "dev", "--", "--hostname", LOCAL_HOST, "--port", String(frontendPort)], {
    cwd: frontendDir, detached, env: { ...childEnv, PORT: String(frontendPort) }, shell: false, stdio: "inherit",
  });
  return { apiPort, frontendPort, backend, frontend, url: localUrl(frontendPort) };
}

function stopChild(child, platform = process.platform, kill = process.kill) {
  if (!child || !child.pid || child.killed) return;
  try { kill(platform === "win32" ? child.pid : -child.pid, "SIGTERM"); } catch (_) { /* child exited */ }
}

function stopDesktopServices(services, platform = process.platform, kill = process.kill) {
  if (!services) return;
  stopChild(services.backend, platform, kill);
  stopChild(services.frontend, platform, kill);
}

module.exports = { LOCAL_HOST, localUrl, isSafeExternalUrl, findAvailablePort, waitForHttp, desktopEnvironment, startDesktopServices, stopChild, stopDesktopServices };
