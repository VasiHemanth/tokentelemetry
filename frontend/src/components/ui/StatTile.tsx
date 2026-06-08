import * as React from "react";
import { cn } from "@/lib/cn";

export interface StatTileProps {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  icon?: React.ReactNode;
  delta?: { value: string; positive?: boolean };
  accent?: string;       // CSS color for left accent bar
  className?: string;
}

export function StatTile({ label, value, hint, icon, delta, accent, className }: StatTileProps) {
  return (
    <div
      className={cn(
        "group relative overflow-hidden rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] p-5 transition-colors hover:border-[var(--tt-border-strong)]",
        className,
      )}
    >
      {accent && (
        <span
          aria-hidden
          className="absolute left-0 top-4 bottom-4 w-[3px] rounded-r-full"
          style={{ backgroundColor: accent, boxShadow: `0 0 12px ${accent}55` }}
        />
      )}
      <div className="flex items-start justify-between gap-3">
        <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--tt-fg-dim)]">
          {label}
        </div>
        {icon && (
          <div className="text-[var(--tt-fg-dim)] group-hover:text-[var(--tt-fg-muted)] transition-colors">
            {icon}
          </div>
        )}
      </div>
      <div className="mt-3 flex items-baseline gap-2">
        <div className="tabular text-[28px] leading-none font-semibold tracking-[-0.02em] text-[var(--tt-fg)]">
          {value}
        </div>
        {delta && (
          <span className={cn("text-[11px] font-medium tabular", delta.positive ? "text-emerald-400" : "text-rose-400")}>
            {delta.positive ? "▲" : "▼"} {delta.value}
          </span>
        )}
      </div>
      {hint && (
        <div
          className="mt-2 text-[11px] leading-snug text-[var(--tt-fg-dim)] tabular"
          title={typeof hint === "string" ? hint : undefined}
        >
          {hint}
        </div>
      )}
    </div>
  );
}
