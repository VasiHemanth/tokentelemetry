"use client";

import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy } from "lucide-react";
import { formatContent } from "@/lib/traceTree/content";
import { SECTION_LABEL } from "./shared";

const FULL_CAP = 1_000_000;
const MARKDOWN_MAX = 50_000;
const COLLAPSE_AT = 600;

interface Props {
  label: string;
  value: unknown;
  error?: boolean;
  /** Start collapsed when the text is long (used for reasoning). */
  collapseLong?: boolean;
  /** Tool input and output are program text, so they render verbatim instead of as markdown. */
  plain?: boolean;
}

/** One labelled content block. Formatting runs only while it is mounted, i.e. for the selected span. */
export default function ContentSection({ label, value, error, collapseLong, plain }: Props) {
  const [showAll, setShowAll] = useState(false);
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const f = useMemo(() => formatContent(value, showAll ? FULL_CAP : undefined), [value, showAll]);
  if (f.kind === "empty") return null;

  const collapsed = !!collapseLong && f.text.length > COLLAPSE_AT && !open;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(f.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      // clipboard unavailable (insecure context or denied)
    }
  };
  const tone = error ? "border-[var(--tt-danger-bd)] bg-[var(--tt-danger-bg)]" : "border-[var(--tt-border)] bg-[var(--tt-sunken)]";
  const btn = "text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)]";

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between pt-1">
        <span className={SECTION_LABEL}>{label}</span>
        <div className="flex items-center gap-3">
          {collapseLong && f.text.length > COLLAPSE_AT && (
            <button type="button" className={btn} onClick={() => setOpen((v) => !v)}>
              {open ? "Collapse" : "Expand"}
            </button>
          )}
          <button type="button" className={`${btn} inline-flex items-center gap-1`} onClick={copy} aria-label={`Copy ${label}`}>
            {copied ? <Check size={10} /> : <Copy size={10} />}
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      </div>
      <div className={`rounded-md border px-2.5 py-2 ${tone} ${collapsed ? "max-h-16 overflow-hidden" : "max-h-80 overflow-auto scrollbar-thin"}`}>
        {f.kind === "text" && !plain && f.text.length <= MARKDOWN_MAX ? (
          <div className={`prose prose-sm max-w-none break-words text-[12px] leading-relaxed text-[var(--tt-fg)] [&_pre]:overflow-x-auto [&_pre]:text-[11px] ${error ? "text-[var(--tt-danger-fg)]" : ""}`}>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{ img: ({ alt }) => <span>{`[image${alt ? `: ${alt}` : ""}]`}</span> }}
            >
              {f.text}
            </ReactMarkdown>
          </div>
        ) : (
          <pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-[var(--tt-fg)]">{f.text}</pre>
        )}
      </div>
      {f.truncated && (
        <div className="flex items-center gap-2 text-[11px] text-[var(--tt-fg-muted)]">
          <span>{showAll ? `Showing the first ${f.text.length.toLocaleString()} characters` : `Showing the first ${f.text.length.toLocaleString()} of ${f.fullLength.toLocaleString()}${f.kind === "json" ? "+" : ""} characters`}</span>
          {!showAll && (
            <button type="button" className={btn} onClick={() => setShowAll(true)}>
              Show all
            </button>
          )}
        </div>
      )}
    </div>
  );
}
