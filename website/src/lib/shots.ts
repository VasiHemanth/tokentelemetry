/**
 * Srcset helpers for the WebP screenshot variants that
 * scripts/optimize-images.mjs generates into public/screenshots/opt/.
 * WIDTHS must match the script. The original PNG stays the <img> fallback.
 */
export const SHOT_WIDTHS = [1000, 1600, 2000] as const;

/** "/screenshots/dashboard.png" -> "/screenshots/opt/dashboard-1000.webp 1000w, …" */
export function webpSrcSet(png: string): string {
  const base = png
    .replace(/^\/screenshots\//, "/screenshots/opt/")
    .replace(/\.png$/, "");
  return SHOT_WIDTHS.map((w) => `${base}-${w}.webp ${w}w`).join(", ");
}
