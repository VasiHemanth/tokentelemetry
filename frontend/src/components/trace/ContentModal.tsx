"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Check, Copy, X } from "lucide-react";
import { formatContent } from "@/lib/traceTree/content";
import ConversationMarkdown from "./ConversationMarkdown";

/** The larger reader formats the original value only while this modal is open. */
export default function ContentModal({ label, value, initialFormatted, onClose }: { label: string; value: unknown; initialFormatted: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const content = useMemo(() => formatContent(value, 1_000_000), [value]);
  const canFormat = content.kind === "text" && content.text.length <= 50_000;
  const [formatted, setFormatted] = useState(initialFormatted && canFormat);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (!dialog.open) dialog.showModal();
    return () => { if (dialog.open) dialog.close(); };
  }, []);
  return <dialog ref={ref} aria-labelledby={titleId} onClose={event => { if (event.target === event.currentTarget && !event.currentTarget.open) onClose(); }} onClick={event => { if (event.target === event.currentTarget) onClose(); }} className="fixed inset-0 m-auto h-[90dvh] max-h-[90dvh] w-[calc(100vw-2rem)] max-w-6xl overflow-hidden rounded-xl border border-[var(--tt-border-strong)] bg-[var(--tt-panel)] p-0 text-[var(--tt-fg)] shadow-xl backdrop:bg-black/60">
    <div className="flex h-full min-w-0 flex-col">
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-[var(--tt-border)] px-4 py-3 sm:px-6">
        <div className="min-w-0"><h2 id={titleId} className="truncate text-base font-semibold">{label} — expanded view</h2><p className="mt-0.5 text-xs text-[var(--tt-fg-muted)]">Recorded content</p></div>
        <button type="button" autoFocus aria-label={`Close expanded ${label}`} onClick={onClose} className="shrink-0 rounded-md p-2 text-[var(--tt-fg-muted)] hover:bg-[var(--tt-raised)] hover:text-[var(--tt-fg)]"><X size={18} /></button>
      </div>
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-[var(--tt-border)] px-4 py-2 sm:px-6">
        {canFormat ? <div role="group" aria-label={`${label} expanded display`} className="inline-flex rounded-md border border-[var(--tt-border)] bg-[var(--tt-canvas)] p-0.5">{[true, false].map(mode => <button key={String(mode)} type="button" aria-pressed={mode === formatted} onClick={() => setFormatted(mode)} className={`rounded px-3 py-1.5 text-xs ${mode === formatted ? "bg-[var(--tt-raised)] text-[var(--tt-fg)]" : "text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)]"}`}>{mode ? "Formatted" : "Raw"}</button>)}</div> : <span className="text-xs text-[var(--tt-fg-muted)]">{content.kind === "json" ? "JSON" : "Raw text"}</span>}
        <button type="button" aria-label={`Copy expanded ${label}`} onClick={async () => { try { await navigator.clipboard.writeText(content.text); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { setCopied(false); } }} className="inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-xs text-[var(--tt-fg-muted)] hover:bg-[var(--tt-raised)] hover:text-[var(--tt-fg)]">{copied ? <Check size={13} /> : <Copy size={13} />}{copied ? "Copied" : "Copy"}</button>
      </div>
      <div className="min-h-0 min-w-0 flex-1 overflow-auto overscroll-contain p-4 scrollbar-thin sm:p-6">
        <div className="mx-auto min-w-0 max-w-5xl">{formatted && canFormat ? <ConversationMarkdown text={content.text} /> : <pre className="whitespace-pre-wrap break-words font-mono text-sm leading-7">{content.text}</pre>}
          {content.truncated && <p className="mt-4 text-xs text-[var(--tt-fg-muted)]">Preview limited to the first {content.text.length.toLocaleString()} characters.</p>}
        </div>
      </div>
    </div>
  </dialog>;
}
