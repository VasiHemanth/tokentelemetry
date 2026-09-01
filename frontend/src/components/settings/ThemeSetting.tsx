"use client";

import { Monitor, Sun, Moon } from "lucide-react";
import { cn } from "@/lib/cn";
import { useTheme, type ThemeMode } from "../ThemeProvider";

const OPTIONS: { value: ThemeMode; label: string; icon: typeof Monitor }[] = [
  { value: "system", label: "System", icon: Monitor },
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
];

/** Theme picker: System / Light / Dark, persisted via the ThemeProvider. */
export function ThemeSetting() {
  const { mode, setMode } = useTheme();

  return (
    <div className="flex flex-wrap items-center gap-2" role="radiogroup" aria-label="Theme">
      {OPTIONS.map((opt) => {
        const Icon = opt.icon;
        const active = mode === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => setMode(opt.value)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-[var(--tt-radius)] border px-3 py-1.5 text-[12px] transition-colors cursor-pointer",
              active
                ? "border-[var(--tt-border-strong)] tt-tint-1 text-[var(--tt-fg)]"
                : "border-[var(--tt-border)] text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] hover:border-[var(--tt-border-strong)]",
            )}
          >
            <Icon size={13} /> {opt.label}
          </button>
        );
      })}
    </div>
  );
}
