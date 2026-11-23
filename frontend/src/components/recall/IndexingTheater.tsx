"use client";

import { useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { AgentBadge } from "@/components/ui";
import { getAgent } from "@/lib/agents";
import {
  RECALL_DOC_TYPES, fetchRecallMap, streamIndexEvents,
  type IndexDocEvent, type IndexDoneEvent, type IndexErrorEvent, type IndexProgress, type IndexStartEvent,
} from "@/lib/recall";
import { DocTypeIcon, docTypeMeta } from "./docTypes";
import { TheaterEngine, type MapPoint } from "./indexingEngine";

// Live view of one index run, drawn from the real /recall/index/events stream.
// Counters come from `progress` events and are exact; the cards and chips are
// sampled to about 8 per second so a fast run stays readable.

const CARD_MIN_GAP_MS = 125;
const CARD_LIFE_MS = 1500;
const SLOTS = 3;
const MAX_QUIET_RETRIES = 5;

interface Card { key: number; type: string; agent: string; title: string; slot: number }

const KEYFRAMES = `
@keyframes tt-recall-card {
  0% { transform: translateX(-24px); opacity: 0; }
  20% { transform: translateX(0); opacity: 1; }
  70% { transform: translateX(0); opacity: 1; }
  100% { transform: translateX(14px) scale(.9); opacity: 0; }
}`;

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const t = window.setTimeout(resolve, ms);
    signal.addEventListener("abort", () => { window.clearTimeout(t); resolve(); }, { once: true });
  });
}

function fmt(n: number | undefined): string {
  return (n ?? 0).toLocaleString();
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-sunken)] px-3 py-2 min-w-0">
      <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--tt-fg-dim)]">{label}</div>
      <div className="tabular text-[17px] font-semibold text-[var(--tt-fg)] truncate">{value}</div>
    </div>
  );
}

