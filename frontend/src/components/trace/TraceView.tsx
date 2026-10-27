"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { ListChevronsDownUp, ListChevronsUpDown, RotateCcw } from "lucide-react";
import type { TraceSpan, TraceTiming } from "@/lib/traceTree/types";
import {
  buildIndex,
  computeRollups,
  defaultExpanded,
  expandAllIds,
  flattenVisible,
  isLazyAgent,
  mainTokens,
  matchesFilter,
  peakConcurrency,
  type TraceFilter,
} from "@/lib/traceTree/tree";
import { buildScale, fmtClock, fmtDur, fmtTokens } from "@/lib/traceTree/timeScale";
import Swimlanes from "./Swimlanes";
import SpanTable, { type LoadState, type TableRow } from "./SpanTable";
import SpanDetail from "./SpanDetail";
import { SECTION_LABEL, makeColorOf } from "./shared";

export interface TraceViewProps {
  roots: TraceSpan[];
  timing: TraceTiming;
  /** Epoch ms of the session's first event; adds an "Into session" offset to the detail panel. */
  sessionStart?: number;
  /** Fetch an agent span's own trace; the parent re-renders with new roots when it resolves. */
  onLoadChild?: (span: TraceSpan) => Promise<void>;
  onJumpToEvent?: (eventIndex: number) => void;
  className?: string;
}

const FILTERS: Array<[TraceFilter, string]> = [
  ["all", "Everything"],
  ["agents", "Subagents"],
  ["errors", "Errors"],
];

const MIN_WINDOW = 0.002;

