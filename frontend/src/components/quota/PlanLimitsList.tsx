"use client";

/**
 * The plan-limits list, shared by the sidebar popover and the menu-bar tray.
 *
 * Extracted so the two surfaces cannot drift: a meter that means one thing in
 * the dashboard and another in the tray is worse than having only one of them.
 * This file owns presentation only — fetching, refreshing and the surrounding
 * chrome stay with each caller.
 */

import Link from "next/link";

import { AgentLogo } from "@/components/icons/AgentLogo";
import {
  quotaAmount, quotaColor, quotaPercent, quotaResourceLabel, resetText, worstWindowFor,
  type QuotaCapability, type QuotaResource, type QuotaSnapshot,
} from "@/lib/quotas";

export function Bar({ label, pct, note }: { label: string; pct: number; note?: string | null }) {
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
export function ProviderRows({ providerId, snapshot }: { providerId: string; snapshot: QuotaSnapshot }) {
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

/**
 * Every provider, closest to a ceiling first.
 *
 * The provider about to cut you off is the one worth reading. A provider with
 * only balances has no window to rank and sorts last rather than dropping out.
 */
export function PlanLimitsList({ providers }: { providers: [string, QuotaSnapshot][] }) {
  const ordered = [...providers].sort(
    ([a, sa], [b, sb]) => (worstWindowFor(b, sb)?.pct ?? -1) - (worstWindowFor(a, sa)?.pct ?? -1));

  if (ordered.length === 0) {
    return (
      <div className="px-4 py-8 text-center text-[12px] text-[var(--tt-fg-dim)]">
        No agent is reporting a plan limit yet.
      </div>
    );
  }
  return (
    <>
      {ordered.map(([id, snapshot]) => (
        <ProviderRows key={id} providerId={id} snapshot={snapshot} />
      ))}
    </>
  );
}

/**
 * The "N other agents have no live quota" footer.
 *
 * `href` is a prop because the tray cannot navigate in place: following a link
 * inside a popover would replace the panel with a full dashboard page in a
 * window sized for a menu.
 */
export function UnavailableFooter({
  unavailable, href, onNavigate,
}: {
  unavailable: QuotaCapability[];
  href?: string;
  onNavigate?: () => void;
}) {
  if (unavailable.length === 0) return null;
  const text = `${unavailable.length} other ${unavailable.length === 1 ? "agent has" : "agents have"} no live quota`;
  const className =
    "block px-3.5 py-2.5 border-t border-[var(--tt-border)] text-[11px] text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] transition-colors text-left w-full";

  if (onNavigate) {
    return <button type="button" onClick={onNavigate} className={className}>{text}</button>;
  }
  return <Link href={href ?? "/agents"} className={className}>{text}</Link>;
}
