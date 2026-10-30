"use client";

import { useMemo, useState } from "react";
import { ArrowDownToLine, Brain, ChevronLeft, ChevronRight, GitBranch, MessageSquare, Wrench } from "lucide-react";
import type { TraceSpan } from "@/lib/traceTree/types";
import { conversationGroups, conversationSignals } from "@/lib/traceTree/workspace";
import { formatContent } from "@/lib/traceTree/content";
import { fmtClock, fmtDur } from "@/lib/traceTree/timeScale";

const PAGE_SIZE = 12;
const button = "rounded-md border border-[var(--tt-border)] px-3 py-1.5 text-xs text-[var(--tt-fg-muted)] hover:bg-[var(--tt-raised)] disabled:opacity-40";

interface Props {
  roots: TraceSpan[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onInspectExecution: (id: string) => void;
  real: boolean;
  focusTurnId?: string | null;
}

export default function Conversation({ roots, selectedId, focusTurnId, onSelect, onInspectExecution, real }: Props) {
  const groups = useMemo(() => conversationGroups(roots), [roots]);
  const [paging, setPaging] = useState<{ page: number; selection: string | null }>({ page: 0, selection: null });
  const focusedGroup = groups.findIndex(g => g.prompt?.id === focusTurnId || g.notifications.some(n => n.id === focusTurnId));
  const last = Math.max(0, Math.ceil(groups.length / PAGE_SIZE) - 1);
  const current = Math.min(paging.selection === selectedId ? paging.page : Math.floor(Math.max(0, focusedGroup) / PAGE_SIZE), last);
  const start = current * PAGE_SIZE;
  return (
    <section aria-label="Session conversation" className="min-h-0 min-w-0 flex-1 overflow-y-auto overscroll-contain px-5 py-5 scrollbar-thin">
      <div className="mx-auto max-w-4xl space-y-7">
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-[var(--tt-fg-muted)]">
          <span>Requests, responses, and delegated work. Select an item to inspect its evidence.</span>
          <span>{groups.length} conversation groups</span>
        </div>
        {groups.slice(start, start + PAGE_SIZE).map((group, offset) => (
          <article key={(group.prompt ?? group.notifications[0]).id} className="border-b border-[var(--tt-border)] pb-6 [content-visibility:auto] [contain-intrinsic-size:auto_400px]">
            {group.prompt ? (
              <>
                <div className="mb-3 flex items-center justify-between gap-3 text-xs text-[var(--tt-fg-muted)]"><span className="inline-flex items-center gap-2"><MessageSquare size={14} />{group.prompt.title}</span>{real && <time>{fmtClock(group.prompt.start)}</time>}</div>
                <button type="button" onClick={() => onSelect(group.prompt!.id)} className={`w-full rounded-lg border p-4 text-left text-sm leading-7 text-[var(--tt-fg)] hover:border-[var(--tt-border-strong)] ${selectedId === group.prompt.id ? "border-[var(--tt-border-focus)] bg-[var(--tt-brand-glow)]" : "border-[var(--tt-border)] bg-[var(--tt-panel)]"}`} aria-pressed={selectedId === group.prompt.id}>
                  <Preview value={group.prompt.content?.input ?? group.prompt.label ?? group.prompt.title} cap={1200} />
                </button>
                <TurnContent turn={group.prompt} selectedId={selectedId} onSelect={onSelect} onInspectExecution={onInspectExecution} real={real} />
              </>
            ) : <h2 className="text-base font-medium text-[var(--tt-fg)]">Recorded activity before the first request</h2>}
            {group.notifications.length > 0 && (
              <details open={group.notifications.some(n => n.id === focusTurnId) || undefined} className="mt-4 rounded-lg border border-[var(--tt-border)] bg-[var(--tt-panel)] px-4 py-3 text-sm">
                <summary className="cursor-pointer text-[var(--tt-fg-muted)]">Agent reports & notifications · {group.notifications.length}</summary>
                <div className="mt-3 space-y-4">{group.notifications.map(turn => <div key={turn.id}><button type="button" onClick={() => onSelect(turn.id)} className="text-left text-xs text-[var(--tt-brand)] hover:underline">{turn.title}{real ? ` · ${fmtClock(turn.start)}` : ""}</button><TurnContent turn={turn} selectedId={selectedId} onSelect={onSelect} onInspectExecution={onInspectExecution} real={real} /></div>)}</div>
              </details>
            )}
            <div className="sr-only">Conversation group {start + offset + 1} of {groups.length}</div>
          </article>
        ))}
        {groups.length === 0 && <p className="text-sm text-[var(--tt-fg-muted)]">No conversation content recorded.</p>}
        {last > 0 && <div className="flex items-center justify-between gap-3"><button type="button" className={button} disabled={!current} onClick={() => setPaging({ page: current - 1, selection: selectedId })}><ChevronLeft size={14} className="inline" /> Previous</button><span className="text-xs text-[var(--tt-fg-muted)]" aria-live="polite">Page {current + 1} of {last + 1}</span><button type="button" className={button} disabled={current === last} onClick={() => setPaging({ page: current + 1, selection: selectedId })}>Next <ChevronRight size={14} className="inline" /></button></div>}
      </div>
    </section>
  );
}

function TurnContent({ turn, selectedId, onSelect, onInspectExecution, real }: Omit<Props, "roots"> & { turn: TraceSpan }) {
  const signals = useMemo(() => conversationSignals(turn), [turn]);
  const [paging, setPaging] = useState<{ offset: number; selection: string | null }>({ offset: 0, selection: null });
  const selectedIndex = signals.visible.findIndex(s => s.id === selectedId);
  const offset = paging.selection === selectedId ? paging.offset : Math.max(0, Math.floor(selectedIndex / 8) * 8);
  const visible = signals.visible.slice(offset, offset + 8);
  const selectedModel = signals.models.find(s => s.id === selectedId && !signals.visible.includes(s));
  return (
    <div className="mt-4 space-y-3">
      {selectedModel && <button type="button" onClick={() => onSelect(selectedModel.id)} className="w-full rounded-lg border border-[var(--tt-border-focus)] bg-[var(--tt-brand-glow)] p-3 text-left text-xs text-[var(--tt-brand)]">Selected model call · {selectedModel.title} · inspect recorded reasoning and calls</button>}
      {visible.map(span => {
        const isResponse = span.kind === "llm";
        return (
          <button type="button" key={span.id} data-conversation-span={span.id} aria-pressed={selectedId === span.id} onClick={() => onSelect(span.id)} className={`block w-full rounded-lg border px-4 py-3 text-left transition-colors ${selectedId === span.id ? "border-[var(--tt-border-focus)] bg-[var(--tt-brand-glow)]" : "border-[var(--tt-border)] bg-[var(--tt-panel)] hover:bg-[var(--tt-raised)]"}`}>
            <span className="flex items-center justify-between gap-3"><span className="flex min-w-0 items-center gap-2 text-sm font-medium text-[var(--tt-fg)]">{isResponse ? <MessageSquare size={14} className="shrink-0 text-[var(--tt-fg-muted)]" /> : span.kind === "agent" ? <GitBranch size={14} className="shrink-0 text-[var(--tt-brand)]" /> : <Wrench size={14} className="shrink-0 text-[var(--tt-fg-muted)]" />}<span className="truncate">{isResponse ? "Assistant response" : span.label || span.title}</span></span>{real && !isResponse && <span className="shrink-0 text-xs tabular-nums text-[var(--tt-fg-muted)]">{fmtDur(span.end - span.start)}</span>}</span>
            {isResponse ? <span className="mt-2 block whitespace-pre-wrap break-words text-sm leading-7 text-[var(--tt-fg-muted)]"><Preview value={span.content?.output} cap={1200} /></span> : <span className="mt-1.5 block text-xs text-[var(--tt-fg-muted)]">{span.title}{span.kind === "agent" ? ` · ${span.agent?.background ? "Background agent" : "Delegated agent"}` : " · Recorded call"}</span>}
            {span.content?.reasoning != null && <span className="mt-2 inline-flex items-center gap-1.5 text-xs text-[var(--tt-fg-muted)]"><Brain size={12} /> Recorded reasoning available in inspector</span>}
            {span.error && <span className="mt-2 block text-xs text-[var(--tt-danger-fg)]">Recorded error · inspect input and result</span>}
          </button>
        );
      })}
      {signals.visible.length > 8 && <div className="flex flex-wrap items-center gap-2"><button type="button" className={button} disabled={!offset} onClick={() => setPaging({ offset: Math.max(0, offset - 8), selection: selectedId })}>Earlier responses</button><span className="text-xs text-[var(--tt-fg-muted)]">{offset + 1}–{Math.min(offset + 8, signals.visible.length)} of {signals.visible.length}</span><button type="button" className={button} disabled={offset + 8 >= signals.visible.length} onClick={() => setPaging({ offset: offset + 8, selection: selectedId })}>Later responses</button></div>}
      {(signals.tools.length > 0 || signals.models.length > 0) && <div className="flex flex-wrap items-center gap-2"><span className="text-xs text-[var(--tt-fg-muted)]">{signals.modelCalls} model calls · {signals.tools.length} other tool calls</span><button type="button" className={button} onClick={() => onInspectExecution(turn.id)}><ArrowDownToLine size={12} className="mr-1 inline" /> Inspect execution</button></div>}
    </div>
  );
}

function Preview({ value, cap }: { value: unknown; cap: number }) {
  const text = useMemo(() => formatContent(value, cap), [value, cap]);
  return <>{text.text || "No readable text recorded."}{text.truncated && <span className="text-[var(--tt-brand)]"> … Select to read more</span>}</>;
}
