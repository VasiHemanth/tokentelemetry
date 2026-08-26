"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

export type Theme = "dark" | "light";
const STORAGE_KEY = "tt-theme";

interface ThemeCtx {
  theme: Theme;
  toggleTheme: () => void;
  setTheme: (t: Theme) => void;
}

const Ctx = createContext<ThemeCtx | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  // Always start with "dark" so server and first client render agree.
  // The no-flash script has already set <html data-theme="…"> for paint;
  // we sync React state to match in a useEffect after mount.
  const [theme, setThemeState] = useState<Theme>("dark");

  const apply = useCallback((t: Theme) => {
    document.documentElement.setAttribute("data-theme", t);
    try { localStorage.setItem(STORAGE_KEY, t); } catch {}
    setThemeState(t);
  }, []);

  /* Sync state from the no-flash script's attribute on mount */
  useEffect(() => {
    const t = document.documentElement.getAttribute("data-theme");
    // The pre-paint script owns the DOM value; state synchronizes after hydration.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (t === "light" || t === "dark") setThemeState(t);
  }, []);

  /* Cross-tab sync */
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY && (e.newValue === "light" || e.newValue === "dark")) {
        apply(e.newValue);
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [apply]);

  const value: ThemeCtx = {
    theme,
    setTheme: apply,
    toggleTheme: () => apply(theme === "dark" ? "light" : "dark"),
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
