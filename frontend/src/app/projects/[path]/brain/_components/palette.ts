/* Node colors follow the page TYPE (identity encoding). The seven known OKF
 * types take the dataviz reference categorical palette slots 1-7 in fixed
 * order; the first unknown type (alphabetically) takes slot 8; any further
 * unknown types fold into neutral gray rather than cycling hues. Both light
 * and dark steps were validated (lightness band, chroma, CVD separation,
 * contrast) against the app surfaces #fbfbfd / #11141a. */

export interface TypeSlot {
  light: string;
  dark: string;
}

const SLOTS: TypeSlot[] = [
  { light: "#2a78d6", dark: "#3987e5" }, // 1 blue
  { light: "#1baf7a", dark: "#199e70" }, // 2 aqua
  { light: "#eda100", dark: "#c98500" }, // 3 yellow
  { light: "#008300", dark: "#008300" }, // 4 green
  { light: "#4a3aa7", dark: "#9085e9" }, // 5 violet
  { light: "#e34948", dark: "#e66767" }, // 6 red
  { light: "#e87ba4", dark: "#d55181" }, // 7 magenta
  { light: "#eb6834", dark: "#d95926" }, // 8 orange
];

export const GRAY: TypeSlot = { light: "#64748b", dark: "#64748b" };

const KNOWN_ORDER = [
  "overview", "subsystem", "feature", "decision", "convention", "playbook", "analysis",
];

/** Fixed type->slot assignment for a wiki's observed types. */
export function buildTypePalette(types: string[]): Map<string, TypeSlot> {
  const map = new Map<string, TypeSlot>();
  for (let i = 0; i < KNOWN_ORDER.length; i++) map.set(KNOWN_ORDER[i], SLOTS[i]);
  const unknown = types
    .map((t) => t.toLowerCase())
    .filter((t) => t && t !== "untyped" && !map.has(t))
    .sort();
  if (unknown.length > 0) map.set(unknown[0], SLOTS[7]);
  for (const t of unknown.slice(1)) map.set(t, GRAY);
  return map;
}

export function typeSlot(palette: Map<string, TypeSlot>, type: string | null): TypeSlot {
  if (!type) return GRAY;
  return palette.get(type.toLowerCase()) ?? GRAY;
}
