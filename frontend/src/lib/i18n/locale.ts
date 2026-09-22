/**
 * Tiny, dependency-free locale store for the runtime-translation overlay.
 * Lives outside React so both the overlay and the sidebar switch can read and
 * react to the current language without a context/provider.
 *
 * Language-agnostic by design: it stores whatever tag `registry.ts` knows
 * about, so adding a language never touches this file.
 *
 * Language is persisted in localStorage (`tt-locale`, mirroring `tt-theme`).
 * Changing it notifies subscribers so the overlay translates/restores in place
 * — deliberately WITHOUT a page reload, which would flash the default-expanded
 * sidebar before the collapsed state is restored.
 */

import { BASE_LOCALE, applyDocumentLocale, normalizeTag } from "./registry";

/** A locale tag registered in `registry.ts`. `en` is the source language. */
export type Locale = string;

const STORAGE_KEY = "tt-locale";

function read(): Locale {
  try {
    return normalizeTag(localStorage.getItem(STORAGE_KEY));
  } catch {
    return BASE_LOCALE;
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
  const next = normalizeTag(locale);
  ensure();
  if (current === next) return;
  current = next;
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch {
    /* storage disabled — the in-memory switch still applies */
  }
  applyDocumentLocale(next);
  listeners.forEach((cb) => cb());
}

/** Subscribe to language changes; returns an unsubscribe fn. */
export function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}
