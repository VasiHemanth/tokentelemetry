"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type CSSProperties } from "react";
import { ListChevronsDownUp, ListChevronsUpDown, RotateCcw, Copy, Check, Search, ChevronDown, GitBranch, MessageSquare, FileCode } from "lucide-react";
import { useSearchParams } from "next/navigation";
import type { Event } from "@/lib/traceEvents";
import { readWorkspaceLocation, updateWorkspaceLocation, type WorkspaceView } from "@/lib/traceTree/workspace";
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
  ownerAgent,
  type TraceFilter,
} from "@/lib/traceTree/tree";
import { buildScale, fmtClock, fmtDur, fmtTokens } from "@/lib/traceTree/timeScale";
import Swimlanes from "./Swimlanes";
import SpanTable, { type LoadState, type TableRow } from "./SpanTable";
import SpanDetail from "./SpanDetail";
import Conversation from "./Conversation";
import EventLog from "./EventLog";
import EvidenceDrawer from "./EvidenceDrawer";
import WorkspaceDivider from "./WorkspaceDivider";
import ContentSection from "./ContentSection";
import { SKILL_COLOR, makeColorOf } from "./shared";

export interface TraceViewProps {
  roots: TraceSpan[];
  timing: TraceTiming;
  notice?: string;
  /** Epoch ms of the session's first event; adds an "Into session" offset to the detail panel. */
  sessionStart?: number;
  /** Fetch an agent span's own trace; the parent re-renders with new roots when it resolves. */
  onLoadChild?: (span: TraceSpan) => Promise<void>;
  onJumpToEvent?: (eventIndex: number) => void;
  /** API event records, including metadata filtered out of the readable trace. */
  sourceEvents?: Event[];
  className?: string;
}

const FILTERS: Array<[TraceFilter, string]> = [
  ["all", "Everything"],
  ["agents", "Agents & skills"],
  ["errors", "Errors"],
];

const MIN_WINDOW = 0.002;

