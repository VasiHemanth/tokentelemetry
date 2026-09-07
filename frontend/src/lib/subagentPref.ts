"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * "Show delegated sessions" preference, shared by the dashboard, every project
 * activity tab, and Settings.
 *
 * One key, several surfaces: flipping the toggle anywhere is the same decision,
 * so a change made on a project page is reflected in Settings and on the
 * dashboard without a reload. Same mechanism as `tt-show-local-dash` — a
 * localStorage key plus a `storage` event, which fires cross-tab natively and
 * is dispatched manually for the current tab.
 *
 * Deliberately localStorage rather than a backend preference: this is a view
 * choice, it should not need the API to be reachable, and it matches the
 * existing dashboard preferences. The cost is that it is per-browser.
 */
export const SHOW_SUBAGENTS_KEY = "tt-show-subagents";

export function readShowSubagents(): boolean {
  try {
    return localStorage.getItem(SHOW_SUBAGENTS_KEY) === "true";
  } catch {
    // Private mode / blocked storage: fall back to the collapsed default.
    return false;
  }
}

export function writeShowSubagents(next: boolean): void {
  try {
    localStorage.setItem(SHOW_SUBAGENTS_KEY, String(next));
  } catch {
    // Non-persistent is still better than throwing mid-render.
  }
  window.dispatchEvent(new Event("storage"));
}

/**
 * Reads the preference and keeps it live. Returns `false` on the first render
 * so server and client markup agree, then settles to the stored value after
 * mount — the same hydration dance `DashboardPreferencesToggle` does.
 */
export function useShowSubagents(): [boolean, (next: boolean) => void] {
  const [show, setShow] = useState(false);

  useEffect(() => {
    const sync = () => setShow(readShowSubagents());
    sync();
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);

  const set = useCallback((next: boolean) => {
    setShow(next);
    writeShowSubagents(next);
  }, []);

  return [show, set];
}
