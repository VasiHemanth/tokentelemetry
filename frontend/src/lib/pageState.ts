"use client";

/**
 * Registry of sessionStorage keys used for persisted page state (UI + scroll).
 */
const registeredKeys = new Set<string>();

/** Tracks a sessionStorage key so it can be purged on menu navigation. */
export function registerStateKey(key: string): void {
  registeredKeys.add(key);
}

/** Removes every tracked page-state and scroll-restoration key. */
export function clearPageState(): void {
  registeredKeys.forEach((key) => {
    try { sessionStorage.removeItem(key); } catch {}
  });
  registeredKeys.clear();
}
