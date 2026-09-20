/**
 * Tiny, dependency-free locale store for the runtime-translation overlay.
 * Lives outside React so both the overlay and the sidebar switch can read and
 * react to the current language without a context/provider.
 *
 * Language is persisted in localStorage (`tt-locale`, mirroring `tt-theme`).
 * Changing it notifies subscribers so the overlay translates/restores in place
 * — deliberately WITHOUT a page reload, which would flash the default-expanded
 * sidebar before the collapsed state is restored.
 */

export type Locale = "en" | "zh";

const STORAGE_KEY = "tt-locale";

function read(): Locale {
  try {
    return localStorage.getItem(STORAGE_KEY) === "zh" ? "zh" : "en";
  } catch {
    return "en";
  }
}

let current: Locale | null = null;
const listeners = new Set<() => void>();

function ensure() {
  if (current === null) current = read();
}

export function getLocale(): Locale {
  ensure();
  return current as Locale;
}

export function setLocale(locale: Locale): void {
  ensure();
  if (current === locale) return;
  current = locale;
  try {
    localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    /* storage disabled — the in-memory switch still applies */
  }
  try {
    document.documentElement.lang = locale;
  } catch {
    /* not attached yet */
  }
  listeners.forEach((cb) => cb());
}

/** Subscribe to language changes; returns an unsubscribe fn. */
export function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}
