"use client";

import { useId, useMemo, useState } from "react";
import { Check, Copy } from "lucide-react";
import { formatContent } from "@/lib/traceTree/content";
import { looksLikeMarkdown } from "@/lib/traceTree/markdown";
import ConversationMarkdown from "./ConversationMarkdown";

const FULL_CAP = 1_000_000;
const MARKDOWN_MAX = 50_000;

interface Props {
  label: string;
  value: unknown;
  error?: boolean;
  /** Keep recorded reasoning behind an explicit disclosure. */
  collapseLong?: boolean;
  /** Force a literal view, for example for raw API records. */
  plain?: boolean;
  /** Detect Markdown in mixed tool text; callers can still choose the display. */
  autoFormat?: boolean;
  accent?: "input" | "output";
}

/** One bounded content block. Formatting runs only while the block is mounted. */
export default function ContentSection({ label, value, error, collapseLong, plain, autoFormat, accent }: Props) {
  const [showAll, setShowAll] = useState(false);
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [display, setDisplay] = useState<"auto" | "formatted" | "raw">("auto");
  const contentId = useId();
  const f = useMemo(() => formatContent(value, showAll ? FULL_CAP : undefined), [value, showAll]);
  if (f.kind === "empty") return label === "Reasoning" ? <p className="text-xs text-[var(--tt-fg-muted)]">No readable reasoning in this record.</p> : null;

  const canFormat = f.kind === "text" && !plain && f.text.length <= MARKDOWN_MAX;
  const formatted = canFormat && (display === "formatted" || (display === "auto" && (!autoFormat || looksLikeMarkdown(f.text))));
  const collapsed = !!collapseLong && !open;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(f.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      // clipboard unavailable (insecure context or denied)
    }
  };
  const accentColor = error ? "var(--tt-danger-fg)" : accent === "input" ? "var(--tt-brand)" : accent === "output" ? "var(--tt-cyan-fg)" : undefined;
  const tone = error ? "border-[var(--tt-danger-bd)] bg-[var(--tt-danger-bg)]" : "border-[var(--tt-border)] bg-[var(--tt-sunken)]";
  const btn = "text-xs font-medium text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)]";

  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
        <span style={{ color: accentColor }} className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--tt-fg-muted)]">{accent && <span aria-hidden="true" className="size-1.5 rounded-full" style={{ background: accentColor }} />}{label}</span>
        <div className="flex flex-wrap items-center gap-3">
          {canFormat && !collapsed && <div role="group" aria-label={`${label} display`} className="inline-flex rounded-md border border-[var(--tt-border)] bg-[var(--tt-canvas)] p-0.5">
            {(["formatted", "raw"] as const).map(mode => <button key={mode} type="button" aria-pressed={mode === "formatted" ? formatted : !formatted} onClick={() => setDisplay(mode)} className={`rounded px-2 py-1 text-xs ${((mode === "formatted") === formatted) ? "bg-[var(--tt-raised)] text-[var(--tt-fg)]" : "text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)]"}`}>{mode === "formatted" ? "Formatted" : "Raw"}</button>)}
          </div>}
          {collapseLong && (
            <button type="button" className={btn} aria-expanded={!collapsed} aria-controls={contentId} onClick={() => setOpen((v) => !v)}>
              {open ? "Collapse" : "Expand"}
            </button>
          )}
          <button type="button" className={`${btn} inline-flex items-center gap-1`} onClick={copy} aria-label={`Copy ${label}`}>
            {copied ? <Check size={10} /> : <Copy size={10} />}
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      </div>
      <div id={contentId}>{collapsed ? <p className="rounded-md border border-[var(--tt-border)] bg-[var(--tt-sunken)] px-3 py-2 text-xs text-[var(--tt-fg-muted)]">Recorded text available · expand to read</p> : <div style={accent ? { borderLeftColor: accentColor, borderLeftWidth: 2 } : undefined} className={`max-h-96 overflow-auto rounded-md border px-3 py-3 scrollbar-thin ${tone}`}>
        {formatted ? (
          <ConversationMarkdown text={f.text} compact />
        ) : (
          <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-6 text-[var(--tt-fg)]">{f.text}</pre>
        )}
      </div>}</div>
      {f.truncated && (
        <div className="flex items-center gap-2 text-[11px] text-[var(--tt-fg-muted)]">
          <span>{showAll ? `Showing the first ${f.text.length.toLocaleString()} characters` : `Showing the first ${f.text.length.toLocaleString()} of ${f.fullLength.toLocaleString()}${f.kind === "json" ? "+" : ""} characters`}</span>
          {!showAll && (
            <button type="button" className={btn} onClick={() => setShowAll(true)}>
              Show more
            </button>
          )}
        </div>
      )}
    </div>
  );
}
