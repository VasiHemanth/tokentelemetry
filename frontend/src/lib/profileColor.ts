// Deterministic per-profile color, mirroring Hermes desktop's own idiom
// (apps/desktop/src/lib/profile-color.ts): hue hashed from the profile name,
// fixed saturation/lightness, so a profile keeps its color everywhere without
// any stored state. The default home is intentionally neutral (null) — only
// named profiles get an identity color, same as the desktop app.

export function profileHue(name: string): number {
  let h = 0;
  for (let i = 0; i < name.length; i++) {
    h = (h * 31 + name.charCodeAt(i)) >>> 0;
  }
  return h % 360;
}

export function profileColor(name: string | null | undefined): string | null {
  if (!name || name === "default") return null;
  return `hsl(${profileHue(name)} 68% 58%)`;
}

/** Soft translucent fill for backgrounds behind the solid color. */
export function profileTint(name: string | null | undefined): string | null {
  if (!name || name === "default") return null;
  return `hsl(${profileHue(name)} 68% 58% / 0.15)`;
}
