"use client";

/* Obsidian-style force-directed graph of the project wiki.
 *
 * d3-force owns the physics; React owns the DOM. Positions stream into React
 * state via requestAnimationFrame while the simulation is warm, so hover /
 * filter / selection stay declarative. Wiki graphs are small (tens to a few
 * hundred nodes), which keeps this comfortably within budget; beyond 300
 * nodes the simulation is pre-run and rendered settled.
 */

import {
  forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY,
  type Simulation, type SimulationNodeDatum,
} from "d3-force";
import {
  Boxes, ChevronDown, Focus, Maximize2, Minus, Plus, Search, SlidersHorizontal, X,
} from "lucide-react";
import {
  useCallback, useEffect, useMemo, useRef, useState,
} from "react";

import { cn } from "@/lib/cn";

import { buildTypePalette, typeSlot, GRAY } from "./palette";
import type { GraphCluster, GraphEdge, GraphNode } from "./types";

/* ------------------------------------------------------------------ types */

interface SimNode extends SimulationNodeDatum {
  ref: GraphNode;
  id: string;
  r: number;
}

interface SimEdge {
  source: SimNode;
  target: SimNode;
  kind: "link" | "index";
}

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  clusters: GraphCluster[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  height?: number;
}

interface Controls {
  repel: number;       // many-body strength (positive slider, applied negative)
  linkDist: number;
  nodeScale: number;
  labelZoom: number;   // zoom level at which labels fully appear
  showHulls: boolean;
  showOrphans: boolean;
  focusDepth: 0 | 1 | 2; // 0 = whole graph
}

const DEFAULTS: Controls = {
  repel: 300, linkDist: 90, nodeScale: 1, labelZoom: 1.25,
  showHulls: true, showOrphans: true, focusDepth: 0,
};

/* ------------------------------------------------------------- component */

