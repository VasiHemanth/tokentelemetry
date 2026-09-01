"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

export type Theme = "dark" | "light";
export type ThemeMode = Theme | "system";
const STORAGE_KEY = "tt-theme";

interface ThemeCtx {
  /** The resolved theme (what is actually applied). */
  theme: Theme;
  /** The chosen mode: dark, light, or the OS setting. */
  mode: ThemeMode;
  setMode: (m: ThemeMode) => void;
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
}

const Ctx = createContext<ThemeCtx | null>(null);

function systemTheme(): Theme {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: light)").matches
    ? "light"
    : "dark";
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  // Always start with "dark" so server and first client render agree.
  // The no-flash script has already set <html data-theme="…"> for paint;
  // we sync React state to match in a useEffect after mount.
  const [theme, setThemeState] = useState<Theme>("dark");
  const [mode, setModeState] = useState<ThemeMode>("system");

  const applyMode = useCallback((m: ThemeMode) => {
    const resolved = m === "system" ? systemTheme() : m;
    document.documentElement.setAttribute("data-theme", resolved);
    try { localStorage.setItem(STORAGE_KEY, m); } catch {}
    setModeState(m);
    setThemeState(resolved);
  }, []);

  /* Sync state from the no-flash script's attribute on mount; also pick up the
     stored mode (default "system", which the no-flash script already honours). */
  useEffect(() => {
    let stored: ThemeMode = "system";
    try {
      const s = localStorage.getItem(STORAGE_KEY);
      if (s === "light" || s === "dark" || s === "system") stored = s;
    } catch {}
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setModeState(stored);
    const t = document.documentElement.getAttribute("data-theme");
    // The pre-paint script owns the DOM value; state synchronizes after hydration.
    if (t === "light" || t === "dark") setThemeState(t);
  }, []);

  /* Follow OS changes while in "system" mode. */
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: light)");
    const onChange = () => {
      setModeState((prev) => {
        if (prev === "system") {
          const resolved = mq.matches ? "light" : "dark";
          document.documentElement.setAttribute("data-theme", resolved);
          setThemeState(resolved);
        }
        return prev;
      });
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  /* Cross-tab sync */
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) {
        const m: ThemeMode = e.newValue === "light" || e.newValue === "dark" || e.newValue === "system"
          ? e.newValue
          : "system";
        applyMode(m);
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [applyMode]);

  const value: ThemeCtx = {
    theme,
    mode,
    setMode: applyMode,
    setTheme: applyMode,
    toggleTheme: () => applyMode(theme === "dark" ? "light" : "dark"),
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useTheme(): ThemeCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useTheme must be used inside <ThemeProvider>");
  return v;
}

/** Inline script — runs before paint to set data-theme so there's no FOUC. */
export const NO_FLASH_SCRIPT = `
try {
  var t = localStorage.getItem('${STORAGE_KEY}');
  if (t !== 'light' && t !== 'dark') {
    t = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  }
  document.documentElement.setAttribute('data-theme', t);
} catch (_) {
  document.documentElement.setAttribute('data-theme', 'dark');
}
`.trim();