export default function TraceView({ roots, timing, notice, sessionStart, onLoadChild, onJumpToEvent, sourceEvents = [], className = "" }: TraceViewProps) {
  const searchParams = useSearchParams();
  const location = readWorkspaceLocation(searchParams);
  const view = location.view;
  const real = timing === "real";
  const index = useMemo(() => buildIndex(roots), [roots]);
  const rollups = useMemo(() => computeRollups(roots), [roots]);
  const scale = useMemo(() => buildScale([...roots, ...index.agents].map((s): [number, number] => [s.start, s.end])), [roots, index]);
  const colorOf = useMemo(() => makeColorOf(index.agents.map((a) => a.agent?.agentType ?? a.title)), [index]);
  const canLoad = !!onLoadChild;
  const lazyIds = useMemo(() => new Set(index.all.filter((s) => isLazyAgent(s, canLoad)).map((s) => s.id)), [index, canLoad]);

  const [expanded, setExpanded] = useState<Set<string>>(() => defaultExpanded(roots));
  const [filter, setFilter] = useState<TraceFilter>("all");
  const selectedId = location.span ?? roots[0]?.id ?? null;
  const [sourceEvent, setSourceEvent] = useState<Event | null>(null);
  const [search, setSearch] = useState("");
  const [copied, setCopied] = useState(false);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [outlineOpen, setOutlineOpen] = useState(false);
  const [win, setWinState] = useState<[number, number]>([0, 1]);
  const [loads, setLoads] = useState<Record<string, LoadState>>({});
  const scrollRef = useRef<HTMLDivElement>(null);
  const workspaceRef = useRef<HTMLDivElement>(null);
  const [splitPercent, setSplitPercent] = useState(34);
  const scrollReq = useRef<{ id: string; block: ScrollLogicalPosition } | null>(null);
  const restoredSelection = useRef<string | null>(null);

  const spanRows = useMemo(() => {
    const all = flattenVisible(roots, expanded, filter);
    const query = search.toLowerCase().trim();
    return query ? all.filter(({ span }) => `${span.title} ${span.label || ""}`.toLowerCase().includes(query)) : all;
  }, [roots, expanded, filter, search]);
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

  const updateLocation = useCallback((patch: { view?: WorkspaceView; span?: string | null }) => {
    const params = updateWorkspaceLocation(new URLSearchParams(window.location.search), patch);
    window.history.replaceState(null, "", `${window.location.pathname}?${params}${window.location.hash}`);
  }, []);

  const stats = useMemo(() => {
    const prompts = roots.filter((r) => r.kind === "turn" && r.turnKind !== "notification").length;
    const mainCalls = index.all.filter(s => s.kind === "llm" && !ownerAgent(index, s));
    const withUsage = mainCalls.filter(s => s.tokens != null).length;
    return {
      wall: scale.t1 - scale.t0,
      active: scale.busyMs,
      prompts,
      recordOnly: roots.some(root => root.recordOnly),
      // A spawn call that never produced a subagent is still a row, but not a subagent.
      agents: index.agents.filter((a) => !a.error).length,
      skills: index.skills.length,
      peak: peakConcurrency(index.agents),
      tokens: mainTokens(roots),
      hasUsage: withUsage > 0,
      partialUsage: withUsage < mainCalls.length,
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
      updateLocation({ span: id });
      if (mode === "reveal") {
        setSearch("");
        if (!matchesFilter(span, filter)) setFilter("all");
        const anc: string[] = [];
        for (let p = index.parent.get(id); p; p = index.parent.get(p.id)) anc.push(p.id);
        if (anc.length) setExpanded((prev) => new Set([...prev, ...anc]));
      }
      if (mode) scrollReq.current = { id, block: mode === "reveal" ? "center" : "nearest" };
    },
    [index, filter, updateLocation],
  );

  // A link into an already-known child can restore it without loading unrelated agents.
  useEffect(() => {
    if (!selectedId || selected) return;
    const ancestor = index.agents.find(a => selectedId.startsWith(`${a.id}/`) && lazyIds.has(a.id));
    if (!ancestor || loads[ancestor.id]) return;
    const task = window.setTimeout(() => startLoad(ancestor), 0);
    return () => window.clearTimeout(task);
  }, [selectedId, selected, index, lazyIds, loads, startLoad]);

  // Restore ancestor expansion after a linked child recording arrives. Do this
  // once per selection/view so a user's later collapse action still works.
  useEffect(() => {
    if (view === "events") { restoredSelection.current = null; return; }
    if (!selected) return;
    const key = `${view}:${selected.id}`;
    if (restoredSelection.current === key) return;
    const ancestors: string[] = [];
    for (let parent = index.parent.get(selected.id); parent; parent = index.parent.get(parent.id)) ancestors.push(parent.id);
    const task = window.setTimeout(() => {
      restoredSelection.current = key;
      setExpanded(previous => new Set([...previous, ...ancestors]));
      scrollReq.current = { id: selected.id, block: "center" };
    }, 0);
    return () => window.clearTimeout(task);
  }, [view, selected, index]);

  useEffect(() => {
    const req = scrollReq.current;
    if (!req) return;
    const box = scrollRef.current;
    const rowIndex = rows.findIndex(r => r.type === "span" && r.span.id === req.id);
    if (!box || rowIndex < 0) return;
    scrollReq.current = null;
    // Scroll only the table. scrollIntoView would also move the page section the
    // trace sits in, pushing the timeline out of view.
    const head = 36;
    const top = head + rowIndex * 36;
    let target: number | null = null;
    if (req.block === "center") target = top - (box.clientHeight - 36) / 2;
    else if (top < box.scrollTop + head) target = top - head;
    else if (top + 36 > box.scrollTop + box.clientHeight) target = top + 36 - box.clientHeight;
    if (target !== null) {
      box.scrollTo({ top: Math.max(0, target), behavior: "auto" });
    }
  }, [selectedId, rows, view]);

  const onSelectReveal = useCallback((id: string) => { select(id, "reveal"); setOutlineOpen(false); }, [select]);
  const setView = (next: WorkspaceView) => {
    updateLocation({ view: next });
    if (next === "execution" && selectedId) select(selectedId, "reveal");
  };
  const inspectEvidence = (id: string) => {
    select(id, "reveal");
    setEvidenceOpen(true);
  };

  const zoomTo = useCallback(
    (span: TraceSpan) => {
      const a = scale.u(span.start);
      const b = scale.u(Math.max(span.end, span.start + 1000));
      const pad = Math.max(0.004, (b - a) * 0.08);
      setWin([Math.max(0, a - pad), Math.min(1, b + pad)]);
      updateLocation({ view: "execution", span: span.id });
    },
    [scale, setWin, updateLocation],
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


  const zoomed = win[0] > 0 || win[1] < 1;
  const card = "rounded-xl border border-[var(--tt-border)] bg-[var(--tt-panel)]";
  const stat = (v: string | number, k: string) => (
    <span key={k} className="inline-flex items-baseline gap-1.5 whitespace-nowrap">
      <b className="font-mono text-[13px] font-semibold tabular-nums text-[var(--tt-fg)]">{v}</b>
      <span className="text-[11px] text-[var(--tt-fg-muted)]">{k}</span>
    </span>
  );
  const statLine = (
    <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
      {real && stat(fmtDur(stats.wall), "wall clock")}
      {real && stat(fmtDur(stats.active), "active")}
      {stat(stats.prompts, stats.recordOnly ? (stats.prompts === 1 ? "user entry" : "user entries") : stats.prompts === 1 ? "prompt" : "prompts")}
      {stat(stats.agents, stats.agents === 1 ? "subagent" : "subagents")}
      {stat(stats.skills, stats.skills === 1 ? "skill" : "skills")}
      {real && stat(stats.peak, "peak parallel")}
      {stat(stats.hasUsage ? `${fmtTokens(stats.tokens)}${stats.partialUsage ? "+" : ""}` : "Unavailable", stats.partialUsage ? "recorded main tokens" : "main tokens")}
    </div>
  );
  const types = [...new Set(index.agents.map((a) => a.agent?.agentType ?? a.title))];

  return (
    <div className={`@container flex min-h-0 flex-col gap-3 ${className}`}>
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-[var(--tt-border)] pb-3">
        <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Session workspace views">
          {([["conversation", "Session", MessageSquare], ["execution", "Execution focus", GitBranch], ["events", "Event log", FileCode]] as const).map(([key, label, Icon]) => <button key={key} type="button" onClick={() => setView(key)} aria-pressed={view === key} className={`inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors ${view === key ? "bg-[var(--tt-brand-glow)] text-[var(--tt-brand)]" : "text-[var(--tt-fg-muted)] hover:bg-[var(--tt-raised)] hover:text-[var(--tt-fg)]"}`}><Icon size={15} />{label}</button>)}
        </div>
        <button type="button" onClick={async () => { try { await navigator.clipboard.writeText(window.location.href); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { setCopied(false); } }} className="inline-flex items-center gap-2 rounded-md border border-[var(--tt-border)] px-3 py-2 text-xs text-[var(--tt-fg-muted)] hover:bg-[var(--tt-raised)]">{copied ? <Check size={13} /> : <Copy size={13} />}{copied ? "Copied" : "Copy view link"}</button>
      </div>
      <div className="shrink-0 px-1 py-1">{statLine}</div>
      {notice && <p className="shrink-0 px-1 text-xs leading-5 text-[var(--tt-fg-muted)]">{notice}</p>}
      {view === "conversation" && <button type="button" onClick={() => setOutlineOpen(value => !value)} aria-expanded={outlineOpen} className="shrink-0 self-start rounded-md border border-[var(--tt-border)] px-3 py-2 text-xs text-[var(--tt-brand)] @min-[800px]:hidden">{outlineOpen ? "Back to conversation" : "Show execution navigation"}</button>}

      {real && view === "execution" && (
        <details className={`${card} group shrink-0 p-3`} open>
          <summary className="mb-3 flex cursor-pointer list-none items-center justify-between text-sm font-medium text-[var(--tt-fg)]">Execution timeline<span className="inline-flex items-center gap-2 text-xs font-normal text-[var(--tt-fg-muted)]">Recorded activity · approximate starts marked ≈ <ChevronDown size={14} /></span></summary>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[var(--tt-fg-muted)]">
              <Legend color="var(--tt-brand)" label="main agent" />
              {index.skills.length > 0 && <Legend color={SKILL_COLOR} label="skill" />}
              {types.map((t) => (
                <Legend key={t} color={colorOf(t)} label={t} />
              ))}
              {zoomed ? (
                <>
                  <span className="font-mono text-[var(--tt-fg-muted)]">
                    {fmtClock(scale.tOf(win[0]))} to {fmtClock(scale.tOf(win[1]))}
                  </span>
                  <ToolBtn onClick={() => setWin([0, 1])} icon={<RotateCcw size={11} />} label="Reset zoom" />
                </>
              ) : (
                <span className="text-[var(--tt-fg-muted)]">drag to zoom, double-click to reset</span>
              )}
            </div>
          </div>
          <Swimlanes roots={roots} index={index} scale={scale} win={win} onWin={setWin} selected={selected} onSelect={onSelectReveal} colorOf={colorOf} />
        </details>
      )}

      <div ref={workspaceRef} style={{ "--trace-split": `${splitPercent}%` } as CSSProperties} className={`grid flex-1 gap-3 ${view === "conversation" ? "min-h-[360px] @min-[800px]:min-h-0 grid-rows-1 @min-[800px]:gap-0 @min-[800px]:grid-cols-[var(--trace-split)_12px_minmax(0,1fr)] @min-[800px]:grid-rows-1" : "min-h-0 grid-rows-[minmax(240px,3fr)_minmax(180px,2fr)] @min-[800px]:grid-cols-[minmax(0,1fr)_clamp(280px,30%,420px)] @min-[800px]:grid-rows-1"}`}>
        <section className={`${card} ${view === "conversation" && !outlineOpen ? "hidden @min-[800px]:flex" : "flex"} min-h-0 min-w-0 flex-col overflow-hidden`}>
          {view === "events" ? <EventLog events={sourceEvents} selected={sourceEvent} onSelect={setSourceEvent} /> : <>
          <div className="flex shrink-0 items-center justify-between border-b border-[var(--tt-border)] px-3 py-2"><h2 className="text-sm font-medium text-[var(--tt-fg)]">Execution</h2>{view === "conversation" && <button type="button" onClick={() => setEvidenceOpen(true)} className="text-xs text-[var(--tt-brand)]">Inspect selected</button>}</div>
          <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-[var(--tt-border)] px-3 py-2">
            <div className="flex items-center gap-1" role="group" aria-label="Filter spans">
              {FILTERS.map(([f, label]) => (
                <button
                  key={f}
                  type="button"
                  aria-pressed={filter === f}
                  onClick={() => setFilter(f)}
                  className={`rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
                    filter === f
                      ? "border-[var(--tt-border-focus)] bg-[var(--tt-brand-glow)] text-[var(--tt-brand)]"
                      : "border-[var(--tt-border)] text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)]"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <label className="flex min-w-0 items-center gap-2 text-[var(--tt-fg-muted)]"><Search size={13} /><input aria-label="Search visible span labels" value={search} onChange={e => setSearch(e.target.value)} placeholder="Find a span…" className="w-32 rounded border border-[var(--tt-border)] bg-[var(--tt-sunken)] px-2 py-1.5 text-xs text-[var(--tt-fg)]" /></label>
            <div className="flex items-center gap-2">
              <ToolBtn onClick={() => setExpanded((prev) => new Set([...prev, ...expandAllIds(roots)]))} icon={<ListChevronsUpDown size={11} />} label="Expand all" />
              <ToolBtn onClick={() => setExpanded(new Set())} icon={<ListChevronsDownUp size={11} />} label="Collapse" />
            </div>
          </div>
          <SpanTable
            compact={view === "conversation"}
            rows={rows}
            index={index}
            rollups={rollups}
            real={real}
            selectedId={selectedId}
            expanded={expanded}
            lazyIds={lazyIds}
            colorOf={colorOf}
            scrollRef={scrollRef}
            onToggle={toggle}
            onSelect={onSelectReveal}
            onRetry={(id) => {
              const s = index.byId.get(id);
              if (s) startLoad(s);
            }}
            onKeyDown={onKeyDown}
          />
          </>}
        </section>
        {view === "conversation" && <WorkspaceDivider value={splitPercent} onChange={setSplitPercent} container={workspaceRef} />}
        {view === "conversation" ? <div className={`${card} ${outlineOpen ? "hidden @min-[800px]:flex" : "flex"} min-h-0 min-w-0 overflow-hidden`}><Conversation roots={roots} selectedId={selectedId} expanded={expanded} loads={loads} onFollow={onSelectReveal} onInspect={inspectEvidence} onToggle={toggle} onRetry={id => { const span = index.byId.get(id); if (span) startLoad(span); }} real={real} /></div> :
        <aside className={`${card} min-h-0 min-w-0 overflow-y-auto overscroll-contain p-3 scrollbar-thin`}>
          {view === "events" ? sourceEvent ? <div className="space-y-3"><h2 className="text-base font-medium text-[var(--tt-fg)]">API event record</h2><p className="text-xs leading-6 text-[var(--tt-fg-muted)]">Event returned by the harness reader. Some harnesses normalize their native records on the backend.</p><ContentSection label="Event payload" value={sourceEvent} plain /></div> : <p className="p-3 text-sm text-[var(--tt-fg-muted)]">Select a record to inspect its payload.</p> : <SpanDetail
            span={selected}
            index={index}
            rollups={rollups}
            colorOf={colorOf}
            real={real}
            sessionStart={sessionStart}
            onSelect={onSelectReveal}
            onZoom={zoomTo}
            onJumpToEvent={onJumpToEvent}
          />}
        </aside>}
      </div>
      <EvidenceDrawer open={evidenceOpen && view === "conversation"} onClose={() => setEvidenceOpen(false)}><SpanDetail
            span={selected}
            index={index}
            rollups={rollups}
            colorOf={colorOf}
            real={real}
            sessionStart={sessionStart}
            onSelect={onSelectReveal}
            onZoom={zoomTo}
            onJumpToEvent={onJumpToEvent}
          /></EvidenceDrawer>
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
      className="inline-flex items-center gap-1 rounded-md border border-[var(--tt-border)] px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--tt-fg-muted)] transition-colors hover:border-[var(--tt-border-strong)] hover:text-[var(--tt-fg)]"
    >
      {icon}
      {label}
    </button>
  );
}
