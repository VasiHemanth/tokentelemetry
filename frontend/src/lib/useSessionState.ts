"use client";

import { useCallback, useEffect, useState } from "react";
import { registerStateKey } from "@/lib/pageState";

export type StateSetter<T> = Partial<T> | ((prev: T) => T);

function readStorage<T>(key: string): T | null {
  try {
    const item = sessionStorage.getItem(key);
    return item !== null ? (JSON.parse(item) as T) : null;
  } catch {
    return null;
  }
}

/**
 * Custom hook that persists React state to sessionStorage under a single key.
 *
 * - Automatically saves state to sessionStorage and restores it on page remount.
 * - Merges saved state with default values so missing fields are safely filled.
 * - Supports partial state updates (patching).
 */
export function useSessionState<T extends object>(key: string, defaults: T): [T, (patch: StateSetter<T>) => void] {
  const [state, setState] = useState<T>(() => {
    if (typeof window === "undefined") return defaults;
    const stored = readStorage<Partial<T>>(key);
    return stored ? { ...defaults, ...stored } : defaults;
  });

  useEffect(() => {
    registerStateKey(key);
  }, [key]);

  useEffect(() => {
    try { sessionStorage.setItem(key, JSON.stringify(state)); } catch {}
  }, [key, state]);

  const set = useCallback((patch: StateSetter<T>) => {
    setState((prev) =>
      typeof patch === "function" ? patch(prev) : { ...prev, ...patch }
    );
  }, []);

  return [state, set];
}
