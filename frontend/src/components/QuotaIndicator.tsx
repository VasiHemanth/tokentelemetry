"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Gauge } from "lucide-react";

import { cn } from "@/lib/cn";
import { AgentLogo } from "@/components/icons/AgentLogo";
import {
  QUOTA_WARN_AT, quotaColor, quotaPercent, worstWindowFor,
  type QuotaCapability, type QuotaSnapshot, type QuotaWindow,
} from "@/lib/quotas";
import { useQuotas } from "./QuotaProvider";

/**
 * Sidebar-bottom plan-limit gauge, built for the collapsed (72px) rail.
 *
 * The icon is tinted by the nearest ceiling across every signed-in provider, so
 * "am I about to be cut off?" is answerable without interacting. Hovering (or
 * focusing, or clicking) opens the per-provider breakdown; the colour is not
 * hidden behind the hover, because a limit you only learn about by pointing at
 * the right pixel is one you find out about by hitting it.
 */
export default function QuotaIndicator({ collapsed }: { collapsed: boolean }) {
  const { data, worst } = useQuotas();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    const onClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  const providers = Object.entries(data?.providers ?? {});
  const unavailable = Object.values(data?.capabilities ?? {}).filter((c) => c.state !== "available");
  if (providers.length === 0 && unavailable.length === 0) return null;

  const tone = worst && worst.pct >= QUOTA_WARN_AT ? quotaColor(worst.pct) : undefined;
  const reading = worst ? `${Math.round(worst.pct)}%` : null;

  return (
    <div
      ref={rootRef}
      className="relative"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label={worst
          ? `Plan limits: ${worst.displayName} ${worst.label} ${Math.round(worst.pct)}% used`
          : "Plan limits"}
        aria-expanded={open}
        title={collapsed ? "Plan limits" : undefined}
        className={cn(
          "w-full flex items-center rounded-[var(--tt-radius)] border border-transparent transition-colors h-9",
          "text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)] hover:border-[var(--tt-border)] hover:tt-tint-1",
          collapsed ? "justify-center" : "justify-between gap-2 px-2",
          open && "tt-tint-1 text-[var(--tt-fg)]",
        )}
      >
        <span className="flex items-center gap-2 min-w-0">
          <span className="relative flex items-center" style={tone ? { color: tone } : undefined}>
            <Gauge size={collapsed ? 16 : 14} />
            {/* Collapsed, the rail has no room for a reading, so the state
                travels as a dot on the icon instead of disappearing. */}
            {collapsed && tone && (
              <span
                aria-hidden
                className="absolute -top-1 -right-1 h-2 w-2 rounded-full ring-2 ring-[var(--tt-panel)]"
                style={{ backgroundColor: tone }}
              />
            )}
          </span>
          {!collapsed && (
            <span className="text-[10px] uppercase tracking-[0.18em] truncate">Plan limits</span>
          )}
        </span>
        {!collapsed && reading && (
          <span className="tabular text-[11px] shrink-0" style={tone ? { color: tone } : undefined}>
            {reading}
          </span>
        )}
      </button>

      {!collapsed && worst && (
        <div className="mt-1 mx-2 h-1 rounded-full tt-tint-1 overflow-hidden" aria-hidden>
          <div
            className="h-full rounded-full transition-[width,background-color] duration-500"
            style={{ width: `${worst.pct}%`, backgroundColor: quotaColor(worst.pct) }}
          />
        </div>
      )}

      {open && <Panel collapsed={collapsed} providers={providers} unavailable={unavailable} />}
    </div>
  );
}

function Row({ window: w }: { window: QuotaWindow }) {
  const spent = w.pct >= 100;
  return (
    <div className="px-3.5 py-2.5">
      <div className="flex items-center justify-between gap-3">
        <span className="flex items-center gap-2 min-w-0">
          <AgentLogo agent={w.providerId} size={13} color />
          <span className="text-[12px] text-[var(--tt-fg)] truncate">{w.displayName}</span>
        </span>
        <span className="tabular text-[11px] whitespace-nowrap" style={{ color: quotaColor(w.pct) }}>
          {spent ? "Limit reached" : `${Math.round(w.pct)}% used`}
        </span>
      </div>
      <div className="mt-1.5 flex items-center gap-2">
        <div className="flex-1 h-1 rounded-full tt-tint-1 overflow-hidden">
          <div className="h-full rounded-full" style={{ width: `${w.pct}%`, backgroundColor: quotaColor(w.pct) }} />
        </div>
        <span className="text-[10px] text-[var(--tt-fg-faint)] whitespace-nowrap">{w.label}</span>
      </div>
    </div>
  );
}

function Panel({
  collapsed, providers, unavailable,
}: {
  collapsed: boolean;
  providers: [string, QuotaSnapshot][];
  unavailable: QuotaCapability[];
}) {
  const rows = providers
    .map(([id, snapshot]) => worstWindowFor(id, snapshot))
    .filter((w): w is QuotaWindow => w != null)
    .sort((a, b) => b.pct - a.pct);

  // Providers that report only balances (credits, spend) have no window to
  // rank, so they would vanish from a list built purely of meters.
  const balances = providers.filter(([id, snapshot]) =>
    !rows.some((r) => r.providerId === id)
    && Object.values(snapshot.resources).some((r) => quotaPercent(r) == null));

  return (
    <div
      role="dialog"
      aria-label="Plan limits"
      className={cn(
        "absolute z-[200] bottom-0 w-72 max-h-[70vh] flex flex-col",
        "rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] shadow-2xl",
        collapsed ? "left-[calc(100%+12px)]" : "left-[calc(100%+8px)]",
      )}
    >
      <div className="px-3.5 py-2.5 border-b border-[var(--tt-border)]">
        <span className="text-[12px] font-semibold text-[var(--tt-fg)]">Plan limits</span>
      </div>

      <div className="overflow-y-auto divide-y divide-[var(--tt-border)]">
        {rows.map((w) => <Row key={w.providerId} window={w} />)}
        {balances.map(([id, snapshot]) => (
          <div key={id} className="px-3.5 py-2.5 flex items-center justify-between gap-3">
            <span className="flex items-center gap-2 min-w-0">
              <AgentLogo agent={id} size={13} color />
              <span className="text-[12px] text-[var(--tt-fg)] truncate">{snapshot.displayName}</span>
            </span>
            <span className="text-[10px] text-[var(--tt-fg-faint)]">balance only</span>
          </div>
        ))}
        {rows.length === 0 && balances.length === 0 && (
          <div className="px-4 py-8 text-center text-[12px] text-[var(--tt-fg-dim)]">
            No agent is reporting a plan limit yet.
          </div>
        )}
      </div>

      {unavailable.length > 0 && (
        <Link
          href="/agents"
          className="px-3.5 py-2.5 border-t border-[var(--tt-border)] text-[11px] text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] transition-colors"
        >
          {unavailable.length} other {unavailable.length === 1 ? "agent has" : "agents have"} no live quota
        </Link>
      )}
    </div>
  );
}
