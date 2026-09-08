import type { NextConfig } from "next";

// Hosts allowed to load the dev server's resources (HMR / JS chunks). Next 15
// blocks non-localhost origins by default; TT_ALLOWED_ORIGINS (wired up by
// bin/cli.js from --allowed-origins) opts specific hosts in for remote/tailnet
// access. Empty by default, so local-only use is unaffected.
// Next matches these as hostnames, but a full origin ("https://box.ts.net/") is
// the natural thing to pass to --allowed-origins, so reduce each entry to its
// host first. Mirrors _origin_host() in backend/main.py and originHost() in
// bin/cli.js, so all three consumers of the list agree on what an entry means.
const allowedDevOrigins = (process.env.TT_ALLOWED_ORIGINS || "")
  .split(",")
  .map((s) => {
    const h = s.trim().toLowerCase();
    if (!h) return "";
    const rest = h.includes("://") ? h.slice(h.indexOf("://") + 3) : h;
    const hostPort = rest.split("/")[0].split("?")[0].split("#")[0];
    if (hostPort.startsWith("[")) {
      const end = hostPort.indexOf("]");
      return end === -1 ? hostPort : hostPort.slice(0, end + 1);
    }
    return hostPort.split(":")[0];
  })
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
