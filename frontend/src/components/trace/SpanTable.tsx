"use client";

import { memo, useEffect, useMemo, useRef, useState, type KeyboardEvent, type RefObject } from "react";
import { ChevronRight, Loader2, RotateCw } from "lucide-react";
import type { TraceSpan } from "@/lib/traceTree/types";
import { agentBursts, type Rollup, type Row, type TraceIndex } from "@/lib/traceTree/tree";
import { axisMarks, fmtDur, fmtHm, fmtTokens, type TimeScale } from "@/lib/traceTree/timeScale";
import { Axis, HATCH, KindChip, Tag, type ColorOf } from "./shared";

export type LoadState = { state: "pending" } | { state: "error"; message: string };

export type TableRow =
  | ({ type: "span" } & Row)
  | { type: "status"; id: string; depth: number; load: LoadState };

const COLS_REAL = "minmax(0,1fr) 56px 60px 38%";
const COLS_ORDER = "minmax(0,1fr) 60px";

interface Props {
  rows: TableRow[];
  index: TraceIndex;
  rollups: Map<string, Rollup>;
  scale: TimeScale;
  win: [number, number];
  real: boolean;
  selectedId: string | null;
  expanded: ReadonlySet<string>;
  lazyIds: ReadonlySet<string>;
  colorOf: ColorOf;
  scrollRef: RefObject<HTMLDivElement | null>;
  onToggle: (id: string) => void;
  onSelect: (id: string) => void;
  onRetry: (id: string) => void;
  onKeyDown: (e: KeyboardEvent<HTMLDivElement>) => void;
}

export default function SpanTable(p: Props) {
  const { rows, scale, win, real, scrollRef, onKeyDown, onToggle, onSelect } = p;
  const axisRef = useRef<HTMLDivElement>(null);
  const [axisW, setAxisW] = useState(400);

  useEffect(() => {
    const el = axisRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setAxisW(el.clientWidth));
    ro.observe(el);
    return () => ro.disconnect();
  }, [real]);

  const marks = useMemo(() => (real ? axisMarks(scale, win[0], win[1], axisW) : []), [real, scale, win, axisW]);
  const cols = real ? COLS_REAL : COLS_ORDER;
  const span = win[1] - win[0];

  const bands = useMemo(() => {
    if (!real) return [];
    return scale.pieces
      .filter((pc) => pc.gap)
      .map((pc) => ({ a: (pc.u0 - win[0]) / span, b: (pc.u1 - win[0]) / span }))
      .filter((g) => g.b > 0 && g.a < 1);
  }, [real, scale, win, span]);

  const onClick = (e: React.MouseEvent) => {
    const el = (e.target as HTMLElement).closest<HTMLElement>("[data-span-id]");
    if (!el) return;
    const id = el.dataset.spanId!;
    if ((e.target as HTMLElement).closest("[data-chevron]")) onToggle(id);
    else onSelect(id);
  };
  const onDoubleClick = (e: React.MouseEvent) => {
    const el = (e.target as HTMLElement).closest<HTMLElement>("[data-span-id]");
    if (el) onToggle(el.dataset.spanId!);
  };

  return (
    <div
      ref={scrollRef}
      role="tree"
      aria-label="Span tree"
      tabIndex={0}
      onKeyDown={onKeyDown}
      onClick={onClick}
      onDoubleClick={onDoubleClick}
      className="max-h-[70vh] overflow-auto outline-none focus-visible:ring-1 focus-visible:ring-[var(--tt-border-focus)] scrollbar-thin"
    >
      <div className="min-w-[640px]">
        <div
          className="sticky top-0 z-20 grid items-end border-b border-[var(--tt-border-strong)] bg-[var(--tt-panel)] text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--tt-fg-dim)]"
          style={{ gridTemplateColumns: cols }}
        >
          <div className="px-3 py-1.5">Span</div>
          {real && <div className="px-2 py-1.5 text-right">Dur</div>}
          <div className="px-2 py-1.5 text-right">Tokens</div>
          {real && (
            <div ref={axisRef} className="border-l border-[var(--tt-border)] normal-case tracking-normal">
              <Axis marks={marks} />
            </div>
          )}
        </div>

        <div className="relative">
          {real && (
            <div className="pointer-events-none absolute inset-y-0 right-0 w-[38%] overflow-hidden">
              {bands.map((g, i) => (
                <div
                  key={i}
                  className="absolute inset-y-0 opacity-70"
                  style={{ ...HATCH, left: `${Math.max(0, g.a) * 100}%`, width: `${(Math.min(1, g.b) - Math.max(0, g.a)) * 100}%` }}
                />
              ))}
            </div>
          )}
          {rows.length === 0 && <div className="px-3 py-6 text-center text-xs text-[var(--tt-fg-dim)]">Nothing matches this filter.</div>}
          {rows.map((r) =>
            r.type === "status" ? (
              <StatusRow key={`status-${r.id}`} id={r.id} depth={r.depth} load={r.load} cols={cols} onRetry={p.onRetry} />
            ) : (
              <SpanRow
                key={r.span.id}
                span={r.span}
                depth={r.depth}
                open={p.expanded.has(r.span.id)}
                lazy={p.lazyIds.has(r.span.id)}
                selected={p.selectedId === r.span.id}
                rollup={p.rollups.get(r.span.id)}
                index={p.index}
                scale={scale}
                w0={win[0]}
                w1={win[1]}
                real={real}
                cols={cols}
                colorOf={p.colorOf}
              />
            ),
          )}
        </div>
      </div>
    </div>
  );
}

