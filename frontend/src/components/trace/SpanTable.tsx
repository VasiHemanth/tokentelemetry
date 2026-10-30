"use client";

import { memo, type KeyboardEvent, type RefObject } from "react";
import { ChevronRight, Loader2, RotateCw } from "lucide-react";
import type { TraceSpan } from "@/lib/traceTree/types";
import type { Rollup, Row, TraceIndex } from "@/lib/traceTree/tree";
import { fmtDur, fmtTokens } from "@/lib/traceTree/timeScale";
import { KindChip, Tag, type ColorOf } from "./shared";

export type LoadState = { state: "pending" } | { state: "error"; message: string };

export type TableRow =
  | ({ type: "span" } & Row)
  | { type: "status"; id: string; depth: number; load: LoadState };

const COLS_REAL = "minmax(0,1fr) 88px 72px";
const COLS_ORDER = "minmax(0,1fr) 72px";

interface Props {
  rows: TableRow[];
  index: TraceIndex;
  rollups: Map<string, Rollup>;
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
  const { rows, real, scrollRef, onKeyDown, onToggle, onSelect } = p;
  const cols = real ? COLS_REAL : COLS_ORDER;

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
      className="min-h-0 flex-1 overflow-auto overscroll-contain outline-none focus-visible:ring-1 focus-visible:ring-[var(--tt-border-focus)] scrollbar-thin"
    >
      <div className="min-w-[420px]">
        <div
          className="sticky top-0 z-20 grid items-end border-b border-[var(--tt-border-strong)] bg-[var(--tt-panel)] text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--tt-fg-muted)]"
          style={{ gridTemplateColumns: cols }}
        >
          <div className="px-3 py-1.5">Span</div>
          {real && <div className="px-2 py-1.5 text-right">Dur</div>}
          <div className="px-2 py-1.5 text-right">Tokens</div>
        </div>

        <div className="relative">
          {rows.length === 0 && <div className="px-3 py-6 text-center text-xs text-[var(--tt-fg-muted)]">Nothing matches this filter.</div>}
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
            <Loader2 size={12} className="animate-spin text-[var(--tt-fg-muted)]" />
            <span className="text-[var(--tt-fg-muted)]">Loading subagent trace</span>
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
              className="inline-flex items-center gap-1 rounded border border-[var(--tt-border-strong)] px-1.5 py-0.5 text-[11px] text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)]"
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
  real: boolean;
  cols: string;
  colorOf: ColorOf;
}

const SpanRow = memo(function SpanRow({ span, depth, open, lazy, selected, rollup, index, real, cols, colorOf }: RowProps) {
  const hasKids = span.children.length > 0 || lazy;
  const color = span.kind === "agent" ? colorOf(span.agent?.agentType) : undefined;
  const resumed = span.resumes ? index.agentByChild.get(span.resumes) : undefined;
  const woke = span.kind === "turn" && span.notifiedBy ? index.agentByChild.get(span.notifiedBy) : undefined;
  const errs = rollup?.errs ?? 0;
  const promptText = span.kind === "turn" ? span.content?.input : undefined;
  const label = typeof promptText === "string" && promptText.trim() ? promptText.trim().split("\n", 1)[0].slice(0, 200) : span.label;

  return (
    <div
      role="treeitem"
      aria-level={depth + 1}
      aria-selected={selected}
      aria-expanded={hasKids ? open : undefined}
      data-span-id={span.id}
      className={`relative grid items-center border-b border-[var(--tt-border)]/50 text-[13px] leading-5 [content-visibility:auto] [contain-intrinsic-size:auto_29px] hover:bg-[var(--tt-raised)] ${selected ? "bg-[var(--tt-brand-glow)]" : ""}`}
      style={{ gridTemplateColumns: cols }}
    >
      <div className="flex min-w-0 items-center gap-1.5 py-1 pr-2" style={{ paddingLeft: depth * 14 + 8 }}>
        <button
          type="button"
          tabIndex={-1}
          data-chevron
          aria-label={open ? "Collapse" : "Expand"}
          className={`flex size-4 shrink-0 items-center justify-center text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] ${hasKids ? "" : "invisible"}`}
        >
          <ChevronRight size={12} className={`transition-transform ${open ? "rotate-90" : ""}`} />
        </button>
        <KindChip span={span} color={color} />
        <span className="max-w-[45%] shrink-0 truncate font-medium text-[var(--tt-fg)]" title={span.title}>
          {woke && <span style={{ color: colorOf(woke.agent?.agentType) }}>{"↩ "}</span>}
          {span.title}
        </span>
        {span.kind === "agent" && span.agent?.background && <Tag title="The spawning call returned and the subagent kept running">bg</Tag>}
        {span.kind === "skill" && span.skill?.via === "command" && <Tag title="The user typed this as a slash command">typed</Tag>}
        {resumed && <Tag color={colorOf(resumed.agent?.agentType)}>{`→ ${resumed.agent?.agentType ?? "agent"}`}</Tag>}
        {errs > 0 && span.kind !== "tool" && <Tag color="var(--tt-danger-fg)">{errs} err</Tag>}
        {label && (
          <span className="min-w-0 flex-1 truncate text-[var(--tt-fg-muted)]" title={label}>
            {label}
          </span>
        )}
      </div>
      {real && (
        <div className="whitespace-nowrap px-2 text-right font-mono text-[12px] tabular-nums text-[var(--tt-fg-muted)]" title={span.approxStart ? "Start time is approximate" : undefined}>
          {span.approxStart && <span className="mr-0.5 text-[var(--tt-warn-fg)]">≈</span>}
          {fmtDur(span.end - span.start)}
        </div>
      )}
      <div className="whitespace-nowrap px-2 text-right font-mono text-[12px] tabular-nums text-[var(--tt-fg-muted)]">{fmtTokens(rollup?.tokens ?? 0)}</div>
    </div>
  );
});
