import type { NextConfig } from "next";
import { createMDX } from "fumadocs-mdx/next";

const withMDX = createMDX();

const nextConfig: NextConfig = {
  output: "export",
  // trailingSlash: true generates /docs/index.html instead of /docs.html,
  // which is required for GitHub Pages to serve /docs correctly.
  trailingSlash: true,
  images: { unoptimized: true },
};

export default withMDX(nextConfig);
