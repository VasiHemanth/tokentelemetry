import type { SpanTokens } from "@/lib/traceTree/types";

const FIELDS: Array<{ key: keyof SpanTokens; label: string; note: string; color: string; background: string }> = [
  { key: "input", label: "Uncached input", note: "New input tokens", color: "var(--tt-brand)", background: "var(--tt-brand-glow)" },
  { key: "cacheRead", label: "Cache read", note: "Reused context", color: "var(--tt-violet-fg)", background: "var(--tt-violet-bg)" },
  { key: "cacheWrite", label: "Cache write", note: "New cached context", color: "var(--tt-warn-fg)", background: "var(--tt-warn-bg)" },
  { key: "output", label: "Output", note: "Generated tokens", color: "var(--tt-cyan-fg)", background: "var(--tt-cyan-bg)" },
];

/** Independent labelled values keep small categories visible beside large caches. */
export default function TokenUsage({ tokens }: { tokens: SpanTokens }) {
  return <section aria-label="Recorded token usage" className="space-y-2">
    <h3 className="text-sm font-medium text-[var(--tt-fg)]">Recorded token usage</h3>
    <dl className="grid grid-cols-2 gap-2">
      {FIELDS.map(({ key, label, note, color, background }) => <div key={key} data-token-key={key} style={{ borderTopColor: color }} className="min-w-0 rounded-lg border border-t-2 border-[var(--tt-border)] bg-[var(--tt-canvas)] p-3">
        <dt className="flex items-center gap-2 text-xs font-medium" style={{ color }}><span aria-hidden="true" className="flex size-5 shrink-0 items-center justify-center rounded" style={{ background }}><span className="size-1.5 rounded-full" style={{ background: color }} /></span>{label}</dt>
        <dd className="mt-1 font-mono text-lg font-medium tabular-nums text-[var(--tt-fg)]">{tokens[key].toLocaleString()}</dd>
        <p className="mt-1 text-[11px] leading-5 text-[var(--tt-fg-muted)]">{note}</p>
      </div>)}
    </dl>
  </section>;
}
