"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Gauge, RefreshCw, Loader2, Clock } from "lucide-react";

import { cn } from "@/lib/cn";
import { AgentLogo } from "@/components/icons/AgentLogo";
import { trackEvent } from "@/lib/telemetry";
import {
  QUOTA_WARN_AT, quotaAmount, quotaColor, quotaPercent, quotaResourceLabel, resetText, worstWindowFor,
  type QuotaCapability, type QuotaResource, type QuotaSnapshot,
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
  const capabilities = data?.capabilities ?? {};
  // A throttled provider whose last reading is still on screen has not lost its
  // live quota, it just could not refresh this minute. Counting it in the
  // footer would contradict the row rendered directly above it. One that has
  // never fetched successfully has nothing to show, so it stays in the count.
  const unavailable = Object.entries(capabilities)
    .filter(([id, c]) => c.state !== "available" && !(c.state === "rateLimited" && data?.providers?.[id]))
    .map(([, c]) => c);
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

      {open && (
        <Panel
          collapsed={collapsed}
          providers={providers}
          capabilities={capabilities}
          unavailable={unavailable}
        />
      )}
    </div>
  );
}

function Bar({ label, pct, note }: { label: string; pct: number; note?: string | null }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-[11px]">
        <span className="text-[var(--tt-fg-muted)]">{label}</span>
        <span className="tabular whitespace-nowrap" style={{ color: quotaColor(pct) }}>
          {pct >= 100 ? "Limit reached" : `${Math.round(pct)}% used`}
        </span>
      </div>
      <div className="mt-1 h-1 rounded-full tt-tint-1 overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: quotaColor(pct) }} />
      </div>
      {note && <div className="mt-1 text-[10px] text-[var(--tt-fg-faint)]">{note}</div>}
    </div>
  );
}

/** One provider: every window it reports, plus any balance it carries. */
function ProviderRows({
  providerId, snapshot, capability,
}: {
  providerId: string;
  snapshot: QuotaSnapshot;
  capability?: QuotaCapability;
}) {
  const entries = Object.entries(snapshot.resources);
  const windows = entries
    .map(([key, resource]) => ({ key, resource, pct: quotaPercent(resource) }))
    .filter((e): e is { key: string; resource: QuotaResource; pct: number } => e.pct != null);
  const balances = entries.filter(([, resource]) => quotaPercent(resource) == null);

  return (
    <div className="px-3.5 py-3 space-y-2.5">
      <div className="flex items-center justify-between gap-3">
        <span className="flex items-center gap-2 min-w-0">
          <AgentLogo agent={providerId} size={13} color />
          <span className="text-[12px] font-medium text-[var(--tt-fg)] truncate">{snapshot.displayName}</span>
        </span>
        {snapshot.plan && (
          <span className="text-[10px] uppercase tracking-[0.14em] text-[var(--tt-fg-faint)] shrink-0">
            {snapshot.plan}
          </span>
        )}
      </div>

      {/* Said before the numbers, not after: a reading the provider refused to
          refresh is one the reader should discount while looking at it. */}
      {capability?.state === "rateLimited" && (
        <div className="flex items-start gap-1.5 text-[10px] leading-snug text-[var(--tt-warn-fg)]">
          <Clock size={11} className="mt-px shrink-0" aria-hidden />
          <span>{capability.detail ?? "The usage API is rate limiting requests. The last reading is still shown."}</span>
        </div>
      )}

      {windows.map(({ key, resource, pct }) => (
        <Bar key={key} label={quotaResourceLabel(key)} pct={pct} note={resetText(resource.resetsAt)} />
      ))}

      {balances.map(([key, resource]) => (
        <div key={key} className="flex items-baseline justify-between gap-3 text-[11px]">
          <span className="text-[var(--tt-fg-muted)]">{quotaResourceLabel(key)}</span>
          <span className="tabular text-[var(--tt-fg-dim)] whitespace-nowrap">
            {resource.available != null
              ? quotaAmount(resource.available, resource.unit)
              : resource.used != null
                ? `${quotaAmount(resource.used, resource.unit)} used`
                : "No data"}
          </span>
        </div>
      ))}

      {windows.length === 0 && balances.length === 0 && (
        <div className="text-[11px] text-[var(--tt-fg-dim)]">No quota reported.</div>
      )}
    </div>
  );
}

function Panel({
  collapsed, providers, capabilities, unavailable,
}: {
  collapsed: boolean;
  providers: [string, QuotaSnapshot][];
  capabilities: Record<string, QuotaCapability>;
  unavailable: QuotaCapability[];
}) {
  // Closest to a ceiling first: the provider about to cut you off is the one
  // worth reading. A provider with only balances has no window to rank and
  // sorts last rather than dropping out of the list.
  const ordered = [...providers].sort(
    ([a, sa], [b, sb]) => (worstWindowFor(b, sb)?.pct ?? -1) - (worstWindowFor(a, sa)?.pct ?? -1));

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
        {ordered.map(([id, snapshot]) => (
          <ProviderRows key={id} providerId={id} snapshot={snapshot} capability={capabilities[id]} />
        ))}
        {ordered.length === 0 && (
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