function StatusRow({ id, depth, load, cols, onRetry }: { id: string; depth: number; load: LoadState; cols: string; onRetry: (id: string) => void }) {
  return (
    <div className="grid items-center py-1 text-xs" style={{ gridTemplateColumns: cols }}>
      <div className="flex items-center gap-2 pr-2" style={{ paddingLeft: depth * 14 + 34 }}>
        {load.state === "pending" ? (
          <>
            <Loader2 size={12} className="animate-spin text-[var(--tt-fg-dim)]" />
            <span className="text-[var(--tt-fg-dim)]">Loading subagent trace</span>
          </>
        ) : (
          <>
            <span className="truncate text-[var(--tt-danger-fg)]" title={load.message}>
              Could not load subagent trace
            </span>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onRetry(id);
              }}
              className="inline-flex items-center gap-1 rounded border border-[var(--tt-border-strong)] px-1.5 py-0.5 text-[10px] text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)]"
            >
              <RotateCw size={10} /> Retry
            </button>
          </>
        )}
      </div>
    </div>
  );
}

interface RowProps {
  span: TraceSpan;
  depth: number;
  open: boolean;
  lazy: boolean;
  selected: boolean;
  rollup?: Rollup;
  index: TraceIndex;
  scale: TimeScale;
  w0: number;
  w1: number;
  real: boolean;
  cols: string;
  colorOf: ColorOf;
}

