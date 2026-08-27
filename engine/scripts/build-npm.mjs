#!/usr/bin/env node
// Cross-compiles the engine for every published platform and lays out the npm
// packages that carry them.
//
// One Go toolchain builds all six targets with nothing but GOOS/GOARCH, which
// is the reason the engine is written in Go: the equivalent Rust or C build
// would need per-platform cross toolchains or CI runners.
//
// Layout produced under engine/dist/npm:
//
//   tokentelemetry/                      launcher, depends on the six below
//   @tokentelemetry/engine-linux-x64/    one prebuilt binary each
//   @tokentelemetry/engine-darwin-arm64/
//   ...
//
// npm resolves exactly one binary package per machine via the `os`/`cpu`
// fields, so a user downloads a single ~8MB binary, not all six.

import { execFileSync } from "node:child_process";
import { cpSync, mkdirSync, rmSync, writeFileSync, readFileSync, chmodSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const engineDir = resolve(here, "..");
const distDir = join(engineDir, "dist", "npm");

const VERSION = process.env.TT_VERSION ?? "0.1.0";
const SCOPE = "@tokentelemetry";

const TARGETS = [
  { goos: "linux", goarch: "amd64", os: "linux", cpu: "x64" },
  { goos: "linux", goarch: "arm64", os: "linux", cpu: "arm64" },
  { goos: "darwin", goarch: "amd64", os: "darwin", cpu: "x64" },
  { goos: "darwin", goarch: "arm64", os: "darwin", cpu: "arm64" },
  { goos: "windows", goarch: "amd64", os: "win32", cpu: "x64" },
  { goos: "windows", goarch: "arm64", os: "win32", cpu: "arm64" },
];

const common = {
  version: VERSION,
  license: "MIT",
  repository: {
    type: "git",
    url: "git+https://github.com/VasiHemanth/tokentelemetry.git",
  },
  homepage: "https://tokentelemetry.com",
};

function build() {
  rmSync(distDir, { recursive: true, force: true });
  mkdirSync(distDir, { recursive: true });

  const optionalDependencies = {};

  for (const t of TARGETS) {
    const pkgName = `${SCOPE}/engine-${t.os}-${t.cpu}`;
    const pkgDir = join(distDir, ...pkgName.split("/"));
    const binDir = join(pkgDir, "bin");
    mkdirSync(binDir, { recursive: true });

    const exe = t.os === "win32" ? "tokentelemetry.exe" : "tokentelemetry";
    const outPath = join(binDir, exe);

    process.stderr.write(`building ${t.goos}/${t.goarch} … `);
    execFileSync(
      "go",
      [
        "build",
        "-trimpath",
        // Strip the symbol table and DWARF: this is a CLI, not something
        // anyone debugs from a published artifact, and it roughly halves the
        // download every user pays for.
        "-ldflags",
        `-s -w -X github.com/VasiHemanth/tokentelemetry/engine/internal/cli.Version=${VERSION}`,
        "-o",
        outPath,
        "./cmd/tokentelemetry",
      ],
      {
        cwd: engineDir,
        env: {
          ...process.env,
          GOOS: t.goos,
          GOARCH: t.goarch,
          CGO_ENABLED: "0", // fully static: no glibc version floor
        },
        stdio: ["ignore", "ignore", "inherit"],
      }
    );
    if (t.os !== "win32") chmodSync(outPath, 0o755);
    process.stderr.write("ok\n");

    writeFileSync(
      join(pkgDir, "package.json"),
      JSON.stringify(
        {
          name: pkgName,
          ...common,
          description: `tokentelemetry engine binary for ${t.os}-${t.cpu}`,
          // npm and bun skip an optional dependency whose os/cpu do not match,
          // so only the matching binary is ever downloaded.
          os: [t.os],
          cpu: [t.cpu],
          files: ["bin"],
        },
        null,
        2
      ) + "\n"
    );
    optionalDependencies[pkgName] = VERSION;
  }

  // Launcher package.
  const launcherSrc = join(engineDir, "npm", "launcher");
  const launcherDir = join(distDir, "tokentelemetry");
  mkdirSync(launcherDir, { recursive: true });
  cpSync(join(launcherSrc, "bin"), join(launcherDir, "bin"), { recursive: true });
  chmodSync(join(launcherDir, "bin", "tokentelemetry.js"), 0o755);

  writeFileSync(
    join(launcherDir, "package.json"),
    JSON.stringify(
      {
        name: "tokentelemetry",
        ...common,
        description:
          "Local token and cost telemetry for AI coding agents. Reads logs already on disk; makes no network calls.",
        keywords: ["ai", "agents", "claude", "codex", "tokens", "cost", "observability", "ccusage"],
        bin: { tokentelemetry: "bin/tokentelemetry.js" },
        files: ["bin", "README.md"],
        optionalDependencies,
        engines: { node: ">=18" },
      },
      null,
      2
    ) + "\n"
  );

  const readme = join(engineDir, "README.md");
  try {
    cpSync(readme, join(launcherDir, "README.md"));
  } catch {
    // README is optional at build time.
  }

  process.stderr.write(`\nwrote ${distDir}\n`);
  process.stderr.write(`  tokentelemetry@${VERSION} + ${TARGETS.length} binary packages\n`);
}

build();
