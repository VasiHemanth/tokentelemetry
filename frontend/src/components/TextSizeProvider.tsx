"use client";

import { createContext, useContext, useMemo, useSyncExternalStore } from "react";
import { normalizeTextSize, TEXT_SIZE_CHANGE_EVENT, TEXT_SIZE_DEFAULT, TEXT_SIZE_STORAGE_KEY } from "@/lib/textSize";

interface TextSizeContextValue {
  percent: number;
  /** Applies immediately and reports whether local persistence succeeded. */
  setPercent: (percent: number) => boolean;
}

const TextSizeContext = createContext<TextSizeContextValue | null>(null);

function applyDocumentSize(percent: number) {
  document.documentElement.setAttribute("data-text-size", String(percent));
  document.documentElement.style.setProperty("--tt-text-scale", String(percent / 100));
}

function getSnapshot() {
  return normalizeTextSize(document.documentElement.getAttribute("data-text-size"));
}

function subscribe(onChange: () => void) {
  const onStorage = (event: StorageEvent) => {
    if (event.key !== TEXT_SIZE_STORAGE_KEY && event.key !== null) return;
    applyDocumentSize(normalizeTextSize(event.newValue));
    window.dispatchEvent(new Event(TEXT_SIZE_CHANGE_EVENT));
  };
  window.addEventListener(TEXT_SIZE_CHANGE_EVENT, onChange);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(TEXT_SIZE_CHANGE_EVENT, onChange);
    window.removeEventListener("storage", onStorage);
  };
}

function setPercent(value: number): boolean {
  const percent = normalizeTextSize(value);
  applyDocumentSize(percent);
  let persisted = true;
  try { localStorage.setItem(TEXT_SIZE_STORAGE_KEY, String(percent)); } catch { persisted = false; }
  window.dispatchEvent(new Event(TEXT_SIZE_CHANGE_EVENT));
  return persisted;
}

/** One preference spans every app route and synchronizes open tabs on this origin. */
export function TextSizeProvider({ children }: { children: React.ReactNode }) {
  const percent = useSyncExternalStore(subscribe, getSnapshot, () => TEXT_SIZE_DEFAULT);
  const value = useMemo(() => ({ percent, setPercent }), [percent]);
  return <TextSizeContext.Provider value={value}>{children}</TextSizeContext.Provider>;
}

export function useTextSize() {
  const context = useContext(TextSizeContext);
  if (!context) throw new Error("useTextSize must be used inside TextSizeProvider");
  return context;
}
