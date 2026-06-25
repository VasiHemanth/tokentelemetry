import type { MetadataRoute } from "next";
import { source } from "@/lib/source";

export const dynamic = "force-static";

const BASE = "https://tokentelemetry.com";

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();

  const staticRoutes: MetadataRoute.Sitemap = [
    { url: BASE, lastModified: now, changeFrequency: "weekly", priority: 1 },
    { url: `${BASE}/resources`, lastModified: now, changeFrequency: "weekly", priority: 0.7 },
    { url: `${BASE}/privacy`, lastModified: now, changeFrequency: "monthly", priority: 0.3 },
  ];

  // Every docs page, derived from the Fumadocs source so the sitemap stays in
  // sync as docs are added/removed (no hardcoded list to forget to update).
  const docRoutes: MetadataRoute.Sitemap = source.getPages().map((page) => ({
    url: `${BASE}${page.url}`,
    lastModified: now,
    changeFrequency: "weekly",
    priority: page.url === "/docs" ? 0.9 : 0.6,
  }));

  return [...staticRoutes, ...docRoutes];
}
