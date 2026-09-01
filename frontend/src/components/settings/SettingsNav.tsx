"use client";

import { useMemo, useState } from "react";
import {
  Settings2, CreditCard, Bot, Database, Shield, Plug, Keyboard, Search, ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { SETTINGS_CATEGORIES, categoryAnchor } from "./categories";

const CATEGORY_ICONS: Record<string, typeof Settings2> = {
  general: Settings2,
  agents: Bot,
  billing: CreditCard,
  data: Database,
  privacy: Shield,
  access: Plug,
  shortcuts: Keyboard,
};

export function SettingsNav({ active }: { active?: string | null }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(SETTINGS_CATEGORIES.map((c) => [c.id, true])),
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return SETTINGS_CATEGORIES;
    return SETTINGS_CATEGORIES.map((cat) => ({
      ...cat,
      items: cat.items.filter(
        (item) => item.label.toLowerCase().includes(q) || item.description.toLowerCase().includes(q),
      ),
    })).filter((cat) => cat.items.length > 0);
  }, [query]);

  const jump = (catId: string) => {
    document.getElementById(categoryAnchor(catId))?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <nav className="w-full min-w-0">
      <div className="relative mb-3">
        <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--tt-fg-faint)]" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search settings"
          aria-label="Search settings"
          className="h-8 w-full rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-sunken)] pl-8 pr-3 text-[12px] text-[var(--tt-fg)] placeholder:text-[var(--tt-fg-faint)] outline-none focus:border-[var(--tt-border-strong)]"
        />
      </div>

      <div className="space-y-0.5">
        {filtered.map((cat) => {
          const Icon = CATEGORY_ICONS[cat.id] ?? Settings2;
          const isOpen = open[cat.id] !== false;
          const isActive = active === cat.id;
          return (
            <div key={cat.id}>
              <button
                onClick={() => setOpen((prev) => ({ ...prev, [cat.id]: !isOpen }))}
                className={cn(
                  "flex w-full items-center gap-2 rounded-[var(--tt-radius)] px-2 py-1.5 text-left text-[13px] transition-colors",
                  "text-[var(--tt-fg-muted)] hover:bg-[var(--tt-tint)] hover:text-[var(--tt-fg)]",
                  isActive && "tt-tint-1 text-[var(--tt-fg)]",
                )}
              >
                <Icon size={14} className="shrink-0 opacity-80" />
                <span className="flex-1 truncate font-medium">{cat.label}</span>
                <ChevronRight
                  size={13}
                  className={cn("shrink-0 text-[var(--tt-fg-faint)] transition-transform", isOpen && "rotate-90")}
                />
              </button>
              {isOpen && (
                <div className="ml-5 pl-2 border-l border-[var(--tt-border)] space-y-0.5 py-0.5">
                  {cat.items.map((item) => (
                    <button
                      key={item.id}
                      onClick={() => jump(cat.id)}
                      className="w-full rounded px-2 py-1 text-left text-[12px] text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)] hover:bg-[var(--tt-tint)] transition-colors truncate"
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          );
        })}
        {filtered.length === 0 && (
          <p className="px-2 py-1 text-[12px] text-[var(--tt-fg-faint)]">No settings match “{query}”.</p>
        )}
      </div>
    </nav>
  );
}