export default function BrainGraph({ nodes, edges, clusters, selectedId, onSelect, height = 640 }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const simRef = useRef<Simulation<SimNode, SimEdge> | null>(null);
  const posCache = useRef<Map<string, { x: number; y: number }>>(new Map());
  const [tick, setTick] = useState(0); // bumped per animation frame while warm
  const [transform, setTransform] = useState({ x: 0, y: 0, k: 1 });
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(new Set());
  const [ctl, setCtl] = useState<Controls>(DEFAULTS);
  const [panelOpen, setPanelOpen] = useState(false);
  const [dark, setDark] = useState(true);
  const [size, setSize] = useState({ w: 1200, h: height });

  /* theme: node fills are literal hex per mode (validated palette) */
  useEffect(() => {
    const el = document.documentElement;
    const read = () => setDark(el.getAttribute("data-theme") !== "light");
    read();
    const obs = new MutationObserver(read);
    obs.observe(el, { attributes: true, attributeFilter: ["data-theme"] });
    return () => obs.disconnect();
  }, []);

  /* container size */
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0]?.contentRect;
      if (r) setSize({ w: r.width, h: r.height });
    });
    ro.observe(svg);
    return () => ro.disconnect();
  }, []);

  const palette = useMemo(
    () => buildTypePalette(nodes.map((n) => n.type ?? "")),
    [nodes],
  );
  const fillOf = useCallback(
    (n: GraphNode) => (dark ? typeSlot(palette, n.type).dark : typeSlot(palette, n.type).light),
    [palette, dark],
  );

  /* ---------------------------------------------------------- filtering */

  const adjacency = useMemo(() => {
    const adj = new Map<string, Set<string>>();
    for (const n of nodes) adj.set(n.id, new Set());
    for (const e of edges) {
      adj.get(e.source)?.add(e.target);
      adj.get(e.target)?.add(e.source);
    }
    return adj;
  }, [nodes, edges]);

  const visibleIds = useMemo(() => {
    let ids = new Set(nodes.map((n) => n.id));
    if (!ctl.showOrphans) {
      // degree comes from the backend and excludes index-hub links, so a page
      // only the index lists still counts as an orphan.
      const degreeById = new Map(nodes.map((n) => [n.id, n.degree]));
      ids = new Set([...ids].filter((id) => id === "index" || (degreeById.get(id) ?? 0) > 0));
    }
    if (hiddenTypes.size > 0) {
      const byId = new Map(nodes.map((n) => [n.id, n]));
      ids = new Set([...ids].filter((id) => !hiddenTypes.has((byId.get(id)?.type ?? "untyped").toLowerCase())));
    }
    const q = search.trim().toLowerCase();
    if (q) {
      const byId = new Map(nodes.map((n) => [n.id, n]));
      ids = new Set([...ids].filter((id) => {
        const n = byId.get(id)!;
        return n.title.toLowerCase().includes(q) || n.id.toLowerCase().includes(q)
          || (n.tags ?? []).some((t) => String(t).toLowerCase().includes(q));
      }));
    }
    if (ctl.focusDepth > 0 && selectedId && ids.has(selectedId)) {
      const keep = new Set<string>([selectedId]);
      let frontier = [selectedId];
      for (let d = 0; d < ctl.focusDepth; d++) {
        const next: string[] = [];
        for (const id of frontier) {
          for (const nb of adjacency.get(id) ?? []) {
            if (!keep.has(nb) && ids.has(nb)) { keep.add(nb); next.push(nb); }
          }
        }
        frontier = next;
      }
      ids = keep;
    }
    return ids;
  }, [nodes, adjacency, ctl.showOrphans, ctl.focusDepth, hiddenTypes, search, selectedId]);

  /* ------------------------------------------------------- simulation */

  const simData = useMemo(() => {
    const visNodes: SimNode[] = nodes
      .filter((n) => visibleIds.has(n.id))
      .map((n) => {
        const cached = posCache.current.get(n.id);
        return {
          ref: n,
          id: n.id,
          r: (n.id === "index" ? 12 : 5 + Math.sqrt(n.degree) * 2.4) * ctl.nodeScale,
          x: cached?.x, y: cached?.y,
        } as SimNode;
      });
    const byId = new Map(visNodes.map((n) => [n.id, n]));
    const visEdges: SimEdge[] = edges
      .filter((e) => byId.has(e.source) && byId.has(e.target))
      .map((e) => ({ source: byId.get(e.source)!, target: byId.get(e.target)!, kind: e.kind ?? "link" }));
    return { visNodes, visEdges };
  }, [nodes, edges, visibleIds, ctl.nodeScale]);

  useEffect(() => {
    const { visNodes, visEdges } = simData;
    if (visNodes.length === 0) return;

    // Cluster anchors on a ring: gives each community its own region so the
    // hulls separate instead of interleaving. The index hub (cluster -1)
    // anchors to the center: the glue that holds the map together.
    const clusterIdxs = [...new Set(visNodes.map((n) => n.ref.cluster))]
      .filter((c) => c >= 0).sort((a, b) => a - b);
    const ring = Math.min(size.w, size.h) * 0.42 * (clusterIdxs.length > 1 ? 1 : 0);
    const anchor = new Map<number, { x: number; y: number }>();
    anchor.set(-1, { x: 0, y: 0 });
    clusterIdxs.forEach((c, i) => {
      const a = (2 * Math.PI * i) / clusterIdxs.length - Math.PI / 2;
      anchor.set(c, { x: Math.cos(a) * ring, y: Math.sin(a) * ring });
    });

    const sim = forceSimulation<SimNode>(visNodes)
      .force("link", forceLink<SimNode, SimEdge>(visEdges)
        .distance((l) => (l.kind === "index" ? ctl.linkDist * 1.9 : ctl.linkDist))
        .strength((l) => (l.kind === "index" ? 0.02 : 0.35)))
      .force("charge", forceManyBody().strength(-ctl.repel))
      .force("center", forceCenter(0, 0).strength(0.04))
      .force("collide", forceCollide<SimNode>().radius((d) => d.r + 6))
      .force("cx", forceX<SimNode>((d) => anchor.get(d.ref.cluster)?.x ?? 0)
        .strength((d) => (d.ref.cluster === -1 ? 0.4 : 0.11)))
      .force("cy", forceY<SimNode>((d) => anchor.get(d.ref.cluster)?.y ?? 0)
        .strength((d) => (d.ref.cluster === -1 ? 0.4 : 0.11)));
    simRef.current = sim;
    sim.stop();

    // Pre-run most of the cooling synchronously (a few ms at wiki scale):
    // the graph paints nearly settled and only a short organic drift remains.
    // Also avoids minutes of slow-motion settling in throttled background tabs.
    const preTicks = visNodes.length > 300 ? 300 : 140;
    for (let i = 0; i < preTicks; i++) sim.tick();
    for (const n of visNodes) posCache.current.set(n.id, { x: n.x!, y: n.y! });
    setTick((t) => t + 1);
    if (visNodes.length > 300) {
      return () => { sim.stop(); simRef.current = null; };
    }

    let raf = 0;
    const frame = () => {
      sim.tick();
      for (const n of visNodes) posCache.current.set(n.id, { x: n.x!, y: n.y! });
      setTick((t) => t + 1);
      if (sim.alpha() > 0.02) raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(raf); sim.stop(); simRef.current = null; };
  }, [simData, ctl.linkDist, ctl.repel, size.w, size.h]);

  /* --------------------------------------------------- pan / zoom / drag */

  const dragState = useRef<{ mode: "pan" | "node"; id?: string; sx: number; sy: number; ox: number; oy: number; moved: boolean } | null>(null);

  const toGraph = useCallback((clientX: number, clientY: number) => {
    const rect = svgRef.current!.getBoundingClientRect();
    return {
      x: (clientX - rect.left - rect.width / 2 - transform.x) / transform.k,
      y: (clientY - rect.top - rect.height / 2 - transform.y) / transform.k,
    };
  }, [transform]);

  const zoomAt = useCallback((px: number, py: number, factor: number) => {
    setTransform((t) => {
      const k = Math.min(4, Math.max(0.2, t.k * factor));
      return { k, x: px - ((px - t.x) / t.k) * k, y: py - ((py - t.y) / t.k) * k };
    });
  }, []);

  // Wheel/pinch must be a NATIVE non-passive listener: React attaches wheel
  // handlers passively, so preventDefault() is ignored there and a trackpad
  // pinch zooms the whole browser tab instead of the graph.
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheelNative = (e: WheelEvent) => {
      e.preventDefault();
      const rect = svg.getBoundingClientRect();
      const px = e.clientX - rect.left - rect.width / 2;
      const py = e.clientY - rect.top - rect.height / 2;
      // ctrlKey marks a pinch gesture; its deltas are small, so scale harder.
      const factor = Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0016));
      zoomAt(px, py, factor);
    };
    svg.addEventListener("wheel", onWheelNative, { passive: false });
    return () => svg.removeEventListener("wheel", onWheelNative);
  }, [zoomAt]);

  const onPointerDown = useCallback((e: React.PointerEvent, nodeId?: string) => {
    (e.target as Element).setPointerCapture?.(e.pointerId);
    if (nodeId) {
      const n = simData.visNodes.find((x) => x.id === nodeId);
      if (!n) return;
      dragState.current = { mode: "node", id: nodeId, sx: e.clientX, sy: e.clientY, ox: n.x!, oy: n.y!, moved: false };
    } else {
      dragState.current = { mode: "pan", sx: e.clientX, sy: e.clientY, ox: transform.x, oy: transform.y, moved: false };
    }
    e.stopPropagation();
  }, [simData, toGraph, transform]);

  /* restart raf while dragging a node so physics feels alive */
  const kickRef = useRef(0);
  const kickSim = useCallback(() => {
    cancelAnimationFrame(kickRef.current);
    const step = () => {
      const sim = simRef.current;
      if (!sim) return;
      sim.tick();
      for (const n of simData.visNodes) posCache.current.set(n.id, { x: n.x!, y: n.y! });
      setTick((t) => t + 1);
      if (sim.alpha() > 0.02 || dragState.current?.mode === "node") kickRef.current = requestAnimationFrame(step);
    };
    kickRef.current = requestAnimationFrame(step);
  }, [simData]);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    const d = dragState.current;
    if (!d) return;
    const dist = Math.hypot(e.clientX - d.sx, e.clientY - d.sy);
    if (!d.moved && dist < 4) return; // click, not drag (yet)
    if (!d.moved) {
      d.moved = true;
      if (d.mode === "node") kickSim(); // wake physics only once dragging is real
    }
    if (d.mode === "pan") {
      setTransform((t) => ({ ...t, x: d.ox + (e.clientX - d.sx), y: d.oy + (e.clientY - d.sy) }));
    } else if (d.id) {
      const n = simData.visNodes.find((x) => x.id === d.id);
      if (n) {
        const p = toGraph(e.clientX, e.clientY);
        n.fx = p.x; n.fy = p.y;
        simRef.current?.alpha(Math.max(simRef.current.alpha(), 0.3));
      }
    }
  }, [simData, toGraph]);

  const onPointerUp = useCallback(() => {
    const d = dragState.current;
    dragState.current = null;
    if (!d) return;
    if (d.mode === "node" && d.id) {
      if (!d.moved) {
        onSelect(d.id); // a stationary press is a click: open the page
      } else {
        const n = simData.visNodes.find((x) => x.id === d.id);
        if (n) { n.fx = null; n.fy = null; }
        simRef.current?.alphaTarget(0);
      }
    } else if (d.mode === "pan" && !d.moved) {
      onSelect(null); // background click clears selection
    }
  }, [simData, onSelect]);

  /* center the view on a node (drawer navigation) */
  useEffect(() => {
    if (!selectedId) return;
    const p = posCache.current.get(selectedId);
    if (p) setTransform((t) => ({ ...t, x: -p.x * t.k, y: -p.y * t.k }));
  }, [selectedId]);

  /* -------------------------------------------------------- hulls */

  const hulls = useMemo(() => {
    if (!ctl.showHulls) return [];
    void tick;
    const byCluster = new Map<number, SimNode[]>();
    for (const n of simData.visNodes) {
      if (n.x == null) continue;
      const arr = byCluster.get(n.ref.cluster) ?? [];
      arr.push(n);
      byCluster.set(n.ref.cluster, arr);
    }
    const out: { cluster: GraphCluster; path: string; labelX: number; labelY: number; color: string }[] = [];
    for (const [cid, members] of byCluster) {
      if (members.length < 2) continue;
      const cluster = clusters.find((c) => c.id === cid);
      if (!cluster) continue;
      const pts = members.map((m) => [m.x!, m.y!] as [number, number]);
      const hull = convexHull(pts);
      const padded = padHull(hull, 30);
      // dominant type color tints the hull
      const typeCount = new Map<string, number>();
      for (const m of members) {
        const t = (m.ref.type ?? "untyped").toLowerCase();
        typeCount.set(t, (typeCount.get(t) ?? 0) + 1);
      }
      const domType = [...typeCount.entries()].sort((a, b) => b[1] - a[1])[0][0];
      const slot = domType === "untyped" ? GRAY : typeSlot(palette, domType);
      const topmost = padded.reduce((a, b) => (b[1] < a[1] ? b : a));
      out.push({
        cluster,
        path: smoothClosedPath(padded),
        labelX: topmost[0],
        labelY: topmost[1] - 10,
        color: dark ? slot.dark : slot.light,
      });
    }
    return out;
  }, [ctl.showHulls, simData, clusters, palette, dark, tick]);

  /* -------------------------------------------------------- highlight */

  const activeId = hoveredId ?? selectedId;
  const neighborSet = useMemo(() => {
    if (!activeId) return null;
    const s = new Set<string>([activeId]);
    for (const nb of adjacency.get(activeId) ?? []) s.add(nb);
    return s;
  }, [activeId, adjacency]);

  const labelOpacity = Math.max(0, Math.min(1, (transform.k - ctl.labelZoom + 0.35) / 0.35));
  const hovered = hoveredId ? simData.visNodes.find((n) => n.id === hoveredId) : null;

  const typeEntries = useMemo(() => {
    const counts = new Map<string, number>();
    for (const n of nodes) {
      const t = (n.type ?? "untyped").toLowerCase();
      counts.set(t, (counts.get(t) ?? 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [nodes]);

  void tick; // positions live in posCache; tick re-renders

  /* ---------------------------------------------------------- render */

  return (
    <div className="relative rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] overflow-hidden bg-[var(--tt-panel)]" style={{ height }}>
      {/* dot-grid backdrop, Obsidian-style */}
      <div
        aria-hidden
        className="absolute inset-0 pointer-events-none opacity-60"
        style={{
          backgroundImage: "radial-gradient(color-mix(in oklab, var(--tt-fg) 7%, transparent) 1px, transparent 1px)",
          backgroundSize: `${24 * transform.k}px ${24 * transform.k}px`,
          backgroundPosition: `${transform.x + size.w / 2}px ${transform.y + size.h / 2}px`,
        }}
      />

      <svg
        ref={svgRef}
        className="w-full h-full cursor-grab active:cursor-grabbing select-none touch-none"
        onPointerDown={(e) => onPointerDown(e)}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={onPointerUp}
        role="img"
        aria-label={`Wiki graph: ${simData.visNodes.length} pages, ${simData.visEdges.length} links`}
      >
        <g transform={`translate(${size.w / 2 + transform.x} ${size.h / 2 + transform.y}) scale(${transform.k})`}>
          {/* cluster hulls */}
          {hulls.map((h) => (
            <g key={h.cluster.id} className="transition-opacity duration-200" opacity={neighborSet ? 0.5 : 1}>
              <path d={h.path} fill={h.color} fillOpacity={0.055} stroke={h.color} strokeOpacity={0.16} strokeWidth={1.2} />
              <text
                x={h.labelX} y={h.labelY}
                fontSize={11 / Math.sqrt(transform.k)}
                fill={h.color} fillOpacity={0.75}
                fontWeight={600} letterSpacing="0.08em"
                style={{ textTransform: "uppercase" }}
              >
                {h.cluster.label}
              </text>
            </g>
          ))}

          {/* edges */}
          {simData.visEdges.map((e, i) => {
            const sp = posCache.current.get(e.source.id);
            const tp = posCache.current.get(e.target.id);
            if (!sp || !tp) return null;
            const lit = neighborSet && activeId != null
              && (e.source.id === activeId || e.target.id === activeId);
            const dim = neighborSet && !lit;
            const isHubTie = e.kind === "index";
            return (
              <line
                key={i}
                x1={sp.x} y1={sp.y} x2={tp.x} y2={tp.y}
                stroke={lit ? "var(--tt-brand)" : "var(--tt-fg)"}
                strokeOpacity={lit ? 0.6 : dim ? 0.03 : isHubTie ? 0.05 : 0.13}
                strokeWidth={(lit ? 1.8 : isHubTie ? 0.9 : 1.1) / transform.k}
                strokeDasharray={isHubTie ? `${3 / transform.k} ${4 / transform.k}` : undefined}
                className="transition-[stroke-opacity] duration-150"
              />
            );
          })}

          {/* nodes */}
          {simData.visNodes.map((n) => {
            const p = posCache.current.get(n.id);
            if (!p) return null;
            const isActive = n.id === activeId;
            const isNeighbor = neighborSet?.has(n.id) ?? false;
            const dim = neighborSet ? !isNeighbor : false;
            const isSelected = n.id === selectedId;
            const isHub = n.id === "index";
            const showLabel = isActive || isSelected || isNeighbor || isHub || labelOpacity > 0.05;
            const thisLabelOpacity = isActive || isSelected || isNeighbor || isHub ? 1 : labelOpacity;
            return (
              <g
                key={n.id}
                transform={`translate(${p.x} ${p.y})`}
                className="cursor-pointer transition-opacity duration-150"
                opacity={dim ? 0.15 : 1}
                onPointerDown={(e) => onPointerDown(e, n.id)}
                onPointerEnter={() => setHoveredId(n.id)}
                onPointerLeave={() => setHoveredId(null)}
              >
                {isSelected && (
                  <circle r={n.r + 5 / transform.k} fill="none" stroke="var(--tt-brand)" strokeWidth={1.5 / transform.k} strokeOpacity={0.8} strokeDasharray={`${4 / transform.k} ${3 / transform.k}`} />
                )}
                {isHub && !isSelected && (
                  <circle r={n.r + 4 / transform.k} fill="none" stroke={fillOf(n.ref)} strokeWidth={1.2 / transform.k} strokeOpacity={0.45} />
                )}
                <circle
                  r={n.r}
                  fill={fillOf(n.ref)}
                  stroke="var(--tt-panel)"
                  strokeWidth={2}
                  style={isActive ? { filter: `drop-shadow(0 0 ${8 / transform.k}px ${fillOf(n.ref)})` } : undefined}
                />
                {showLabel && (
                  <text
                    y={n.r + 12 / transform.k}
                    textAnchor="middle"
                    fontSize={11 / transform.k}
                    fill="var(--tt-fg-muted)"
                    opacity={thisLabelOpacity}
                    style={{ paintOrder: "stroke", stroke: "var(--tt-panel)", strokeWidth: 3 / transform.k, strokeLinejoin: "round" }}
                  >
                    {n.ref.title}
                  </text>
                )}
              </g>
            );
          })}
        </g>
      </svg>

      {/* hover tooltip */}
      {hovered && hovered.ref.description && (
        <div
          className="absolute z-10 max-w-[300px] px-3 py-2 rounded-[var(--tt-radius)] bg-[var(--tt-overlay)] border border-[var(--tt-border-strong)] shadow-[var(--tt-shadow-pop)] text-[11px] leading-snug text-[var(--tt-fg-muted)] pointer-events-none"
          style={{
            left: Math.min(size.w - 320, size.w / 2 + transform.x + (posCache.current.get(hovered.id)?.x ?? 0) * transform.k + 16),
            top: size.h / 2 + transform.y + (posCache.current.get(hovered.id)?.y ?? 0) * transform.k + 16,
          }}
        >
          <div className="text-[12px] font-semibold text-[var(--tt-fg)] mb-0.5">{hovered.ref.title}</div>
          {hovered.ref.description}
        </div>
      )}

      {/* search, top-left */}
      <div className="absolute top-3 left-3 flex items-center gap-2">
        <div className="flex items-center gap-1.5 h-8 px-2.5 rounded-[var(--tt-radius)] bg-[var(--tt-overlay)]/90 backdrop-blur border border-[var(--tt-border)] focus-within:border-[var(--tt-border-focus)]">
          <Search size={13} className="text-[var(--tt-fg-dim)]" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter pages…"
            className="bg-transparent outline-none focus-visible:outline-none text-[12px] text-[var(--tt-fg)] placeholder:text-[var(--tt-fg-faint)] w-[150px]"
          />
          {search && (
            <button onClick={() => setSearch("")} className="text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)]">
              <X size={12} />
            </button>
          )}
        </div>
        {selectedId && (
          <button
            onClick={() => setCtl((c) => ({ ...c, focusDepth: c.focusDepth === 0 ? 1 : c.focusDepth === 1 ? 2 : 0 }))}
            className={cn(
              "flex items-center gap-1.5 h-8 px-2.5 rounded-[var(--tt-radius)] border text-[11px] font-medium backdrop-blur transition-colors",
              ctl.focusDepth > 0
                ? "bg-[var(--tt-brand-glow)] border-[color:var(--tt-brand)]/40 text-[var(--tt-brand)]"
                : "bg-[var(--tt-overlay)]/90 border-[var(--tt-border)] text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)]",
            )}
            title="Cycle local-graph depth: off / 1 / 2"
          >
            <Focus size={13} />
            {ctl.focusDepth === 0 ? "Focus" : `Depth ${ctl.focusDepth}`}
          </button>
        )}
      </div>

      {/* controls panel, top-right */}
      <div className="absolute top-3 right-3 flex flex-col items-end gap-2">
        <button
          onClick={() => setPanelOpen((o) => !o)}
          className="flex items-center gap-1.5 h-8 px-2.5 rounded-[var(--tt-radius)] bg-[var(--tt-overlay)]/90 backdrop-blur border border-[var(--tt-border)] text-[11px] font-medium text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)]"
        >
          <SlidersHorizontal size={13} />
          Controls
          <ChevronDown size={12} className={cn("transition-transform", panelOpen && "rotate-180")} />
        </button>
        {panelOpen && (
          <div className="w-[230px] p-3 rounded-[var(--tt-radius-lg)] bg-[var(--tt-overlay)]/95 backdrop-blur border border-[var(--tt-border-strong)] shadow-[var(--tt-shadow-pop)] space-y-3">
            <PanelSection title="Display">
              <Slider label="Node size" min={0.5} max={2} step={0.1} value={ctl.nodeScale} onChange={(v) => setCtl((c) => ({ ...c, nodeScale: v }))} />
              <Slider label="Label fade" min={0.2} max={2.5} step={0.1} value={ctl.labelZoom} onChange={(v) => setCtl((c) => ({ ...c, labelZoom: v }))} />
              <Toggle label="Cluster hulls" checked={ctl.showHulls} onChange={(v) => setCtl((c) => ({ ...c, showHulls: v }))} />
              <Toggle label="Orphan pages" checked={ctl.showOrphans} onChange={(v) => setCtl((c) => ({ ...c, showOrphans: v }))} />
            </PanelSection>
            <PanelSection title="Forces">
              <Slider label="Repel" min={40} max={500} step={10} value={ctl.repel} onChange={(v) => setCtl((c) => ({ ...c, repel: v }))} />
              <Slider label="Link distance" min={25} max={200} step={5} value={ctl.linkDist} onChange={(v) => setCtl((c) => ({ ...c, linkDist: v }))} />
            </PanelSection>
            <button
              onClick={() => { setCtl(DEFAULTS); setTransform({ x: 0, y: 0, k: 1 }); }}
              className="w-full h-7 rounded-[var(--tt-radius-sm)] border border-[var(--tt-border)] text-[11px] text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)] hover:border-[var(--tt-border-strong)] transition-colors"
            >
              Reset view
            </button>
          </div>
        )}
      </div>

      {/* legend, bottom-left: type identity is never color-alone (labels + counts) */}
      <div className="absolute bottom-3 left-3 flex flex-wrap items-center gap-1.5 max-w-[70%]">
        {typeEntries.map(([t, count]) => {
          const hiddenT = hiddenTypes.has(t);
          const slot = t === "untyped" ? GRAY : typeSlot(palette, t);
          return (
            <button
              key={t}
              onClick={() => setHiddenTypes((prev) => {
                const next = new Set(prev);
                if (next.has(t)) next.delete(t); else next.add(t);
                return next;
              })}
              className={cn(
                "flex items-center gap-1.5 h-6 px-2 rounded-full border text-[10.5px] font-medium backdrop-blur transition-all",
                hiddenT
                  ? "bg-transparent border-[var(--tt-border)] text-[var(--tt-fg-faint)] line-through"
                  : "bg-[var(--tt-overlay)]/90 border-[var(--tt-border)] text-[var(--tt-fg-muted)] hover:border-[var(--tt-border-strong)]",
              )}
              title={hiddenT ? `Show ${t} pages` : `Hide ${t} pages`}
            >
              <span className="h-2 w-2 rounded-full" style={{ background: dark ? slot.dark : slot.light, opacity: hiddenT ? 0.3 : 1 }} />
              {t} <span className="text-[var(--tt-fg-faint)] tabular">{count}</span>
            </button>
          );
        })}
      </div>

      {/* zoom controls + graph stats, bottom-right */}
      <div className="absolute bottom-12 right-3 flex flex-col rounded-[var(--tt-radius)] overflow-hidden border border-[var(--tt-border)] bg-[var(--tt-overlay)]/90 backdrop-blur">
        <ZoomButton title="Zoom in" onClick={() => zoomAt(0, 0, 1.4)}><Plus size={13} /></ZoomButton>
        <ZoomButton title="Zoom out" onClick={() => zoomAt(0, 0, 1 / 1.4)}><Minus size={13} /></ZoomButton>
        <ZoomButton title="Reset view" onClick={() => setTransform({ x: 0, y: 0, k: 1 })}><Maximize2 size={12} /></ZoomButton>
      </div>
      <div className="absolute bottom-3 right-3 flex items-center gap-1.5 text-[10.5px] text-[var(--tt-fg-dim)] px-2.5 h-6 rounded-full bg-[var(--tt-overlay)]/90 backdrop-blur border border-[var(--tt-border)]">
        <Boxes size={11} />
        {simData.visNodes.filter((n) => n.id !== "index").length} pages · {simData.visEdges.length} links · {hulls.length || clusters.length} clusters
      </div>
    </div>
  );
}

/* ------------------------------------------------------------ controls UI */

function ZoomButton({ title, onClick, children }: { title: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      title={title}
      aria-label={title}
      onClick={onClick}
      className="h-7 w-7 grid place-items-center text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)] hover:tt-tint-2 transition-colors border-b border-[var(--tt-border)] last:border-b-0"
    >
      {children}
    </button>
  );
}

function PanelSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[9px] font-semibold uppercase tracking-[0.18em] text-[var(--tt-fg-faint)] mb-1.5">{title}</div>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}

function Slider({ label, min, max, step, value, onChange }: {
  label: string; min: number; max: number; step: number; value: number; onChange: (v: number) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-[11px] text-[var(--tt-fg-muted)]">
      <span className="w-[76px] shrink-0">{label}</span>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="flex-1 h-1 accent-[var(--tt-brand)]"
      />
    </label>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center justify-between gap-2 text-[11px] text-[var(--tt-fg-muted)] cursor-pointer">
      {label}
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="accent-[var(--tt-brand)]" />
    </label>
  );
}

/* --------------------------------------------------------------- geometry */

/** Andrew's monotone chain convex hull. */
function convexHull(points: [number, number][]): [number, number][] {
  if (points.length <= 2) return points;
  const pts = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (o: number[], a: number[], b: number[]) =>
    (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower: [number, number][] = [];
  for (const p of pts) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
    lower.push(p);
  }
  const upper: [number, number][] = [];
  for (const p of [...pts].reverse()) {
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
    upper.push(p);
  }
  return [...lower.slice(0, -1), ...upper.slice(0, -1)];
}

/** Push hull vertices outward from the centroid by `pad`. */
function padHull(hull: [number, number][], pad: number): [number, number][] {
  const cx = hull.reduce((s, p) => s + p[0], 0) / hull.length;
  const cy = hull.reduce((s, p) => s + p[1], 0) / hull.length;
  return hull.map(([x, y]) => {
    const dx = x - cx, dy = y - cy;
    const len = Math.sqrt(dx * dx + dy * dy) || 1;
    return [x + (dx / len) * pad, y + (dy / len) * pad] as [number, number];
  });
}

/** Closed Catmull-Rom spline through the hull points (soft blob look). */
function smoothClosedPath(pts: [number, number][]): string {
  if (pts.length < 3) {
    if (pts.length === 2) {
      const [a, b] = pts;
      return `M ${a[0]} ${a[1]} L ${b[0]} ${b[1]}`;
    }
    return "";
  }
  const n = pts.length;
  let d = `M ${pts[0][0]} ${pts[0][1]}`;
  for (let i = 0; i < n; i++) {
    const p0 = pts[(i - 1 + n) % n];
    const p1 = pts[i];
    const p2 = pts[(i + 1) % n];
    const p3 = pts[(i + 2) % n];
    const c1x = p1[0] + (p2[0] - p0[0]) / 6;
    const c1y = p1[1] + (p2[1] - p0[1]) / 6;
    const c2x = p2[0] - (p3[0] - p1[0]) / 6;
    const c2y = p2[1] - (p3[1] - p1[1]) / 6;
    d += ` C ${c1x} ${c1y}, ${c2x} ${c2y}, ${p2[0]} ${p2[1]}`;
  }
  return d + " Z";
}
