"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { tokenDistribution, formatTokenShare } from "@/lib/traceTree/tokenDistribution";
import type { SpanTokens } from "@/lib/traceTree/types";

const FIELDS: Array<{ key: keyof SpanTokens; label: string; note: string; color: string; background: string }> = [
  { key: "input", label: "Uncached input", note: "New input tokens", color: "var(--tt-brand)", background: "var(--tt-brand-glow)" },
  { key: "cacheRead", label: "Cache read", note: "Reused context", color: "var(--tt-violet-fg)", background: "var(--tt-violet-bg)" },
  { key: "cacheWrite", label: "Cache write", note: "New cached context", color: "var(--tt-warn-fg)", background: "var(--tt-warn-bg)" },
  { key: "output", label: "Output", note: "Generated tokens", color: "var(--tt-cyan-fg)", background: "var(--tt-cyan-bg)" },
];

/** Exact proportions in the bar; labelled values keep tiny categories readable. */
export default function TokenUsage({ tokens }: { tokens: SpanTokens }) {
  const distribution = tokenDistribution(tokens);
  const tooltipId = useId();
  const tooltipRef = useRef<HTMLDivElement>(null);
  const hideTimer = useRef<number | null>(null);
  const [hover, setHover] = useState<{ key: keyof SpanTokens; left: number; top: number } | null>(null);
  const cancelHide = useCallback(() => { if (hideTimer.current !== null) window.clearTimeout(hideTimer.current); }, []);
  const dismiss = useCallback(() => { cancelHide(); setHover(null); }, [cancelHide]);
  const show = (key: keyof SpanTokens, element: HTMLElement) => {
    cancelHide();
    const rect = element.getBoundingClientRect();
    setHover({ key, left: Math.max(8, Math.min(window.innerWidth - 248, rect.left + rect.width / 2 - 120)), top: rect.top >= 176 ? rect.top - 168 : Math.max(8, Math.min(window.innerHeight - 168, rect.bottom + 8)) });
  };
  const scheduleHide = () => { cancelHide(); hideTimer.current = window.setTimeout(() => setHover(null), 120); };
  useEffect(() => {
    const tooltip = tooltipRef.current;
    if (!tooltip) return;
    if (hover && !tooltip.matches(":popover-open")) tooltip.showPopover();
    else if (!hover && tooltip.matches(":popover-open")) tooltip.hidePopover();
  }, [hover]);
  useEffect(() => {
    if (!hover) return;
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); dismiss(); } };
    window.addEventListener("keydown", escape, true);
    window.addEventListener("scroll", dismiss, true);
    window.addEventListener("resize", dismiss);
    return () => { window.removeEventListener("keydown", escape, true); window.removeEventListener("scroll", dismiss, true); window.removeEventListener("resize", dismiss); };
  }, [hover, dismiss]);
  useEffect(() => () => { if (hideTimer.current !== null) window.clearTimeout(hideTimer.current); }, []);
  const active = FIELDS.find(field => field.key === hover?.key);
  const summary = FIELDS.map(({ key, label }) => `${label}: ${tokens[key].toLocaleString()} tokens, ${distribution ? formatTokenShare(distribution.shares[key]) : "share unavailable"}`).join("; ");
  return <section aria-label="Recorded token usage" className="space-y-2">
    <h3 className="text-sm font-medium text-[var(--tt-fg)]">Recorded token usage</h3>
    {distribution && <div className="rounded-lg border border-[var(--tt-border)] bg-[var(--tt-canvas)] p-3">
      <div className="mb-2 flex items-center justify-between gap-2 text-xs text-[var(--tt-fg-muted)]"><span>Token usage mix</span><span className="font-mono tabular-nums">{distribution.total.toLocaleString()} total</span></div>
      <div role="group" aria-label={`Token usage mix. ${summary}`} className="flex h-4 w-full overflow-hidden rounded-full bg-[var(--tt-raised)]">
        {FIELDS.map(({ key, label, color }) => tokens[key] > 0 && <button type="button" key={key} data-token-segment={key} aria-label={`${label}: ${tokens[key].toLocaleString()} tokens, ${formatTokenShare(distribution.shares[key])}`} aria-describedby={hover?.key === key ? tooltipId : undefined} onPointerEnter={event => show(key, event.currentTarget)} onPointerLeave={scheduleHide} onFocus={event => show(key, event.currentTarget)} onBlur={scheduleHide} className="h-full shrink-0 border-0 p-0 outline-none hover:brightness-125 focus-visible:brightness-125 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--tt-fg)]" style={{ width: `${distribution.shares[key]}%`, background: color }} />)}
      </div>
      {distribution.total === 0 && <p className="mt-2 text-xs text-[var(--tt-fg-muted)]">All recorded counts are zero.</p>}
    </div>}
    <dl className="grid grid-cols-2 gap-2">
      {FIELDS.map(({ key, label, note, color, background }) => <div key={key} role="group" aria-label={`${label}: ${tokens[key].toLocaleString()} tokens`} tabIndex={0} aria-describedby={hover?.key === key ? tooltipId : undefined} onPointerEnter={event => show(key, event.currentTarget)} onPointerLeave={scheduleHide} onFocus={event => show(key, event.currentTarget)} onBlur={scheduleHide} data-token-key={key} style={{ borderTopColor: color }} className="min-w-0 rounded-lg border border-t-2 border-[var(--tt-border)] bg-[var(--tt-canvas)] p-3 outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--tt-border-focus)]">
        <dt className="flex items-center gap-2 text-xs font-medium" style={{ color }}><span aria-hidden="true" className="flex size-5 shrink-0 items-center justify-center rounded" style={{ background }}><span className="size-1.5 rounded-full" style={{ background: color }} /></span>{label}</dt>
        <dd className="mt-1 font-mono text-lg font-medium tabular-nums text-[var(--tt-fg)]">{tokens[key].toLocaleString()}</dd>
        <p className="mt-1 text-[11px] leading-5 text-[var(--tt-fg-muted)]">{note}{distribution && <span className="ml-1.5 font-mono tabular-nums">· {formatTokenShare(distribution.shares[key])}</span>}</p>
      </div>)}
    </dl>
    <div ref={tooltipRef} id={tooltipId} role="tooltip" popover="manual" onPointerEnter={cancelHide} onPointerLeave={scheduleHide} className="fixed z-50 m-0 h-40 w-60 rounded-xl border p-4 text-[var(--tt-fg)] shadow-xl" style={{ inset: "auto", left: hover?.left ?? 0, top: hover?.top ?? 0, borderColor: active?.color, background: active ? `color-mix(in srgb, ${active.color} 18%, var(--tt-panel))` : "var(--tt-panel)" }}>
      {active && <><div className="flex items-center gap-2 text-xs font-semibold" style={{ color: active.color }}><span aria-hidden="true" className="size-2 rounded-full" style={{ background: active.color }} />{active.label}</div><div className="mt-2 font-mono text-2xl font-semibold tabular-nums">{tokens[active.key].toLocaleString()} <span className="font-sans text-xs font-normal text-[var(--tt-fg-muted)]">tokens</span></div><p className="mt-1 text-xs text-[var(--tt-fg-muted)]">{active.note}</p><div className="mt-3 flex items-center justify-between border-t border-[var(--tt-border-strong)] pt-2 text-xs"><span className="text-[var(--tt-fg-muted)]">Share of total</span><span className="font-mono font-medium" style={{ color: active.color }}>{distribution ? formatTokenShare(distribution.shares[active.key]) : "Unavailable"}</span></div></>}
    </div>
  </section>;
}
