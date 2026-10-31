"use client";

import type { TraceSpan } from "@/lib/traceTree/types";
import ContentSection from "./ContentSection";

/** Mounted only on expansion; full payloads stay out of the scrolling hot path. */
export default function InlineEvidence({ span }: { span: TraceSpan }) {
  return <div className="mt-3 space-y-3 border-t border-[var(--tt-border)] pt-3" aria-label="Inline tool evidence">
    <RecordedField label="Input" value={span.content?.input} />
    <RecordedField label="Result" value={span.content?.output} error={span.error} />
  </div>;
}

function RecordedField({ label, value, error }: { label: string; value: unknown; error?: boolean }) {
  if (value === undefined) return <p className="text-xs text-[var(--tt-fg-muted)]">{label} unavailable in this trace.</p>;
  if (value === null || value === "") return <p className="text-xs text-[var(--tt-fg-muted)]">{label}: {value === null ? "null" : "empty string"}</p>;
  return <ContentSection label={label} value={value} plain error={error} />;
}
