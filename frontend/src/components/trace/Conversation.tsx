"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowDownToLine, Brain, ChevronRight, FileSearch, GitBranch, MessageSquare, Wrench } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { TraceSpan } from "@/lib/traceTree/types";
import { conversationLayout, conversationRowAt, conversationRows } from "@/lib/traceTree/conversation";
import { formatContent } from "@/lib/traceTree/content";
import { fmtClock, fmtDur } from "@/lib/traceTree/timeScale";
import InlineEvidence from "./InlineEvidence";
import type { LoadState } from "./SpanTable";

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
}

/** Continuous reading with measured rows: format only nearby payloads. */
export default function Conversation({ roots, selectedId, expanded, loads, onFollow, onInspect, onToggle, onRetry, real }: Props) {
  const rows = useMemo(() => conversationRows(roots, expanded), [roots, expanded]);
  const [evidenceExpanded, setEvidenceExpanded] = useState<Set<string>>(new Set());
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
    setEvidenceExpanded(previous => { const next = new Set(previous); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  };
  return (
    <section className="flex min-h-0 min-w-0 flex-1 flex-col" aria-label="Session conversation">
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-[var(--tt-border)] px-4 py-3">
        <div><h2 className="text-sm font-medium text-[var(--tt-fg)]">Conversation</h2><p className="mt-0.5 text-xs text-[var(--tt-fg-muted)]">Follow the session · open any entry for evidence</p></div>
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
          {rows.slice(first, last).map((row, offset) => <MeasuredEntry key={row.span.id} top={layout.offsets[first + offset]} onMeasure={measure} span={row.span} depth={row.depth} selected={selectedId === row.span.id} real={real} evidenceOpen={evidenceExpanded.has(row.span.id)} onToggleEvidence={toggleEvidence} open={expanded.has(row.span.id)} load={loads[row.span.id]} onInspect={onInspect} onToggle={onToggle} onRetry={onRetry} />)}
        </div>
        {!rows.length && <p className="p-6 text-sm text-[var(--tt-fg-muted)]">No conversation content recorded.</p>}
      </div>
    </section>
  );
}

function MeasuredEntry({ top, onMeasure, span, depth, selected, real, evidenceOpen, onToggleEvidence, open, load, onInspect, onToggle, onRetry }: {
  top: number; onMeasure: (id: string, height: number) => void; span: TraceSpan; depth: number; selected: boolean; real: boolean; evidenceOpen: boolean; onToggleEvidence: (id: string) => void; open: boolean; load?: LoadState;
  onInspect: (id: string) => void; onToggle: (id: string) => void; onRetry: (id: string) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const observer = new ResizeObserver(entries => onMeasure(span.id, Math.ceil(entries[0].borderBoxSize[0].blockSize)));
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [span.id, onMeasure]);
  const isPrompt = span.kind === "turn", isReply = span.kind === "llm", isAgent = span.kind === "agent";
  const value = isPrompt ? span.content?.input : isReply ? span.content?.output : undefined;
  const text = useMemo(() => formatContent(value, 6000), [value]);
  const label = isReply ? "Assistant" : isPrompt && span.turnKind === "notification" && !span.recordOnly ? "Agent report / notification" : span.title;
  const Icon = isPrompt || isReply ? MessageSquare : isAgent ? GitBranch : Wrench;
  const canExpand = isAgent && (!!span.agent?.childId || span.children.length > 0);
  return (
    <div ref={ref} data-conversation-span={span.id} className="absolute left-0 w-full px-3 pb-3 pt-1 sm:px-5" style={{ top }}>
      <article className={`min-w-0 rounded-lg border px-4 py-3 ${selected ? "border-[var(--tt-border-focus)] bg-[var(--tt-brand-glow)]" : isPrompt ? "border-[var(--tt-border)] bg-[var(--tt-raised)]" : "border-transparent"} ${depth ? "border-l-2 border-l-[var(--tt-brand)]" : ""}`}>
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2 text-sm font-medium text-[var(--tt-fg)]"><Icon size={14} className={`shrink-0 ${isAgent ? "text-[var(--tt-brand)]" : "text-[var(--tt-fg-muted)]"}`} /><span className="truncate">{depth > 0 ? "↳ " : ""}{label}</span>{span.error && <span className="text-xs text-[var(--tt-danger-fg)]">Error</span>}</div>
          <button type="button" aria-label={`Inspect ${span.title}`} onClick={() => onInspect(span.id)} className="shrink-0 rounded px-1.5 py-1 text-xs text-[var(--tt-fg-muted)] hover:bg-[var(--tt-raised)] hover:text-[var(--tt-brand)]"><FileSearch size={14} /></button>
        </div>
        {(isPrompt || isReply) && text.text ? <div className="mt-2 break-words text-sm leading-7 text-[var(--tt-fg)]">{isReply ? <div className="space-y-3 [&_pre]:overflow-x-auto [&_pre]:rounded-md [&_pre]:bg-[var(--tt-sunken)] [&_pre]:p-3 [&_pre]:text-xs [&_code]:font-mono [&_a]:text-[var(--tt-brand)] [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_table]:block [&_table]:overflow-x-auto [&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-semibold"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{ img: ({ alt }) => <span>{`[image${alt ? `: ${alt}` : ""}]`}</span> }}>{text.text}</ReactMarkdown></div> : <span className="whitespace-pre-wrap">{text.text}</span>}{text.truncated && <button type="button" onClick={() => onInspect(span.id)} className="ml-1 text-[var(--tt-brand)]">… Read full record</button>}</div> : <p className="mt-1 break-words text-xs leading-6 text-[var(--tt-fg-muted)]">{span.label || (isReply ? `${span.recordOnly ? "Assistant entry" : "Model call"} · no response text recorded` : isPrompt ? "No readable request recorded" : isAgent ? "Delegated work" : "Recorded tool call")}</p>}
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-[var(--tt-fg-muted)]">
          {real && <span className="font-mono tabular-nums">{fmtClock(span.start)}{!isPrompt ? ` · ${span.approxStart ? "≈ " : ""}${fmtDur(span.end - span.start)}` : ""}</span>}
          {isReply && <span>{span.title}</span>}
          {span.content?.reasoning != null && <button type="button" onClick={() => onInspect(span.id)} className="inline-flex items-center gap-1 hover:text-[var(--tt-brand)]"><Brain size={12} /> Recorded reasoning</button>}
          {!isPrompt && !isReply && <button type="button" onClick={() => onToggleEvidence(span.id)} aria-expanded={evidenceOpen} className="inline-flex items-center gap-1 text-[var(--tt-brand)]"><ChevronRight size={12} className={evidenceOpen ? "rotate-90" : ""} />Input & result</button>}
          {canExpand && <button type="button" onClick={() => onToggle(span.id)} aria-expanded={open} className="inline-flex items-center gap-1 text-[var(--tt-brand)]"><ChevronRight size={12} className={open ? "rotate-90" : ""} />{open ? "Hide child recording" : "Explore child recording"}</button>}
          {isAgent && open && span.agent?.loaded && span.children.length === 0 && <span>No readable child records returned.</span>}
          {load?.state === "pending" && <span role="status">Loading child recording…</span>}
          {load?.state === "error" && <button type="button" onClick={() => onRetry(span.id)} className="text-[var(--tt-danger-fg)]">Could not load · Retry</button>}
        </div>
        {evidenceOpen && <InlineEvidence span={span} />}
      </article>
    </div>
  );
}
