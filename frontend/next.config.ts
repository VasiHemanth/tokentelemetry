import type { NextConfig } from "next";

// Hosts allowed to load the dev server's resources (HMR / JS chunks). Next 15
// blocks non-localhost origins by default; TT_ALLOWED_ORIGINS (wired up by
// bin/cli.js from --allowed-origins) opts specific hosts in for remote/tailnet
// access. Empty by default, so local-only use is unaffected.
const allowedDevOrigins = (process.env.TT_ALLOWED_ORIGINS || "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

const nextConfig: NextConfig = {
  output: "standalone",
  // Electron owns a separate Next dev server. A distinct build directory keeps
  // that server independent of a dashboard a developer may already be running.
  distDir: process.env.TT_NEXT_DIST_DIR || ".next",
  devIndicators: false,
  // This app has its own lockfile inside the repository's launcher package.
  // Pin Turbopack here instead of letting it infer the parent or a user-level
  // lockfile as the workspace root.
  turbopack: { root: process.cwd() },
  // Empty array == default (no extra origins), so this is safe when unset.
  allowedDevOrigins,
};

export default nextConfig;
