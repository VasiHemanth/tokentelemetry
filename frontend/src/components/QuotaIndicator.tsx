"use client";

import { useEffect, useRef, useState } from "react";
import { Gauge, RefreshCw, Loader2 } from "lucide-react";

import { cn } from "@/lib/cn";
import { trackEvent } from "@/lib/telemetry";
import {
  QUOTA_WARN_AT, quotaColor,
  type QuotaCapability, type QuotaSnapshot,
} from "@/lib/quotas";
import { useQuotas } from "./QuotaProvider";
import { PlanLimitsList, UnavailableFooter } from "@/components/quota/PlanLimitsList";

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
  const [hovering, setHovering] = useState(false);
  // Clicking pins the panel so it survives the pointer leaving — needed to
  // scroll it, follow its link, or just read it without holding the mouse
  // still. Hover alone remains the quick look.
  const [pinned, setPinned] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const open = pinned || hovering;

  useEffect(() => {
    if (!pinned) return;
    const close = () => { setPinned(false); setHovering(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    const onClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) close();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [pinned]);

  const providers = Object.entries(data?.providers ?? {});
  const unavailable = Object.values(data?.capabilities ?? {}).filter((c) => c.state !== "available");
  if (providers.length === 0 && unavailable.length === 0) return null;

  const tone = worst && worst.pct >= QUOTA_WARN_AT ? quotaColor(worst.pct) : undefined;
  const reading = worst ? `${Math.round(worst.pct)}%` : null;

  return (
    <div
      ref={rootRef}
      className="relative"
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => setHovering(false)}
    >
      <button
        onClick={() => {
          const next = !pinned;
          setPinned(next);
          trackEvent("planlimits.toggled", { state: next ? "opened" : "closed" });
        }}
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
          {/* The icon and label keep the nav's own colour. A whole sidebar row
              turning red reads as "this control is broken" rather than "your
              week is nearly spent", so the state is carried by the reading and
              the bar, which are the things actually measuring something. */}
          <span className="relative flex items-center">
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
          <span className="tabular text-[11px] shrink-0 text-[var(--tt-fg-muted)]">{reading}</span>
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

function Panel({
  collapsed, providers, unavailable,
}: {
  collapsed: boolean;
  providers: [string, QuotaSnapshot][];
  unavailable: QuotaCapability[];
}) {
  const [refreshing, setRefreshing] = useState(false);
  const { refresh } = useQuotas();

  const doRefresh = async () => {
    setRefreshing(true);
    try {
      await refresh();
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-label="Plan limits"
      className={cn(
        "absolute z-[200] bottom-0 w-80 max-h-[75vh] flex flex-col",
        "rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] shadow-2xl",
        collapsed ? "left-[calc(100%+12px)]" : "left-[calc(100%+8px)]",
      )}
    >
      <div className="flex items-center justify-between gap-2 px-3.5 py-2.5 border-b border-[var(--tt-border)]">
        <span className="text-[12px] font-semibold text-[var(--tt-fg)]">Plan limits</span>
        <button
          type="button"
          onClick={doRefresh}
          disabled={refreshing}
          aria-label="Refresh plan limits"
          title="Refresh plan limits"
          className="inline-flex h-6 w-6 items-center justify-center rounded-md text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] hover:bg-[var(--tt-sunken)] disabled:opacity-50 transition-colors"
        >
          {refreshing ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
        </button>
      </div>

      <div className="overflow-y-auto divide-y divide-[var(--tt-border)]">
        <PlanLimitsList providers={providers} />
      </div>

      <UnavailableFooter unavailable={unavailable} />

    </div>
  );
}