export default function TraceView({ roots, timing, sessionStart, onLoadChild, onJumpToEvent, className = "" }: TraceViewProps) {
  const real = timing === "real";
  const index = useMemo(() => buildIndex(roots), [roots]);
  const rollups = useMemo(() => computeRollups(roots), [roots]);
  const scale = useMemo(() => buildScale([...roots, ...index.agents].map((s): [number, number] => [s.start, s.end])), [roots, index]);
  const colorOf = useMemo(() => makeColorOf(index.agents.map((a) => a.agent?.agentType ?? a.title)), [index]);
  const canLoad = !!onLoadChild;
  const lazyIds = useMemo(() => new Set(index.all.filter((s) => isLazyAgent(s, canLoad)).map((s) => s.id)), [index, canLoad]);

  const [expanded, setExpanded] = useState<Set<string>>(() => defaultExpanded(roots));
  const [filter, setFilter] = useState<TraceFilter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [win, setWinState] = useState<[number, number]>([0, 1]);
  const [loads, setLoads] = useState<Record<string, LoadState>>({});
  const scrollRef = useRef<HTMLDivElement>(null);
  const scrollReq = useRef<{ id: string; block: ScrollLogicalPosition } | null>(null);

  const spanRows = useMemo(() => flattenVisible(roots, expanded, filter), [roots, expanded, filter]);
  const rows = useMemo<TableRow[]>(() => {
    const out: TableRow[] = [];
    for (const r of spanRows) {
      out.push({ type: "span", ...r });
      const load = loads[r.span.id];
      if (load && expanded.has(r.span.id)) out.push({ type: "status", id: r.span.id, depth: r.depth + 1, load });
    }
    return out;
  }, [spanRows, loads, expanded]);

  const selected = selectedId ? (index.byId.get(selectedId) ?? null) : null;

  const stats = useMemo(() => {
    const prompts = roots.filter((r) => r.kind === "turn" && r.turnKind !== "notification").length;
    return {
      wall: scale.t1 - scale.t0,
      active: scale.busyMs,
      prompts,
      agents: index.agents.length,
      peak: peakConcurrency(index.agents),
      tokens: mainTokens(roots),
    };
  }, [roots, scale, index]);

  const setWin = useCallback((w: [number, number]) => {
    let [a, b] = w;
    if (b - a < MIN_WINDOW) {
      a = Math.max(0, a - MIN_WINDOW / 2);
      b = Math.min(1, a + MIN_WINDOW);
    }
    setWinState([a, b]);
  }, []);

  const startLoad = useCallback(
    (span: TraceSpan) => {
      if (!onLoadChild) return;
      setLoads((prev) => ({ ...prev, [span.id]: { state: "pending" } }));
      onLoadChild(span).then(
        () =>
          setLoads((prev) => {
            const next = { ...prev };
            delete next[span.id];
            return next;
          }),
        (err: unknown) =>
          setLoads((prev) => ({ ...prev, [span.id]: { state: "error", message: err instanceof Error ? err.message : String(err) } })),
      );
    },
    [onLoadChild],
  );

  const toggle = useCallback(
    (id: string) => {
      const span = index.byId.get(id);
      if (!span || !(span.children.length || lazyIds.has(id))) return;
      const opening = !expanded.has(id);
      setExpanded((prev) => {
        const next = new Set(prev);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        return next;
      });
      if (opening && lazyIds.has(id) && loads[id]?.state !== "pending") startLoad(span);
    },
    [index, lazyIds, expanded, loads, startLoad],
  );

  const select = useCallback(
    (id: string, mode?: "reveal" | "keyboard") => {
      const span = index.byId.get(id);
      if (!span) return;
      setSelectedId(id);
      if (mode === "reveal") {
        if (!matchesFilter(span, filter)) setFilter("all");
        const anc: string[] = [];
        for (let p = index.parent.get(id); p; p = index.parent.get(p.id)) anc.push(p.id);
        if (anc.length) setExpanded((prev) => new Set([...prev, ...anc]));
      }
      if (mode) scrollReq.current = { id, block: mode === "reveal" ? "center" : "nearest" };
    },
    [index, filter],
  );

  useEffect(() => {
    const req = scrollReq.current;
    if (!req) return;
    const el = scrollRef.current?.querySelector(`[data-span-id="${CSS.escape(req.id)}"]`);
    if (el) {
      scrollReq.current = null;
      el.scrollIntoView({ block: req.block, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    }
  }, [selectedId, rows]);

  const onSelectReveal = useCallback((id: string) => select(id, "reveal"), [select]);
  const onSelectPlain = useCallback((id: string) => select(id), [select]);

  const zoomTo = useCallback(
    (span: TraceSpan) => {
      const a = scale.u(span.start);
      const b = scale.u(Math.max(span.end, span.start + 1000));
      const pad = Math.max(0.004, (b - a) * 0.08);
      setWin([Math.max(0, a - pad), Math.min(1, b + pad)]);
    },
    [scale, setWin],
  );

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const cur = selected ? spanRows.findIndex((r) => r.span.id === selected.id) : -1;
    if (e.key === "ArrowDown") {
      const r = spanRows[Math.min(spanRows.length - 1, cur + 1)];
      if (r) select(r.span.id, "keyboard");
    } else if (e.key === "ArrowUp") {
      const r = spanRows[Math.max(0, cur - 1)];
      if (r) select(r.span.id, "keyboard");
    } else if (e.key === "ArrowRight" && selected) {
      const hasKids = selected.children.length > 0 || lazyIds.has(selected.id);
      if (hasKids && !expanded.has(selected.id)) toggle(selected.id);
      else if (selected.children[0] && spanRows.some((r) => r.span.id === selected.children[0].id)) select(selected.children[0].id, "keyboard");
    } else if (e.key === "ArrowLeft" && selected) {
      const parent = index.parent.get(selected.id);
      if (expanded.has(selected.id) && (selected.children.length || lazyIds.has(selected.id))) toggle(selected.id);
      else if (parent) select(parent.id, "keyboard");
    } else return;
    e.preventDefault();
  };

  if (!roots.length) {
    return <div className={`rounded-xl border border-[var(--tt-border)] bg-[var(--tt-panel)] p-6 text-center text-xs text-[var(--tt-fg-dim)] ${className}`}>No spans recorded for this session.</div>;
  }

  const zoomed = win[0] > 0 || win[1] < 1;
  const card = "rounded-xl border border-[var(--tt-border)] bg-[var(--tt-panel)]";
  const stat = (v: string | number, k: string) => (
    <div key={k} className="flex min-w-[88px] flex-col gap-0.5 px-3 py-2">
      <b className="font-mono text-sm font-semibold text-[var(--tt-fg)]">{v}</b>
      <span className="text-[10px] uppercase tracking-[0.18em] text-[var(--tt-fg-dim)]">{k}</span>
    </div>
  );
  const types = [...new Set(index.agents.map((a) => a.agent?.agentType ?? a.title))];

  return (
    <div className={`flex flex-col gap-3 ${className}`}>
      <div className={`${card} flex flex-wrap divide-x divide-[var(--tt-border)]`}>
        {real && stat(fmtDur(stats.wall), "Wall clock")}
        {real && stat(fmtDur(stats.active), "Active")}
        {stat(stats.prompts, "Prompts")}
        {stat(stats.agents, "Subagents")}
        {stat(stats.peak, "Peak parallel")}
        {stat(fmtTokens(stats.tokens), "Main tokens")}
      </div>

      {real && (
        <section className={`${card} p-3`}>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <span className={SECTION_LABEL}>Timeline</span>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-[var(--tt-fg-muted)]">
              <Legend color="var(--tt-brand)" label="main agent" />
              {types.map((t) => (
                <Legend key={t} color={colorOf(t)} label={t} />
              ))}
              <span className="text-[var(--tt-fg-dim)]">drag to zoom, double-click to reset</span>
            </div>
          </div>
          <Swimlanes roots={roots} index={index} scale={scale} win={win} onWin={setWin} selectedId={selectedId} onSelect={onSelectReveal} colorOf={colorOf} />
        </section>
      )}

      <div className="grid items-start gap-3 min-[1100px]:grid-cols-[minmax(0,1fr)_340px]">
        <section className={`${card} min-w-0 overflow-hidden`}>
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--tt-border)] px-3 py-2">
            <div className="flex items-center gap-1" role="group" aria-label="Filter spans">
              {FILTERS.map(([f, label]) => (
                <button
                  key={f}
                  type="button"
                  aria-pressed={filter === f}
                  onClick={() => setFilter(f)}
                  className={`rounded-md border px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] transition-colors ${
                    filter === f
                      ? "border-[var(--tt-border-focus)] bg-[var(--tt-brand-glow)] text-[var(--tt-brand)]"
                      : "border-[var(--tt-border)] text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)]"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              {real && zoomed && (
                <>
                  <span className="font-mono text-[10px] text-[var(--tt-fg-dim)]">
                    {fmtClock(scale.tOf(win[0]))} to {fmtClock(scale.tOf(win[1]))}
                  </span>
                  <ToolBtn onClick={() => setWin([0, 1])} icon={<RotateCcw size={11} />} label="Reset zoom" />
                </>
              )}
              <ToolBtn onClick={() => setExpanded((prev) => new Set([...prev, ...expandAllIds(roots)]))} icon={<ListChevronsUpDown size={11} />} label="Expand all" />
              <ToolBtn onClick={() => setExpanded(new Set())} icon={<ListChevronsDownUp size={11} />} label="Collapse" />
            </div>
          </div>
          <SpanTable
            rows={rows}
            index={index}
            rollups={rollups}
            scale={scale}
            win={win}
            real={real}
            selectedId={selectedId}
            expanded={expanded}
            lazyIds={lazyIds}
            colorOf={colorOf}
            scrollRef={scrollRef}
            onToggle={toggle}
            onSelect={onSelectPlain}
            onRetry={(id) => {
              const s = index.byId.get(id);
              if (s) startLoad(s);
            }}
            onKeyDown={onKeyDown}
          />
        </section>

        <aside className={`${card} min-w-0 p-3 min-[1100px]:sticky min-[1100px]:top-4 min-[1100px]:max-h-[calc(100vh-2rem)] min-[1100px]:overflow-y-auto`}>
          <SpanDetail
            span={selected}
            index={index}
            rollups={rollups}
            colorOf={colorOf}
            real={real}
            sessionStart={sessionStart}
            onSelect={onSelectReveal}
            onZoom={zoomTo}
            onJumpToEvent={onJumpToEvent}
          />
        </aside>
      </div>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <i className="size-2 rounded-sm" style={{ background: color }} />
      {label}
    </span>
  );
}

function ToolBtn({ onClick, icon, label }: { onClick: () => void; icon: React.ReactNode; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1 rounded-md border border-[var(--tt-border)] px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--tt-fg-muted)] transition-colors hover:border-[var(--tt-border-strong)] hover:text-[var(--tt-fg)]"
    >
      {icon}
      {label}
    </button>
  );
}
