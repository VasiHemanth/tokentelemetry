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
  devIndicators: false,
  // Empty array == default (no extra origins), so this is safe when unset.
  allowedDevOrigins,
};

export default nextConfig;
