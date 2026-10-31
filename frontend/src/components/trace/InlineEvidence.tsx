"use client";

import type { TraceSpan } from "@/lib/traceTree/types";
import ContentSection from "./ContentSection";

/** Mounted only in nearby conversation entries; full payloads stay out of the scrolling hot path. */
export default function InlineEvidence({ span }: { span: TraceSpan }) {
  return <div className="@container mt-3 border-t border-[var(--tt-border)] pt-3" aria-label="Inline tool evidence">
    <div className="grid min-w-0 grid-cols-1 gap-4 @min-[720px]:grid-cols-2 [&_pre]:text-xs [&_pre]:leading-6"><RecordedField label="Input" value={span.content?.input} />
    <RecordedField label="Result" value={span.content?.output} error={span.error} /></div>
  </div>;
}

function RecordedField({ label, value, error }: { label: string; value: unknown; error?: boolean }) {
  if (value === undefined) return <p className="text-xs text-[var(--tt-fg-muted)]">{label} unavailable in this trace.</p>;
  if (Array.isArray(value) && value.length === 0 || value && typeof value === "object" && !Array.isArray(value) && Object.keys(value).length === 0) return <p className="text-xs text-[var(--tt-fg-muted)]">{label}: <code className="font-mono text-[var(--tt-fg)]">{Array.isArray(value) ? "[]" : "{}"}</code></p>;
  if (value === null || value === "") return <p className="text-xs text-[var(--tt-fg-muted)]">{label}: {value === null ? "null" : "empty string"}</p>;
  return <ContentSection label={label} value={value} autoFormat accent={label === "Input" ? "input" : "output"} error={error} />;
}