const SpanRow = memo(function SpanRow({ span, depth, open, lazy, selected, rollup, index, scale, w0, w1, real, cols, colorOf }: RowProps) {
  const hasKids = span.children.length > 0 || lazy;
  const color = span.kind === "agent" ? colorOf(span.agent?.agentType) : undefined;
  const resumed = span.resumes ? index.agentByChild.get(span.resumes) : undefined;
  const woke = span.kind === "turn" && span.notifiedBy ? index.agentByChild.get(span.notifiedBy) : undefined;
  const errs = rollup?.errs ?? 0;

  return (
    <div
      role="treeitem"
      aria-level={depth + 1}
      aria-selected={selected}
      aria-expanded={hasKids ? open : undefined}
      data-span-id={span.id}
      className={`relative grid items-center border-b border-[var(--tt-border)]/50 text-xs [content-visibility:auto] [contain-intrinsic-size:auto_28px] hover:bg-[var(--tt-raised)] ${selected ? "bg-[var(--tt-brand-glow)]" : ""}`}
      style={{ gridTemplateColumns: cols }}
    >
      <div className="flex min-w-0 items-center gap-1.5 py-1 pr-2" style={{ paddingLeft: depth * 14 + 8 }}>
        <button
          type="button"
          tabIndex={-1}
          data-chevron
          aria-label={open ? "Collapse" : "Expand"}
          className={`flex size-4 shrink-0 items-center justify-center text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)] ${hasKids ? "" : "invisible"}`}
        >
          <ChevronRight size={12} className={`transition-transform ${open ? "rotate-90" : ""}`} />
        </button>
        <KindChip span={span} color={color} />
        <span className="max-w-[45%] shrink-0 truncate font-medium text-[var(--tt-fg)]" title={span.title}>
          {woke && <span style={{ color: colorOf(woke.agent?.agentType) }}>{"↩ "}</span>}
          {span.title}
        </span>
        {span.kind === "agent" && span.agent?.background && <Tag title="The spawning call returned and the subagent kept running">bg</Tag>}
        {resumed && <Tag color={colorOf(resumed.agent?.agentType)}>{`→ ${resumed.agent?.agentType ?? "agent"}`}</Tag>}
        {errs > 0 && span.kind !== "tool" && <Tag color="var(--tt-danger-fg)">{errs} err</Tag>}
        {span.label && (
          <span className="min-w-0 flex-1 truncate text-[var(--tt-fg-dim)]" title={span.label}>
            {span.label}
          </span>
        )}
      </div>
      {real && (
        <div className="px-2 text-right font-mono text-[11px] text-[var(--tt-fg-muted)]" title={span.approxStart ? "Start time is approximate" : undefined}>
          {span.approxStart ? "~" : ""}
          {fmtDur(span.end - span.start)}
        </div>
      )}
      <div className="px-2 text-right font-mono text-[11px] text-[var(--tt-fg-muted)]">{fmtTokens(rollup?.tokens ?? 0)}</div>
      {real && <GanttCell span={span} scale={scale} w0={w0} w1={w1} color={color} />}
    </div>
  );
});

function GanttCell({ span, scale, w0, w1, color }: { span: TraceSpan; scale: TimeScale; w0: number; w1: number; color?: string }) {
  const range = w1 - w0;
  const x = (t: number) => ((scale.u(t) - w0) / range) * 100;
  const a = x(span.start);
  const b = x(Math.max(span.end, span.start + 1));
  const wrap = "relative h-full min-h-6 border-l border-[var(--tt-border)]";
  if (b < 0) return <div className={wrap}><span className="absolute left-1 top-1/2 -translate-y-1/2 font-mono text-[9px] text-[var(--tt-fg-dim)]">{`◂ ${fmtHm(span.start)}`}</span></div>;
  if (a > 100) return <div className={wrap}><span className="absolute right-1 top-1/2 -translate-y-1/2 font-mono text-[9px] text-[var(--tt-fg-dim)]">{`${fmtHm(span.start)} ▸`}</span></div>;

  const l = Math.max(0, a);
  const r = Math.min(100, b);
  const w = `max(2px, ${r - l}%)`;
  const bar = "absolute top-1/2 h-3 -translate-y-1/2 rounded-[3px]";

  if (span.kind === "agent" && !span.error) {
    return (
      <div className={wrap}>
        <div className="absolute top-1/2 h-[2px] -translate-y-1/2 opacity-40" style={{ left: `${l}%`, width: w, background: color }} />
        {agentBursts(span).map(([s0, s1], i) => {
          const x0 = Math.max(0, x(s0));
          const x1 = Math.min(100, x(Math.max(s1, s0 + 1)));
          if (x1 < 0 || x0 > 100) return null;
          return <div key={i} className={bar} style={{ left: `${x0}%`, width: `max(2px, ${x1 - x0}%)`, background: color }} />;
        })}
      </div>
    );
  }

  let bg = "var(--tt-fg-muted)";
  if (span.error) bg = "var(--tt-danger)";
  else if (span.kind === "turn") bg = span.turnKind === "notification" ? "color-mix(in srgb, var(--tt-brand) 35%, transparent)" : "var(--tt-brand)";
  else if (span.kind === "llm") bg = "var(--tt-fg-dim)";
  return (
    <div className={wrap}>
      <div className={bar} style={{ left: `${l}%`, width: w, background: bg }} />
    </div>
  );
}
