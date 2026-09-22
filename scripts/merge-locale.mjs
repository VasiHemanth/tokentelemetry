#!/usr/bin/env node
/**
 * Recombine translated chunks into a dictionary source file.
 *
 * Translation is done per chunk (see scripts/locales/parts/), each chunk
 * emitting `scripts/locales/out/<tag>-part<N>.json` as a map of entry index →
 * translated string. Indexes rather than English keys mean a translation pass
 * can never silently retype a key.
 *
 *   node scripts/merge-locale.mjs ja            → scripts/locales/ja.json
 *   node scripts/merge-locale.mjs ja --dry      report only
 *
 * Refuses to write when any canonical index is missing, so a half-translated
 * language cannot slip into the bundle unnoticed.
 */

import { readFileSync, writeFileSync, existsSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const DATA = join(ROOT, "scripts", "locales");
const OUT = join(DATA, "out");

const [tag, ...flags] = process.argv.slice(2);
if (!tag) {
  console.error("usage: node scripts/merge-locale.mjs <tag> [--dry]");
  process.exit(1);
}

const canonical = JSON.parse(readFileSync(join(DATA, "en.json"), "utf8"));
const translations = new Map();
const problems = [];

if (!existsSync(OUT)) {
  console.error(`✗ ${OUT} does not exist — run the translation chunks first`);
  process.exit(1);
}

for (const file of readdirSync(OUT).sort()) {
  if (!file.startsWith(`${tag}-part`) || !file.endsWith(".json")) continue;
  const parsed = JSON.parse(readFileSync(join(OUT, file), "utf8"));
  for (const [index, value] of Object.entries(parsed)) {
    const i = Number(index);
    if (!Number.isInteger(i) || i < 0 || i >= canonical.length) {
      problems.push(`${file}: index ${index} is outside 0..${canonical.length - 1}`);
      continue;
    }
    if (typeof value !== "string" || !value.trim()) {
      problems.push(`${file}: entry ${index} is empty`);
      continue;
    }
    if (translations.has(i)) problems.push(`${file}: duplicate entry ${i}`);
    translations.set(i, value);
  }
}

const missing = canonical.map((_, i) => i).filter((i) => !translations.has(i));
const sameAsEnglish = [...translations.entries()].filter(([i, v]) => v === canonical[i]);

console.log(`${tag}: ${translations.size}/${canonical.length} entries`);
if (missing.length) console.log(`  ⚠ ${missing.length} missing — indexes ${missing.slice(0, 20).join(", ")}${missing.length > 20 ? " …" : ""}`);
if (sameAsEnglish.length) console.log(`  · ${sameAsEnglish.length} identical to English (fine for product names, suspicious otherwise)`);
if (problems.length) problems.slice(0, 20).forEach((p) => console.log(`  ✗ ${p}`));

if (flags.includes("--dry")) process.exit(0);
if (missing.length || problems.length) {
  console.error("✗ not written — resolve gaps/duplicates first (re-run the chunk, then merge again)");
  process.exit(1);
}

const dictionary = {};
canonical.forEach((key, i) => {
  dictionary[key] = translations.get(i);
});
writeFileSync(join(DATA, `${tag}.json`), JSON.stringify(dictionary, null, 2) + "\n", "utf8");
console.log(`✓ scripts/locales/${tag}.json`);
console.log(`Next: node scripts/build-locale.mjs ${tag}`);
