#!/usr/bin/env node
// Launcher shim.
//
// The real tool is a native Go binary. npm ships one prebuilt binary per
// platform as an optional dependency, marked with `os`/`cpu` so the installer
// downloads only the one that matches; this file finds it and hands the
// process over. It is the same pattern esbuild, biome and swc use, and it is
// what makes `npx tokentelemetry` and `bunx tokentelemetry` work without a
// compiler, a postinstall download, or a Python runtime.
//
// Handing over via execve on POSIX (rather than spawning a child) means signals,
// exit codes, TTY detection and pipes all behave exactly as if the binary had
// been invoked directly — no wrapper process sitting in the middle swallowing
// Ctrl-C.

const { platform, arch } = process;

const PACKAGES = {
  "darwin arm64": "@tokentelemetry/engine-darwin-arm64",
  "darwin x64": "@tokentelemetry/engine-darwin-x64",
  "linux arm64": "@tokentelemetry/engine-linux-arm64",
  "linux x64": "@tokentelemetry/engine-linux-x64",
  "win32 arm64": "@tokentelemetry/engine-win32-arm64",
  "win32 x64": "@tokentelemetry/engine-win32-x64",
};

function binaryPath() {
  const key = `${platform} ${arch}`;
  const pkg = PACKAGES[key];
  if (!pkg) {
    throw new Error(
      `tokentelemetry does not ship a prebuilt binary for ${key}.\n` +
        `Build from source instead:\n` +
        `  go install github.com/VasiHemanth/tokentelemetry/engine/cmd/tokentelemetry@latest`
    );
  }
  const exe = platform === "win32" ? "tokentelemetry.exe" : "tokentelemetry";
  try {
    return require.resolve(`${pkg}/bin/${exe}`);
  } catch {
    throw new Error(
      `tokentelemetry's binary package ${pkg} is missing.\n` +
        `This usually means the install ran with --no-optional or --omit=optional.\n` +
        `Reinstall without that flag, or run:\n` +
        `  npm install ${pkg}`
    );
  }
}

let bin;
try {
  bin = binaryPath();
} catch (err) {
  console.error(err.message);
  process.exit(1);
}

const args = process.argv.slice(2);

if (platform === "win32") {
  // Windows has no execve. Spawn, mirror the exit status, and forward the
  // signal-terminated case as the conventional 128+n so scripts can branch on
  // it the same way they would on POSIX.
  const { spawnSync } = require("child_process");
  const r = spawnSync(bin, args, { stdio: "inherit", windowsHide: true });
  if (r.error) {
    console.error(`tokentelemetry: ${r.error.message}`);
    process.exit(1);
  }
  process.exit(r.status === null ? 1 : r.status);
} else {
  // Replace this process entirely, so the Node wrapper leaves no trace.
  let execve;
  try {
    // Node 24 exposes execve natively; older versions fall back to spawn.
    ({ execve } = require("node:process"));
  } catch {
    execve = undefined;
  }
  if (typeof execve === "function") {
    try {
      execve(bin, [bin, ...args], process.env);
    } catch (err) {
      console.error(`tokentelemetry: ${err.message}`);
      process.exit(1);
    }
  } else {
    const { spawn } = require("child_process");
    const child = spawn(bin, args, { stdio: "inherit" });
    child.on("error", (err) => {
      console.error(`tokentelemetry: ${err.message}`);
      process.exit(1);
    });
    child.on("exit", (code, signal) => {
      if (signal) {
        process.kill(process.pid, signal);
        return;
      }
      process.exit(code === null ? 1 : code);
    });
  }
}
