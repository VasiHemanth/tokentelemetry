// Static-export fix: Next auto-routes the OG image at /opengraph-image (no extension),
// which GitHub Pages serves with the wrong Content-Type. Rename to og.png and rewrite
// all HTML references so social scrapers fetch a valid image/png URL.
import { readdirSync, readFileSync, renameSync, existsSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const out = join(process.cwd(), "out");
const src = join(out, "opengraph-image");
const dest = join(out, "og.png");

if (!existsSync(src)) {
  console.warn("post-build: opengraph-image not found, skipping");
  process.exit(0);
}

renameSync(src, dest);
console.log("post-build: opengraph-image -> og.png");

const walk = (dir) => {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p);
    else if (p.endsWith(".html")) {
      const before = readFileSync(p, "utf8");
      const after = before.replace(/\/opengraph-image(\?[^"'\s]*)?/g, "/og.png");
      if (before !== after) {
        writeFileSync(p, after);
        console.log(`post-build: rewrote OG URL in ${p.replace(out, "out")}`);
      }
    }
  }
};

walk(out);
