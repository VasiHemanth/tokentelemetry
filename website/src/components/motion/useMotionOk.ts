"use client";
/**
 * Single source of truth for prefers-reduced-motion at animejs call sites.
 *
 * - `motionOk()` — plain util, safe to call inside effects/handlers (client
 *   only). Returns false during SSR so nothing animates before hydration.
 * - `useMotionOk()` — reactive hook; re-renders when the OS setting flips.
 *
 * Every animejs call MUST be gated with `if (!motionOk()) { render final
 * state; return; }`. motion/react components should keep using
 * `useReducedMotion()` from "motion/react"; this util exists for imperative
 * (animejs / class-toggle) call sites.
 */
import { useSyncExternalStore } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

export function motionOk(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return !window.matchMedia(QUERY).matches;
}

function subscribe(onChange: () => void): () => void {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return () => {};
  }
  const mql = window.matchMedia(QUERY);
  mql.addEventListener("change", onChange);
  return () => mql.removeEventListener("change", onChange);
}

export function useMotionOk(): boolean {
  return useSyncExternalStore(subscribe, motionOk, () => false);
}
