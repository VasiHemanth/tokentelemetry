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
  let placeholder: string | undefined;
  if (value === undefined) placeholder = "Unavailable in this trace.";
  else if (Array.isArray(value) && value.length === 0 || value && typeof value === "object" && !Array.isArray(value) && Object.keys(value).length === 0) placeholder = Array.isArray(value) ? "[]" : "{}";
  else if (value === null || value === "") placeholder = value === null ? "null" : '""';
  if (placeholder !== undefined) return <div data-content-label={label} className="min-w-0 space-y-2">
    <div className="flex h-8 items-center"><span className="text-xs font-medium" style={{ color: label === "Input" ? "var(--tt-brand)" : "var(--tt-cyan-fg)" }}>{label}</span></div>
    <div className="flex h-8 items-center text-xs text-[var(--tt-fg-muted)]">{value === undefined ? "No record" : "Empty value"}</div>
    <div data-content-body className="rounded-md border border-[var(--tt-border)] bg-[var(--tt-sunken)] p-3 text-xs text-[var(--tt-fg-muted)]">{placeholder}</div>
  </div>;
  return <ContentSection label={label} value={value} autoFormat accent={label === "Input" ? "input" : "output"} error={error} />;
}
