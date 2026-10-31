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
  const summary = FIELDS.map(({ key, label }) => `${label}: ${tokens[key].toLocaleString()} tokens, ${distribution ? formatTokenShare(distribution.shares[key]) : "share unavailable"}`).join("; ");
  return <section aria-label="Recorded token usage" className="space-y-2">
    <h3 className="text-sm font-medium text-[var(--tt-fg)]">Recorded token usage</h3>
    {distribution && <div className="rounded-lg border border-[var(--tt-border)] bg-[var(--tt-canvas)] p-3">
      <div className="mb-2 flex items-center justify-between gap-2 text-xs text-[var(--tt-fg-muted)]"><span>Token usage mix</span><span className="font-mono tabular-nums">{distribution.total.toLocaleString()} total</span></div>
      <div role="img" aria-label={`Token usage mix. ${summary}`} className="flex h-4 w-full overflow-hidden rounded-full bg-[var(--tt-raised)]">
        {FIELDS.map(({ key, label, color }) => tokens[key] > 0 && <span key={key} data-token-segment={key} title={`${label}: ${tokens[key].toLocaleString()} tokens (${formatTokenShare(distribution.shares[key])})`} className="h-full shrink-0" style={{ width: `${distribution.shares[key]}%`, background: color }} />)}
      </div>
      {distribution.total === 0 && <p className="mt-2 text-xs text-[var(--tt-fg-muted)]">All recorded counts are zero.</p>}
    </div>}
    <dl className="grid grid-cols-2 gap-2">
      {FIELDS.map(({ key, label, note, color, background }) => <div key={key} data-token-key={key} style={{ borderTopColor: color }} className="min-w-0 rounded-lg border border-t-2 border-[var(--tt-border)] bg-[var(--tt-canvas)] p-3">
        <dt className="flex items-center gap-2 text-xs font-medium" style={{ color }}><span aria-hidden="true" className="flex size-5 shrink-0 items-center justify-center rounded" style={{ background }}><span className="size-1.5 rounded-full" style={{ background: color }} /></span>{label}</dt>
        <dd className="mt-1 font-mono text-lg font-medium tabular-nums text-[var(--tt-fg)]">{tokens[key].toLocaleString()}</dd>
        <p className="mt-1 text-[11px] leading-5 text-[var(--tt-fg-muted)]">{note}{distribution && <span className="ml-1.5 font-mono tabular-nums">· {formatTokenShare(distribution.shares[key])}</span>}</p>
      </div>)}
    </dl>
  </section>;
}
