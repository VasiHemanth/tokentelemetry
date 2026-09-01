"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { SHORTCUTS, loadBindings, shortcutKey, isTypingTarget, type ShortcutId } from "@/lib/shortcuts";

const LEADER_TIMEOUT_MS = 1200;

const LEADER_BY_ID: Record<ShortcutId, string | undefined> = Object.fromEntries(
  SHORTCUTS.map((s) => [s.id, s.leader]),
) as Record<ShortcutId, string | undefined>;

const ROUTE_BY_ID: Record<ShortcutId, string | undefined> = Object.fromEntries(
  SHORTCUTS.map((s) => [s.id, s.route]),
) as Record<ShortcutId, string | undefined>;

/**
 * App-wide keyboard shortcut dispatcher. Mount it once in the root layout, not
 * per page. Navigation uses the leader pattern (`g` then a letter); `?` opens
 * the shortcut reference. Bindings are read from localStorage (updated by the
 * Settings page) and refreshed whenever they change via a storage event.
 */
export function KeyboardShortcutsProvider() {
  const router = useRouter();
  const pendingRef = useRef<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let bindings = loadBindings();
    const refresh = () => { bindings = loadBindings(); };
    const onStorage = (e: StorageEvent) => { if (e.key === "tt-shortcuts") refresh(); };
    const onCustom = () => refresh();
    window.addEventListener("storage", onStorage);
    window.addEventListener("tt-shortcuts-changed", onCustom);

    const clearPending = () => {
      pendingRef.current = null;
      if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null; }
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (isTypingTarget(event.target)) { clearPending(); return; }
      const key = shortcutKey(event);
      if (!key) { clearPending(); return; }

      const pending = pendingRef.current;
      if (pending) {
        clearPending();
        const id = (Object.keys(bindings) as ShortcutId[]).find((candidate) => {
          const def = LEADER_BY_ID[candidate];
          return def !== undefined && def === pending && bindings[candidate] === key;
        });
        if (id) {
          const route = ROUTE_BY_ID[id];
          if (route) router.push(route);
        }
        return;
      }

      if (key === "g") {
        pendingRef.current = "g";
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(clearPending, LEADER_TIMEOUT_MS);
        return;
      }

      // Single-key shortcut (`?`), which never uses a leader.
      if (key === bindings.help && LEADER_BY_ID.help === undefined) {
        const route = ROUTE_BY_ID.help;
        if (route) router.push(route);
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("tt-shortcuts-changed", onCustom);
      clearPending();
    };
  }, [router]);

  return null;
}
