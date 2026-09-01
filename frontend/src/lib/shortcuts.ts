"use client";

/**
 * Keyboard shortcuts for the dashboard.
 *
 * Navigation uses the GitHub/Grafana "leader" pattern: press `g`, then a letter
 * within a short window (e.g. `g` then `h` for home). The `help` shortcut is a
 * single key (`?`). Bindings are stored per-user in localStorage and are
 * rebindable from Settings → Keyboard shortcuts; this module is the pure logic
 * and storage layer so it can be unit-tested without React.
 */

export type ShortcutId =
  | "home"
  | "analytics"
  | "projects"
  | "traces"
  | "settings"
  | "hermes"
  | "local-models"
  | "help";

export interface ShortcutDef {
  id: ShortcutId;
  label: string;
  description: string;
  /** The leader key for sequence-style shortcuts (`g`), else null. */
  leader: string | null;
  /** The default second key (or single key for singleton shortcuts). */
  defaultKey: string;
  /** The route the shortcut navigates to, when it navigates. */
  route?: string;
  /** `sequence` = leader + key; `single` = one key with no leader. */
  kind: "sequence" | "single";
}

export const SHORTCUTS: ShortcutDef[] = [
  { id: "home",         label: "Go to dashboard", description: "Wireframe overview of today's activity.",         leader: "g", defaultKey: "h", route: "/",                             kind: "sequence" },
  { id: "analytics",    label: "Go to analytics", description: "Token and cost breakdowns across agents and models.", leader: "g", defaultKey: "a", route: "/analytics",                     kind: "sequence" },
  { id: "projects",     label: "Go to projects",  description: "One card per working directory.",                   leader: "g", defaultKey: "p", route: "/projects",                      kind: "sequence" },
  { id: "traces",       label: "Go to sessions",  description: "Replayable per-session traces.",                   leader: "g", defaultKey: "t", route: "/sessions",                      kind: "sequence" },
  { id: "settings",     label: "Go to settings",  description: "Configuration, billing, privacy and shortcuts.",   leader: "g", defaultKey: "s", route: "/settings",                      kind: "sequence" },
  { id: "hermes",       label: "Go to Hermes",    description: "Autonomous-agent hub.",                            leader: "g", defaultKey: "e", route: "/hermes",                        kind: "sequence" },
  { id: "local-models", label: "Go to local models", description: "Local power and energy insights.",              leader: "g", defaultKey: "l", route: "/local-models",                  kind: "sequence" },
  { id: "help",         label: "Show shortcut help", description: "Open the shortcut reference in Settings.",       leader: null, defaultKey: "?", route: "/settings?section=shortcuts",   kind: "single" },
];

const STORAGE_KEY = "tt-shortcuts";

export function defaultBindings(): Record<ShortcutId, string> {
  const out = {} as Record<ShortcutId, string>;
  for (const s of SHORTCUTS) out[s.id] = s.defaultKey;
  return out;
}

export function loadBindings(): Record<ShortcutId, string> {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return defaultBindings();
    const parsed = JSON.parse(raw) as Partial<Record<ShortcutId, string>>;
    const defaults = defaultBindings();
    for (const s of SHORTCUTS) {
      const stored = parsed[s.id];
      if (typeof stored === "string" && stored.length === 1) defaults[s.id] = stored;
    }
    return defaults;
  } catch {
    return defaultBindings();
  }
}

export function saveBindings(bindings: Record<ShortcutId, string>): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(bindings));
  } catch {
    /* storage may be blocked; shortcuts just reset on next load */
  }
}

/**
 * The canonical key for a keydown, or null when the key is not a shortcut key.
 * Letters are lowercased; `?` (from Shift+/ on a US layout) is kept as-is.
 * Anything with Ctrl/Alt/Meta or a modifier is ignored so shortcuts never clash
 * with a browser/devtools or an OS-level chord.
 */
export function shortcutKey(event: Pick<KeyboardEvent, "key" | "ctrlKey" | "altKey" | "metaKey">): string | null {
  if (event.ctrlKey || event.altKey || event.metaKey) return null;
  const key = event.key;
  if (key === "?") return "?";
  if (/^[a-zA-Z]$/.test(key)) return key.toLowerCase();
  return null;
}

export function isTypingTarget(target: EventTarget | null): boolean {
  if (typeof HTMLElement === "undefined") return false;
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT" ||
    target.isContentEditable
  );
}

/**
 * True when the given key is bound to a shortcut that has the provided leader.
 * Used by the provider to decide whether to enter the leader-armed state and to
 * resolve a follow-up key.
 */
export function bindingUsesLeader(bindings: Record<ShortcutId, string>, id: ShortcutId, leader: string | null): boolean {
  return SHORTCUTS.find((s) => s.id === id)?.leader === leader;
}

export function shortcutRoute(id: ShortcutId): string | undefined {
  return SHORTCUTS.find((s) => s.id === id)?.route;
}

/** Human label for a chord, e.g. "g then h" or "?". */
export function describeBinding(def: ShortcutDef, key: string): string {
  return def.leader ? `${def.leader} then ${key}` : key;
}

/** The badge tokens to render a chord, e.g. ["g", "h"] or ["?"]. */
export function chordTokens(def: ShortcutDef, key: string): string[] {
  return def.leader ? [def.leader, key] : [key];
}