export function IndexingTheater({ project, enabled, images, runId, onFinished }: {
  project: string; enabled: boolean; images: boolean;
  runId: string | null;
  onFinished?: (ok: boolean) => void;
}) {
  const stageRef = useRef<HTMLCanvasElement>(null);
  const mapRef = useRef<HTMLCanvasElement>(null);
  const engineRef = useRef<TheaterEngine | null>(null);
  const reducedRef = useRef(false);
  const lastCardAt = useRef(0);
  const finishedCb = useRef(onFinished);
  useEffect(() => { finishedCb.current = onFinished; }, [onFinished]);

  const [phase, setPhase] = useState<"idle" | "running" | "done" | "error">("idle");
  const [reconnecting, setReconnecting] = useState(false);
  const [start, setStart] = useState<IndexStartEvent | null>(null);
  const [progress, setProgress] = useState<IndexProgress | null>(null);
  const [done, setDone] = useState<IndexDoneEvent | null>(null);
  const [failure, setFailure] = useState<{ message: string; fix?: string } | null>(null);
  const [cards, setCards] = useState<Card[]>([]);
  const [reduced, setReduced] = useState(false);
  const [tip, setTip] = useState<{ left: number; top: number; p: MapPoint } | null>(null);
  const [mapCount, setMapCount] = useState(0);

  // Canvas engine lifetime and reduced-motion preference.
  useEffect(() => {
    const stage = stageRef.current, map = mapRef.current;
    if (!stage || !map) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    reducedRef.current = mq.matches;
    setReduced(mq.matches);
    const engine = new TheaterEngine();
    engineRef.current = engine;
    engine.attach(stage, map, mq.matches);
    const onMq = () => { reducedRef.current = mq.matches; setReduced(mq.matches); engine.setReduced(mq.matches); };
    mq.addEventListener("change", onMq);
    const ro = new ResizeObserver(() => engine.resize());
    ro.observe(stage);
    ro.observe(map);
    const mo = new MutationObserver(() => engine.kick(true));
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme"] });
    return () => {
      mq.removeEventListener("change", onMq);
      ro.disconnect();
      mo.disconnect();
      engine.destroy();
      engineRef.current = null;
    };
  }, []);

  // One stream per runId. Reconnects with the last seq so a drop loses nothing.
  useEffect(() => {
    if (!runId) return;
    const engine = engineRef.current;
    if (!engine) return;
    const ctl = new AbortController();
    const timers = new Set<number>();
    engine.reset();
    setPhase("running"); setStart(null); setProgress(null); setDone(null); setFailure(null);
    setCards([]); setReconnecting(false); setMapCount(0);
    lastCardAt.current = 0;
    let lastSeq = 0;
    let finished = false;
    let quiet = 0;

    const showCard = (ev: IndexDocEvent) => {
      if (images || ev.doc_type !== "image") engine.noteDoc(ev);
      if (reducedRef.current) return;
      const now = performance.now();
      if (now - lastCardAt.current < CARD_MIN_GAP_MS) return;
      lastCardAt.current = now;
      const slot = ev.seq % SLOTS;
      const card: Card = { key: ev.seq, type: ev.doc_type, agent: ev.agent, title: ev.title, slot };
      setCards((cs) => [...cs.filter((c) => c.slot !== slot), card]);
      engine.spawnChips(ev, (slot * 2 + 1) / (SLOTS * 2));
      const t = window.setTimeout(() => {
        timers.delete(t);
        setCards((cs) => cs.filter((c) => c.key !== card.key));
      }, CARD_LIFE_MS);
      timers.add(t);
    };

    const finish = (ok: boolean) => {
      finished = true;
      setMapCount(engine.points.length);
      finishedCb.current?.(ok);
    };

    void (async () => {
      while (!ctl.signal.aborted && !finished) {
        let got = false;
        try {
          for await (const ev of streamIndexEvents(runId, lastSeq, ctl.signal)) {
            if (ctl.signal.aborted) return;
            got = true;
            setReconnecting(false);
            const terminal = ev.type === "done" || ev.type === "error";
            if (!terminal && ev.seq <= lastSeq) continue;
            lastSeq = Math.max(lastSeq, ev.seq);
            switch (ev.type) {
              case "start": setStart(ev); break;
              case "doc": showCard(ev); break;
              case "vector": engine.addVector(ev); break;
              case "progress": setProgress(ev); setMapCount(engine.points.length); break;
              case "done": setDone(ev); setPhase("done"); finish(true); break;
              case "error": setFailure(ev as IndexErrorEvent); setPhase("error"); finish(false); break;
            }
            if (finished) break;
          }
        } catch {
          if (ctl.signal.aborted) return;
        }
        if (finished || ctl.signal.aborted) break;
        quiet = got ? 0 : quiet + 1;
        if (quiet > MAX_QUIET_RETRIES) {
          setFailure({ message: "Lost the connection to the index run.", fix: "Reload the page to reattach, or start the run again." });
          setPhase("error");
          finish(false);
          break;
        }
        setReconnecting(true);
        await sleep(got ? 300 : 1000, ctl.signal);
      }
    })();

    return () => {
      ctl.abort();
      timers.forEach((t) => window.clearTimeout(t));
    };
  }, [runId, images]);

  useEffect(() => {
    if (!enabled || (runId && phase !== "done")) return;
    const ctl = new AbortController();
    void fetchRecallMap(project, ctl.signal).then(({ points }) => {
      if (ctl.signal.aborted || !engineRef.current) return;
      engineRef.current.setMap(points);
      setMapCount(engineRef.current.points.length);
      setTip(null);
    }).catch(() => { /* retain the map from the live stream */ });
    return () => ctl.abort();
  }, [enabled, images, phase, project, runId]);

  const onMapMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const engine = engineRef.current;
    if (!engine) return;
    const r = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - r.left, y = e.clientY - r.top;
    const p = engine.hitTest(x, y);
    engine.setHover(p);
    setTip(p ? { left: Math.max(4, Math.min(x + 12, r.width - 200)), top: Math.max(4, y - 36), p } : null);
  };
  const onMapLeave = () => { engineRef.current?.setHover(null); setTip(null); };

  const total = start?.totals.documents ?? 0;
  const docsDone = progress?.documents_done ?? 0;
  const pct = total > 0 ? Math.min(100, Math.round((docsDone / total) * 100)) : 0;
  const byType = RECALL_DOC_TYPES.filter((t) => (progress?.by_type?.[t] ?? 0) > 0 || (start?.totals.by_type?.[t] ?? 0) > 0);
  const byAgent = Object.entries(progress?.by_agent ?? {}).sort((a, b) => b[1] - a[1]);
  const saved = phase === "idle" && enabled && mapCount > 0;
  const visible = phase !== "idle" || saved;

  return (
    <section
      aria-label="Indexing"
      aria-busy={phase === "running"}
      className={visible ? "rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] p-4 space-y-4" : "hidden"}
    >
      <style>{KEYFRAMES}</style>

      <div className="flex flex-wrap items-center gap-3">
        {phase === "running" && <Loader2 size={14} className="animate-spin text-[var(--tt-brand)]" />}
        {phase === "done" && <CheckCircle2 size={14} className="text-[var(--tt-success-fg)]" />}
        {phase === "error" && <AlertTriangle size={14} className="text-[var(--tt-danger-fg)]" />}
        <h3 className="text-[13px] font-semibold text-[var(--tt-fg)]">
          {phase === "done" || saved ? "Project knowledge map" : phase === "error" ? "Indexing stopped" : `Indexing${start?.project?.name ? ` ${start.project.name}` : ""}`}
        </h3>
        {reconnecting && phase === "running" && (
          <span className="text-[11px] text-[var(--tt-warn-fg)]" role="status">Reconnecting</span>
        )}
        <span className="ml-auto text-[11px] text-[var(--tt-fg-dim)] tabular">
          {total > 0 ? `${fmt(docsDone)} of ${fmt(total)} documents` : ""}
        </span>
      </div>

      {total > 0 && phase === "running" && (
        <div className="h-1 rounded-full tt-tint-2 overflow-hidden" aria-hidden>
          <div className="h-full bg-[var(--tt-brand)] transition-all" style={{ width: `${pct}%` }} />
        </div>
      )}

      {!saved && <div className="grid gap-2 grid-cols-2 sm:grid-cols-5">
        <Stat label="Documents" value={fmt(docsDone)} />
        <Stat label="Chunks embedded" value={fmt(progress?.chunks_embedded)} />
        <Stat label="Chunks reused" value={fmt(progress?.chunks_reused)} />
        <Stat label="Estimated tokens" value={fmt(progress?.tokens)} />
        <Stat label="Chunks / s" value={(progress?.per_sec ?? 0).toFixed(1)} />
      </div>}

      {(byType.length > 0 || byAgent.length > 0) && (
        <div className="space-y-2">
          {byType.length > 0 && (
            <ul className="flex flex-wrap gap-x-4 gap-y-1.5 text-[12px] text-[var(--tt-fg-muted)]" aria-label="Documents by type">
              {byType.map((t) => (
                <li key={t} className="inline-flex items-center gap-1.5 tabular">
                  <DocTypeIcon type={t} size={12} />
                  {docTypeMeta(t).plural} {fmt(progress?.by_type?.[t] ?? 0)}
                  {start?.totals.by_type?.[t] ? <span className="text-[var(--tt-fg-dim)]">/ {fmt(start.totals.by_type[t])}</span> : null}
                </li>
              ))}
            </ul>
          )}
          {byAgent.length > 0 && (
            <ul className="flex flex-wrap gap-2" aria-label="Documents by agent">
              {byAgent.map(([a, n]) => (
                <li key={a} className="inline-flex items-center gap-1.5 tabular text-[11px] text-[var(--tt-fg-dim)]">
                  <AgentBadge agent={a} size="xs" /> {fmt(n)}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div
          className={reduced || saved ? "hidden" : "relative h-[132px] overflow-hidden rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-sunken)]"}
          aria-hidden
        >
          <canvas ref={stageRef} className="absolute inset-0 h-full w-full" />
          {cards.map((c) => (
            <div
              key={c.key}
              className="absolute left-2 w-[44%] max-w-[260px] flex items-center gap-2 rounded-[var(--tt-radius)] border border-[var(--tt-border-strong)] bg-[var(--tt-panel)] px-2 py-1.5 shadow-sm"
              style={{
                top: `calc(${((c.slot * 2 + 1) / (SLOTS * 2)) * 100}% - 18px)`,
                height: 36,
                animation: `tt-recall-card ${CARD_LIFE_MS}ms ease-out both`,
              }}
            >
              <DocTypeIcon type={c.type} size={14} />
              <span className="min-w-0 flex-1 truncate text-[11.5px] text-[var(--tt-fg)]" title={c.title}>{c.title || "(untitled)"}</span>
              <span className="shrink-0 text-[9px] font-semibold uppercase tracking-wide" style={{ color: getAgent(c.agent).hex }}>
                {getAgent(c.agent).label.split(" ")[0]}
              </span>
            </div>
          ))}
          {phase === "running" && cards.length === 0 && (
            <div className="absolute inset-0 grid place-items-center text-[11px] text-[var(--tt-fg-dim)]">Waiting for documents</div>
          )}
        </div>

        <div className={reduced || saved ? "relative h-[260px] lg:col-span-2" : "relative h-[260px]"}>
          <canvas
            ref={mapRef}
            role="img"
            aria-label={`Project knowledge map, ${mapCount} documents plotted. Hover a dot for its title.`}
            className="h-full w-full rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-sunken)]"
            onMouseMove={onMapMove}
            onMouseLeave={onMapLeave}
          />
          {tip && (
            <div
              className="pointer-events-none absolute z-10 max-w-[260px] rounded-[var(--tt-radius)] border border-[var(--tt-border-strong)] bg-[var(--tt-overlay)] px-2.5 py-1.5 text-[11.5px] text-[var(--tt-fg)] shadow-md"
              style={{ left: tip.left, top: tip.top }}
            >
              <div className="flex items-center gap-1.5">
                <DocTypeIcon type={tip.p.type} size={12} />
                <span className="truncate">{tip.p.title || tip.p.docId}</span>
              </div>
              {tip.p.agent && <div className="text-[10px] text-[var(--tt-fg-dim)]">{getAgent(tip.p.agent).label}</div>}
            </div>
          )}
        </div>
      </div>

      {phase === "done" && done && (
        <p className="text-[12px] text-[var(--tt-fg-muted)] tabular" role="status">
          Done in {done.elapsed_s.toFixed(1)} s: {fmt(progress?.documents_done)} documents,{" "}
          {fmt(progress?.chunks_embedded)} chunks embedded, {fmt(progress?.chunks_reused)} reused,{" "}
          {fmt(progress?.tokens)} tokens. Hover a dot on the map to see which document it is.
        </p>
      )}
      {phase === "error" && failure && (
        <p className="text-[12px] text-[var(--tt-danger-fg)]" role="alert">
          {failure.message}{failure.fix ? ` ${failure.fix}` : ""}
        </p>
      )}
    </section>
  );
}
