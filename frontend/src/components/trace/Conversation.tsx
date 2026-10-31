"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowDownToLine, MessageSquare } from "lucide-react";
import type { TraceSpan } from "@/lib/traceTree/types";
import { conversationLayout, conversationRowAt, conversationRows } from "@/lib/traceTree/conversation";
import ConversationEntry, { type ConversationEntryProps } from "./ConversationEntry";
import type { LoadState } from "./SpanTable";
import type { ColorOf } from "./shared";

interface Props {
  roots: TraceSpan[];
  selectedId: string | null;
  expanded: ReadonlySet<string>;
  loads: Record<string, LoadState>;
  onFollow: (id: string) => void;
  onInspect: (id: string) => void;
  onToggle: (id: string) => void;
  onRetry: (id: string) => void;
  real: boolean;
  colorOf: ColorOf;
}

/** Continuous reading with measured rows: format only nearby payloads. */
export default function Conversation({ roots, selectedId, expanded, loads, onFollow, onInspect, onToggle, onRetry, real, colorOf }: Props) {
  const rows = useMemo(() => conversationRows(roots, expanded), [roots, expanded]);
  const [evidenceCollapsed, setEvidenceCollapsed] = useState<Set<string>>(new Set());
  const measured = useRef(new Map<string, number>());
  const [heights, setHeights] = useState(new Map<string, number>());
  const layout = useMemo(() => conversationLayout(rows, heights), [rows, heights]);
  const boxRef = useRef<HTMLDivElement>(null);
  const [viewport, setViewport] = useState({ top: 0, height: 700 });
  const followed = useRef<string | null>(null);
  const handled = useRef<string | null>(null);
  const pendingReveal = useRef<string | null>(null);
  const userScrolling = useRef(false);
  const pinBottom = useRef(false);
  const layoutRef = useRef({ rows, layout });
  useEffect(() => { layoutRef.current = { rows, layout }; }, [rows, layout]);
  useEffect(() => {
    const box = boxRef.current;
    if (!box) return;
    const observer = new ResizeObserver(() => { if (box.clientHeight > 0) setViewport({ top: box.scrollTop, height: box.clientHeight }); });
    observer.observe(box);
    return () => observer.disconnect();
  }, []);
  const measure = useCallback((id: string, height: number) => {
    if (height <= 0 || measured.current.get(id) === height) return;
    const { rows, layout } = layoutRef.current;
    const i = rows.findIndex(row => row.span.id === id);
    const box = boxRef.current;
    const oldHeight = i >= 0 ? (layout.offsets[i + 1] ?? layout.total) - layout.offsets[i] : height;
    measured.current.set(id, height);
    // Preserve the visible position when earlier content changes height.
    if (box && i >= 0 && layout.offsets[i] + oldHeight <= box.scrollTop) box.scrollTop += height - oldHeight;
    setHeights(previous => new Map(previous).set(id, height));
  }, []);
  useEffect(() => {
    if (!selectedId || handled.current === selectedId) return;
    if (followed.current === selectedId) { handled.current = selectedId; return; }
    const i = rows.findIndex(row => row.span.id === selectedId);
    if (i < 0) return;
    handled.current = selectedId;
    if (selectedId !== rows.at(-1)?.span.id) pinBottom.current = false;
    userScrolling.current = false;
    pendingReveal.current = pinBottom.current ? null : selectedId;
    boxRef.current?.scrollTo({ top: layout.offsets[i], behavior: "instant" });
  }, [selectedId, rows, layout]);
  useEffect(() => {
    const id = pendingReveal.current;
    if (!id) return;
    const i = rows.findIndex(row => row.span.id === id);
    if (i < 0) return;
    const frame = requestAnimationFrame(() => {
      const box = boxRef.current;
      if (box) {
        box.scrollTo({ top: layout.offsets[i], behavior: "instant" });
        setViewport(previous => previous.top === box.scrollTop && previous.height === box.clientHeight ? previous : { top: box.scrollTop, height: box.clientHeight });
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [rows, layout, heights, viewport]);
  useEffect(() => {
    if (!pinBottom.current) return;
    const frame = requestAnimationFrame(() => {
      const box = boxRef.current;
      if (box) {
        box.scrollTop = box.scrollHeight;
        setViewport(previous => previous.top === box.scrollTop && previous.height === box.clientHeight ? previous : { top: box.scrollTop, height: box.clientHeight });
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [layout, viewport]);
  const first = Math.max(0, conversationRowAt(layout.offsets, viewport.top) - 3);
  const last = Math.min(rows.length, conversationRowAt(layout.offsets, viewport.top + viewport.height) + 5);
  const latest = () => {
    const row = rows.at(-1);
    if (!row) return;
    pinBottom.current = true;
    pendingReveal.current = null;
    followed.current = null;
    onFollow(row.span.id);
    userScrolling.current = false;
    boxRef.current?.scrollTo({ top: layout.total, behavior: "instant" });
  };
  const beginScroll = () => {
    userScrolling.current = true;
    pinBottom.current = false;
    pendingReveal.current = null;
  };
  const toggleEvidence = (id: string) => {
    pendingReveal.current = null;
    followed.current = id;
    onFollow(id);
    setEvidenceCollapsed(previous => { const next = new Set(previous); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  };
  return (
    <section className="flex min-h-0 min-w-0 flex-1 flex-col" aria-label="Session conversation">
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-[var(--tt-border)] px-4 py-3">
        <div className="flex min-w-0 items-center gap-3"><span className="hidden size-8 shrink-0 items-center justify-center rounded-lg border border-[var(--tt-border)] bg-[var(--tt-canvas)] text-[var(--tt-fg-muted)] sm:flex"><MessageSquare size={15} /></span><div><h2 className="text-sm font-semibold text-[var(--tt-fg)]">Conversation</h2><p className="mt-0.5 text-xs text-[var(--tt-fg-muted)]">Requests, responses & recorded activity</p></div></div>
        <button type="button" onClick={latest} className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-[var(--tt-border)] px-2.5 py-1.5 text-xs text-[var(--tt-fg-muted)] hover:bg-[var(--tt-raised)]"><ArrowDownToLine size={13} /> Latest</button>
      </div>
      <div ref={boxRef} tabIndex={0} aria-label="Continuous conversation" className="min-h-0 flex-1 overflow-y-auto overscroll-contain outline-none focus-visible:ring-1 focus-visible:ring-[var(--tt-border-focus)] scrollbar-thin [overflow-anchor:none]"
        onWheel={beginScroll} onTouchMove={beginScroll} onPointerDown={beginScroll} onKeyDown={e => { if (["ArrowDown", "ArrowUp", "PageDown", "PageUp", "Home", "End", " "].includes(e.key)) beginScroll(); }}
        onScroll={e => {
          const box = e.currentTarget;
          setViewport({ top: box.scrollTop, height: box.clientHeight });
          if (!userScrolling.current) return;
          const row = rows[conversationRowAt(layout.offsets, box.scrollTop + 32)];
          if (row && row.span.id !== followed.current) { followed.current = row.span.id; onFollow(row.span.id); }
        }}>
        <div className="relative mx-auto max-w-4xl" style={{ height: layout.total }}>
          {rows.slice(first, last).map((row, offset) => <MeasuredEntry key={row.span.id} top={layout.offsets[first + offset]} onMeasure={measure} span={row.span} depth={row.depth} agentColor={row.span.kind === "agent" ? colorOf(row.span.agent?.agentType) : undefined} selected={selectedId === row.span.id} real={real} evidenceOpen={!evidenceCollapsed.has(row.span.id)} onToggleEvidence={toggleEvidence} open={expanded.has(row.span.id)} load={loads[row.span.id]} onInspect={onInspect} onToggle={onToggle} onRetry={onRetry} />)}
        </div>
        {!rows.length && <p className="p-6 text-sm text-[var(--tt-fg-muted)]">No conversation content recorded.</p>}
      </div>
    </section>
  );
}

function MeasuredEntry({ top, onMeasure, ...entry }: ConversationEntryProps & { top: number; onMeasure: (id: string, height: number) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const observer = new ResizeObserver(entries => onMeasure(entry.span.id, Math.ceil(entries[0].borderBoxSize[0].blockSize)));
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [entry.span.id, onMeasure]);
  return <div ref={ref} data-conversation-span={entry.span.id} className="absolute left-0 w-full px-3 pb-4 pt-1 sm:px-5" style={{ top }}><ConversationEntry {...entry} /></div>;
}
