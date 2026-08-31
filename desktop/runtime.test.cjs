"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const runtime = require("./runtime.cjs");

test("desktop URLs always use localhost", () => {
  assert.equal(runtime.LOCAL_HOST, "localhost");
  assert.equal(runtime.localUrl(4312), "http://localhost:4312/");
  assert.equal(runtime.localUrl(4312, "/openapi.json"), "http://localhost:4312/openapi.json");
});

test("only HTTPS links may leave the sandboxed dashboard", () => {
  assert.equal(runtime.isSafeExternalUrl("https://tokentelemetry.com/docs"), true);
  assert.equal(runtime.isSafeExternalUrl("http://localhost:8000"), false);
  assert.equal(runtime.isSafeExternalUrl("file:///etc/passwd"), false);
  assert.equal(runtime.isSafeExternalUrl("javascript:alert(1)"), false);
  assert.equal(runtime.isSafeExternalUrl("not a URL"), false);
});

test("desktop environment pins renderer API variables to localhost", () => {
  const env = runtime.desktopEnvironment({ PYTHONPATH: "/existing", KEEP: "yes" }, "/repo/backend", "/data", 8123);
  assert.equal(env.NEXT_PUBLIC_API_BASE, "http://localhost:8123/");
  assert.equal(env.NEXT_PUBLIC_API_PORT, "8123");
  assert.equal(env.TT_NEXT_DIST_DIR, ".next-desktop");
  assert.equal(env.TT_HOST, "localhost");
  assert.equal(env.TT_API_PORT, "8123");
  assert.equal(env.TOKENTELEMETRY_DATA_DIR, "/data");
  assert.equal(env.KEEP, "yes");
  assert.deepEqual(env.PYTHONPATH.split(path.delimiter), ["/repo/backend", "/existing"]);
});

test("desktop startup gives both children a localhost-only contract", async () => {
  const calls = [];
  const services = await runtime.startDesktopServices({
    spawn(command, args, options) { calls.push({ command, args, options }); return { pid: calls.length + 100, killed: false }; },
    python: "/repo/backend/venv/bin/python3", npm: "npm", backendDir: "/repo/backend", frontendDir: "/repo/frontend", env: { KEEP: "yes" }, dataDir: "/tmp/token-data",
  });
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[0].args.slice(0, 4), ["main.py", "--host", "localhost", "--port"]);
  assert.deepEqual(calls[1].args.slice(0, 5), ["run", "dev", "--", "--hostname", "localhost"]);
  assert.equal(calls[0].options.env.NEXT_PUBLIC_API_BASE, `http://localhost:${services.apiPort}/`);
  assert.equal(calls[1].options.env.NEXT_PUBLIC_API_BASE, `http://localhost:${services.apiPort}/`);
  assert.equal(services.url, `http://localhost:${services.frontendPort}/`);
});

test("desktop shutdown signals detached process groups on POSIX", () => {
  const targets = [];
  runtime.stopDesktopServices({ backend: { pid: 12 }, frontend: { pid: 34 } }, "darwin", (pid, signal) => targets.push([pid, signal]));
  assert.deepEqual(targets, [[-12, "SIGTERM"], [-34, "SIGTERM"]]);
});
