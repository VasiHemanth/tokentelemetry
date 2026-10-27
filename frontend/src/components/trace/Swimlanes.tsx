"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { TraceSpan } from "@/lib/traceTree/types";
import type { TraceIndex } from "@/lib/traceTree/tree";
import { agentBursts } from "@/lib/traceTree/tree";
import { axisMarks, fmtClock, fmtDur, type TimeScale } from "@/lib/traceTree/timeScale";
import { Axis, HATCH, type ColorOf } from "./shared";

const LANE = 20;
const DRAG_MIN = 0.01;

interface Props {
  roots: TraceSpan[];
  index: TraceIndex;
  scale: TimeScale;
  win: [number, number];
  onWin: (w: [number, number]) => void;
  selectedId: string | null;
  onSelect: (id: string) => void;
  colorOf: ColorOf;
}

export default function Swimlanes({ roots, index, scale, win, onWin, selectedId, onSelect, colorOf }: Props) {
  const trackRef = useRef<HTMLDivElement>(null);
  const cursorRef = useRef<HTMLDivElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const brushRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x0: number; moved: boolean; id: string | null } | null>(null);
  const [width, setWidth] = useState(800);

  useEffect(() => {
    const el = trackRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWidth(el.clientWidth));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const marks = useMemo(() => axisMarks(scale, 0, 1, width), [scale, width]);
  const pct = (t: number) => scale.u(t) * 100;
  const mainSpan = roots[0];
  const zoomed = win[0] > 0 || win[1] < 1;

  const fracAt = (clientX: number) => {
    const r = trackRef.current!.getBoundingClientRect();
    return Math.min(1, Math.max(0, (clientX - r.left) / r.width));
  };

  const onDown = (e: React.PointerEvent) => {
    const hit = (e.target as HTMLElement).closest<HTMLElement>("[data-span-id]");
    drag.current = { x0: fracAt(e.clientX), moved: false, id: hit?.dataset.spanId ?? null };
    trackRef.current!.setPointerCapture(e.pointerId);
  };

  const onMove = (e: React.PointerEvent) => {
    const x = fracAt(e.clientX);
    const cur = cursorRef.current;
    const tip = tipRef.current;
    if (cur && tip) {
      cur.style.display = tip.style.display = "block";
      cur.style.left = tip.style.left = `${x * 100}%`;
      tip.textContent = fmtClock(scale.tOf(x));
    }
    const d = drag.current;
    if (!d) return;
    if (Math.abs(x - d.x0) > 0.005) d.moved = true;
    const b = brushRef.current;
    if (d.moved && b) {
      b.style.display = "block";
      b.style.left = `${Math.min(x, d.x0) * 100}%`;
      b.style.width = `${Math.abs(x - d.x0) * 100}%`;
    }
  };

  const onUp = (e: React.PointerEvent) => {
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    const x = fracAt(e.clientX);
    if (d.moved && Math.abs(x - d.x0) > DRAG_MIN) {
      onWin([Math.min(x, d.x0), Math.max(x, d.x0)]);
      // Keep showing the committed window; the persistent brush below takes over.
      if (brushRef.current) brushRef.current.style.display = "none";
    } else if (d.id) {
      onSelect(d.id);
    }
  };

  const onLeave = () => {
    if (cursorRef.current) cursorRef.current.style.display = "none";
    if (tipRef.current) tipRef.current.style.display = "none";
  };

  const barBase = "absolute top-[3px] h-[14px] rounded-[3px] cursor-pointer";
  const ring = (id: string) => (selectedId === id ? " ring-1 ring-[var(--tt-fg)]" : "");

  return (
    <div className="select-none">
      <div className="grid grid-cols-[11rem_minmax(0,1fr)]">
        <div />
        <Axis marks={marks} />
      </div>
      <div className="max-h-64 overflow-y-auto scrollbar-thin">
        <div className="grid grid-cols-[11rem_minmax(0,1fr)]">
          <div className="flex flex-col">
            {mainSpan && (
              <button
                type="button"
                onClick={() => onSelect(mainSpan.id)}
                className="flex h-5 items-center truncate pr-2 text-left text-[11px] font-medium text-[var(--tt-brand)] hover:text-[var(--tt-fg)]"
                style={{ height: LANE }}
              >
                main agent
              </button>
            )}
            {index.agents.map((a) => (
              <button
                key={a.id}
                type="button"
                title={`${a.agent?.agentType ?? a.title}${a.label ? ` · ${a.label}` : ""}`}
                onClick={() => onSelect(a.id)}
                className={`flex items-center gap-1.5 truncate pr-2 text-left text-[11px] hover:text-[var(--tt-fg)] ${selectedId === a.id ? "text-[var(--tt-fg)]" : "text-[var(--tt-fg-muted)]"}`}
                style={{ height: LANE }}
              >
                <span className="size-1.5 shrink-0 rounded-full" style={{ background: colorOf(a.agent?.agentType) }} />
                <span className="truncate">
                  {a.agent?.agentType ?? a.title}
                  {a.label ? ` · ${a.label}` : ""}
                </span>
              </button>
            ))}
          </div>

          <div
            ref={trackRef}
            className="relative cursor-crosshair touch-none border-l border-[var(--tt-border)]"
            style={{ height: LANE * (index.agents.length + 1) }}
            onPointerDown={onDown}
            onPointerMove={onMove}
            onPointerUp={onUp}
            onPointerLeave={onLeave}
            onDoubleClick={() => onWin([0, 1])}
          >
            {scale.pieces.map(
              (p, i) =>
                p.gap && (
                  <div key={i} className="absolute inset-y-0" style={{ ...HATCH, left: `${p.u0 * 100}%`, width: `${(p.u1 - p.u0) * 100}%` }} />
                ),
            )}
            {Array.from({ length: index.agents.length + 1 }, (_, i) => (
              <div key={i} className="absolute inset-x-0 border-b border-[var(--tt-border)]" style={{ top: (i + 1) * LANE - 1 }} />
            ))}

            {roots.map((r) => (
              <div
                key={r.id}
                data-span-id={r.id}
                title={`${r.title} · ${fmtClock(r.start)}`}
                className={`${barBase} ${r.turnKind === "notification" ? "bg-[var(--tt-brand)]/35" : "bg-[var(--tt-brand)]"}${ring(r.id)}`}
                style={{ left: `${pct(r.start)}%`, width: `max(2px, ${pct(r.end) - pct(r.start)}%)` }}
              />
            ))}

            {index.agents.map((a, i) => {
              const c = colorOf(a.agent?.agentType);
              const top = i * LANE + LANE;
              const tip = `${a.agent?.agentType ?? a.title} · ${fmtClock(a.start)} to ${fmtClock(a.end)} (${fmtDur(a.end - a.start)})`;
              const spawnAt = a.agent?.callStart ?? a.start;
              const lineTop = LANE - 3;
              const lineH = top + LANE / 2 - lineTop;
              return (
                <div key={a.id}>
                  <div
                    className="absolute h-[2px] rounded opacity-40"
                    style={{ top: top + LANE / 2 - 1, background: c, left: `${pct(a.start)}%`, width: `${pct(a.end) - pct(a.start)}%` }}
                  />
                  {agentBursts(a).map(([b0, b1], k) => (
                    <div
                      key={k}
                      data-span-id={a.id}
                      title={tip}
                      className={`${barBase}${ring(a.id)}`}
                      style={{ top: top + 3, background: c, left: `${pct(b0)}%`, width: `max(2px, ${pct(b1) - pct(b0)}%)` }}
                    />
                  ))}
                  <div
                    className="pointer-events-none absolute border-l border-dashed border-[var(--tt-fg-dim)]"
                    style={{ left: `${pct(spawnAt)}%`, top: lineTop, height: lineH }}
                  />
                  {(a.agent?.childId ? index.reports.get(a.agent.childId) : undefined)?.map((r) => (
                    <div
                      key={r.id}
                      className="pointer-events-none absolute border-l border-dotted opacity-60"
                      style={{ left: `${pct(r.start)}%`, top: lineTop, height: lineH, borderColor: c }}
                    />
                  ))}
                </div>
              );
            })}

            {zoomed && (
              <div
                className="pointer-events-none absolute inset-y-0 border-x border-[var(--tt-brand)] bg-[var(--tt-brand-glow)]"
                style={{ left: `${win[0] * 100}%`, width: `${(win[1] - win[0]) * 100}%` }}
              />
            )}
            <div ref={brushRef} className="pointer-events-none absolute inset-y-0 hidden border-x border-[var(--tt-brand)] bg-[var(--tt-brand-glow)]" />
            <div ref={cursorRef} className="pointer-events-none absolute inset-y-0 hidden w-px bg-[var(--tt-fg-muted)]/60" />
            <div
              ref={tipRef}
              className="pointer-events-none absolute top-0.5 z-10 hidden translate-x-1 rounded bg-[var(--tt-overlay)] px-1.5 font-mono text-[10px] leading-4 text-[var(--tt-fg)] shadow"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
