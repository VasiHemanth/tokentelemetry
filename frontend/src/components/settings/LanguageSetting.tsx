"use client";

import { useSyncExternalStore } from "react";
import { Languages } from "lucide-react";
import { cn } from "@/lib/cn";
import { getLocale, setLocale, subscribe } from "@/lib/i18n/locale";
import { BASE_LOCALE, LOCALES } from "@/lib/i18n/registry";

/**
 * Language picker: one pill per registered locale, deliberately the same markup
 * and tokens as <ThemeSetting> in the card above it (the Settings page supplies
 * the `p-5`). Languages are listed in their own script — that is the point of the
 * control — with the English name on hover.
 *
 * The choice is applied in place by <LocaleOverlay> (no reload) and persisted by
 * the locale store, so this component only reads and writes the registry tag.
 */
export function LanguageSetting() {
  const locale = useSyncExternalStore(
    subscribe,
    getLocale,
    () => BASE_LOCALE,
  );

  return (
    <div className="space-y-3">
      <div
        className="flex flex-wrap items-center gap-2"
        role="radiogroup"
        aria-label="Interface language"
      >
        {LOCALES.map((option) => {
          const active = option.tag === locale;
          return (
            <button
              key={option.tag}
              type="button"
              role="radio"
              aria-checked={active}
              title={option.englishName}
              onClick={() => setLocale(option.tag)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-[var(--tt-radius)] border px-3 py-1.5 text-[12px] transition-colors cursor-pointer",
                active
                  ? "border-[var(--tt-border-strong)] tt-tint-1 text-[var(--tt-fg)]"
                  : "border-[var(--tt-border)] text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] hover:border-[var(--tt-border-strong)]",
              )}
            >
              <Languages size={13} /> {option.nativeName}
            </button>
          );
        })}
      </div>
      <p className="text-[12px] text-[var(--tt-fg-dim)]">
        Strings that are not matched exactly — numbers, names, tooltips — stay English.
      </p>
    </div>
  );
}
