// Build-time screenshot optimizer (static export has no next/image optimizer).
//
// Generates WebP variants of public/screenshots/*.png at the widths below into
// public/screenshots/opt/, committed to the repo. Runs before `next build`
// (see package.json "build") and is idempotent: a variant is only re-encoded
// when it is missing or older than its source PNG.
//
// Consumers build srcsets via src/lib/shots.ts — keep WIDTHS in sync with it.
import { mkdirSync, readdirSync, statSync, utimesSync } from "node:fs";
import { basename, join } from "node:path";
import sharp from "sharp";

const SRC_DIR = new URL("../public/screenshots/", import.meta.url).pathname;
const OUT_DIR = join(SRC_DIR, "opt");
const WIDTHS = [1000, 1600, 2000];
const WEBP_OPTS = { quality: 82, effort: 4 };

const fresh = (out, srcMtime) => {
  try {
    return statSync(out).mtimeMs >= srcMtime;
  } catch {
    return false;
  }
};

const kb = (n) => `${(n / 1024).toFixed(0)}KB`;

mkdirSync(OUT_DIR, { recursive: true });

const pngs = readdirSync(SRC_DIR).filter((f) => f.endsWith(".png"));
let encoded = 0;
let skipped = 0;
let srcTotal = 0;
let outTotal = 0;

for (const file of pngs) {
  const src = join(SRC_DIR, file);
  const { mtimeMs, size: srcSize } = statSync(src);
  srcTotal += srcSize;
  const name = basename(file, ".png");
  const meta = await sharp(src).metadata();

  for (const w of WIDTHS) {
    const out = join(OUT_DIR, `${name}-${w}.webp`);
    if (fresh(out, mtimeMs)) {
      skipped++;
      outTotal += statSync(out).size;
      continue;
    }
    // Never upscale: cap at the source width (srcset descriptor stays `${w}w`,
    // so the browser just treats it as a slightly smaller candidate).
    const width = Math.min(w, meta.width ?? w);
    const { size } = await sharp(src)
      .resize({ width })
      .webp(WEBP_OPTS)
      .toFile(out);
    // Stamp output mtime from the source so freshness checks stay stable.
    const t = new Date(mtimeMs + 1);
    utimesSync(out, t, t);
    outTotal += size;
    encoded++;
    console.log(`optimize-images: ${name}-${w}.webp ${kb(srcSize)} -> ${kb(size)}`);
  }
}

console.log(
  `optimize-images: ${pngs.length} PNGs (${kb(srcTotal)}) -> ${
    encoded + skipped
  } WebP variants (${kb(outTotal)}); encoded ${encoded}, fresh ${skipped}`
);
