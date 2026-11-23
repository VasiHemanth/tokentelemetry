"use client";

import { History, Plus, RotateCw } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui";
import { cn } from "@/lib/cn";
import type { RecallConversationSummary } from "@/lib/recall";

export function AskHistory({ items, activeId, disabled, loading, error, onSelect, onNew, onRetry }: {
  items: RecallConversationSummary[];
  activeId?: string;
  disabled: boolean;
  loading: boolean;
  error?: Error;
  onSelect: (id: string) => void;
  onNew: () => void;
  onRetry: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <aside aria-label="Ask history" className="min-w-0 rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] lg:sticky lg:top-4 lg:self-start">
      <div className="flex items-center justify-between gap-2 p-2.5">
        <h2 className="hidden items-center gap-1.5 pl-1 text-[12px] font-semibold text-[var(--tt-fg-muted)] lg:flex">
          <History size={14} /> Ask history
        </h2>
        <button type="button" aria-expanded={expanded} aria-controls="recall-ask-history"
          className="inline-flex items-center gap-1.5 px-1 text-[12px] font-semibold text-[var(--tt-fg-muted)] lg:hidden"
          onClick={() => setExpanded(!expanded)}>
          <History size={14} /> Ask history
        </button>
        <Button size="sm" onClick={() => { onNew(); setExpanded(false); }} disabled={disabled}>
          <Plus size={13} /> New chat
        </Button>
      </div>
      <div id="recall-ask-history" className={cn(
        "max-h-[min(55vh,34rem)] overflow-y-auto space-y-1 border-t border-[var(--tt-border)] p-2",
        expanded ? "block" : "hidden lg:block",
      )}>
        {error ? (
          <Button size="sm" variant="ghost" onClick={onRetry}><RotateCw size={12} /> Retry history</Button>
        ) : loading && !items.length ? (
          <p role="status" className="px-2 py-2 text-xs text-[var(--tt-fg-muted)]">Loading history…</p>
        ) : !items.length ? (
          <p className="px-2 py-2 text-xs text-[var(--tt-fg-muted)]">Your chats will appear here.</p>
        ) : items.map((item) => (
          <button key={item.id} type="button" title={item.title} disabled={disabled}
            aria-current={activeId === item.id ? "true" : undefined}
            onClick={() => { onSelect(item.id); setExpanded(false); }}
            className={cn(
              "block w-full rounded-[var(--tt-radius)] border px-2.5 py-2 text-left disabled:opacity-60",
              activeId === item.id
                ? "border-[var(--tt-border-strong)] bg-[var(--tt-sunken)]"
                : "border-transparent hover:bg-[var(--tt-sunken)]",
            )}>
            <span className="block truncate text-[12px] font-medium text-[var(--tt-fg)]">{item.title}</span>
            <span className="block truncate text-[11px] text-[var(--tt-fg-muted)]">{item.project_name || "All projects"}</span>
          </button>
        ))}
      </div>
    </aside>
  );
}
