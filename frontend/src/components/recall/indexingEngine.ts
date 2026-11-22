import type { IndexDocEvent, RecallMapPoint, IndexVectorEvent } from "@/lib/recall";
import { DOC_TYPES, cssVar, docTypeMeta } from "./docTypes";

// Canvas 2D drawing for the indexing animation. Two canvases:
//   stage: token chips travelling to a vector strip drawn from a real preview.
//   map:   one dot per embedded document at its projected xy, kept after the run.
// No React in here. The component feeds it events and reads hover hits back.

export interface MapPoint {
  x: number; y: number; docId: string; type: string; title: string; agent: string;
}

interface Chip { sx: number; sy: number; t0: number; dur: number; color: string }
interface Strip { vals: number[]; type: string; t0: number; replacedAt: number | null }
interface Pulse { p: MapPoint; t0: number }

const MAX_CHIPS = 120;
const MAX_POINTS = 20000;
const STRIP_BARS = 24;
const STRIP_HOLD_MS = 1400;
const PULSE_MS = 650;
const CHIP_MS = 700;

const ease = (t: number) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);

export class TheaterEngine {
  points: MapPoint[] = [];
  private pointsById = new Map<string, MapPoint>();
  private chips: Chip[] = [];
  private strips: Strip[] = [];
  private pulses: Pulse[] = [];
  private stage: HTMLCanvasElement | null = null;
  private map: HTMLCanvasElement | null = null;
  private raf = 0;
  private reduced = false;
  private hover: MapPoint | null = null;
  private colors: Record<string, string> = {};
  private colorsAt = -Infinity;
  private dead = false;

  attach(stage: HTMLCanvasElement, map: HTMLCanvasElement, reduced: boolean) {
    this.stage = stage;
    this.map = map;
    this.reduced = reduced;
    this.resize();
  }

  setReduced(reduced: boolean) { this.reduced = reduced; this.kick(true); }

  destroy() {
    this.dead = true;
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = 0;
  }

  reset() {
    this.points = [];
    this.pointsById.clear();
    this.chips = [];
    this.strips = [];
    this.pulses = [];
    this.hover = null;
    this.kick(true);
  }

  noteDoc(ev: IndexDocEvent | RecallMapPoint) {
    if (!ev.xy || this.points.length >= MAX_POINTS || this.pointsById.has(ev.doc_id)) return;
    const [x, y] = ev.xy;
    const p = { x, y, docId: ev.doc_id, type: ev.doc_type, title: ev.title, agent: ev.agent };
    this.pointsById.set(p.docId, p);
    this.points.push(p);
    this.kick();
  }

  setMap(points: RecallMapPoint[]) {
    this.points = [];
    this.pointsById.clear();
    this.pulses = [];
    this.hover = null;
    points.forEach((point) => this.noteDoc(point));
    this.kick();
  }

  /** Chips break off a card and head for the strip. `slotY` is the card row, 0..1 of the stage height. */
  spawnChips(ev: IndexDocEvent, slotY: number) {
    if (this.reduced || !this.stage) return;
    const { w, h } = this.size(this.stage);
    const color = this.color(DOC_TYPES[ev.doc_type]?.color ?? "--tt-fg-muted");
    const n = Math.max(1, Math.min(ev.chunks || 1, 10));
    const now = performance.now();
    for (let i = 0; i < n; i++) {
      this.chips.push({
        sx: w * 0.44 + Math.random() * 6,
        sy: h * slotY + (Math.random() - 0.5) * 14,
        t0: now + i * 35,
        dur: CHIP_MS,
        color,
      });
    }
    if (this.chips.length > MAX_CHIPS) this.chips.splice(0, this.chips.length - MAX_CHIPS);
    this.kick();
  }

  addVector(ev: IndexVectorEvent) {
    const point = this.pointsById.get(ev.doc_id);
    if (point && !this.reduced) this.pulses.push({ p: point, t0: performance.now() });
    if (!this.reduced && Array.isArray(ev.preview) && ev.preview.length) {
      const now = performance.now();
      const last = this.strips[this.strips.length - 1];
      if (last && last.replacedAt == null) last.replacedAt = now;
      this.strips.push({ vals: ev.preview.slice(0, STRIP_BARS).map(Number), type: ev.doc_type, t0: now, replacedAt: null });
      if (this.strips.length > 2) this.strips.shift();
    }
    this.kick();
  }

  setHover(p: MapPoint | null) {
    if (this.hover === p) return;
    this.hover = p;
    this.kick();
  }

  /** Nearest dot within 10 css px of (cx, cy), or null. */
  hitTest(cx: number, cy: number): MapPoint | null {
    if (!this.map) return null;
    const { w, h } = this.size(this.map);
    let best: MapPoint | null = null;
    let bestD = 100;
    for (const p of this.points) {
      const [px, py] = this.toMap(p, w, h);
      const d = (px - cx) ** 2 + (py - cy) ** 2;
      if (d < bestD) { bestD = d; best = p; }
    }
    return best;
  }

  resize() {
    for (const c of [this.stage, this.map]) {
      if (!c) continue;
      const rect = c.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const w = Math.max(1, Math.round(rect.width * dpr));
      const h = Math.max(1, Math.round(rect.height * dpr));
      if (c.width !== w) c.width = w;
      if (c.height !== h) c.height = h;
    }
    this.kick(true);
  }

  kick(refreshColors = false) {
    if (refreshColors) this.colorsAt = -Infinity;
    if (this.raf || this.dead) return;
    this.raf = requestAnimationFrame(() => { this.raf = 0; this.frame(); });
  }

  // ---- internals ----

  private size(c: HTMLCanvasElement) {
    const dpr = c.width / Math.max(1, c.getBoundingClientRect().width);
    return { w: c.width / dpr, h: c.height / dpr, dpr };
  }

  private color(token: string): string {
    return this.colors[token] ?? "#888";
  }

  private refreshColors(el: Element, now: number) {
    if (now - this.colorsAt < 1000) return;
    this.colorsAt = now;
    const tokens = new Set<string>([
      "--tt-brand", "--tt-warn-fg", "--tt-fg-dim", "--tt-fg-muted", "--tt-border", "--tt-border-strong", "--tt-fg",
    ]);
    for (const m of Object.values(DOC_TYPES)) tokens.add(m.color);
    for (const t of tokens) this.colors[t] = cssVar(el, t);
  }

  private toMap(p: { x: number; y: number }, w: number, h: number): [number, number] {
    const pad = 14;
    return [pad + ((p.x + 1) / 2) * (w - 2 * pad), pad + (1 - (p.y + 1) / 2) * (h - 2 * pad)];
  }

  private frame() {
    if (this.dead) return;
    const now = performance.now();
    if (this.stage) this.refreshColors(this.stage, now);
    else if (this.map) this.refreshColors(this.map, now);

    this.chips = this.chips.filter((c) => now - c.t0 < c.dur);
    this.pulses = this.pulses.filter((p) => now - p.t0 < PULSE_MS);
    this.strips = this.strips.filter((s) =>
      s.replacedAt != null ? now - s.replacedAt < 160 : now - s.t0 < STRIP_HOLD_MS + 500);

    this.drawStage(now);
    this.drawMap(now);

    if (this.chips.length || this.pulses.length || this.strips.length) this.kick();
  }

  private prep(c: HTMLCanvasElement) {
    const ctx = c.getContext("2d");
    if (!ctx) return null;
    const { w, h, dpr } = this.size(c);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    return { ctx, w, h };
  }

  private drawStage(now: number) {
    if (!this.stage) return;
    const s = this.prep(this.stage);
    if (!s) return;
    const { ctx, w, h } = s;
    if (this.reduced) return;

    const x0 = w * 0.54, x1 = w - 12;
    const tx = x0, ty = h / 2;

    for (const c of this.chips) {
      const t = (now - c.t0) / c.dur;
      if (t <= 0) continue;
      const e = ease(Math.min(1, t));
      const x = c.sx + (tx - c.sx) * e;
      const y = c.sy + (ty - c.sy) * e;
      ctx.globalAlpha = 1 - Math.max(0, t - 0.8) * 5;
      ctx.fillStyle = c.color;
      const cw = 12 - 8 * e, ch = 6 - 3 * e;
      ctx.beginPath();
      ctx.roundRect(x - cw / 2, y - ch / 2, cw, ch, 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;

    const barW = Math.max(2, (x1 - x0) / STRIP_BARS - 2);
    const maxH = h * 0.4;
    for (const st of this.strips) {
      const age = now - st.t0;
      let alpha = 1;
      if (st.replacedAt != null) alpha = 1 - (now - st.replacedAt) / 160;
      else if (age > STRIP_HOLD_MS) alpha = 1 - (age - STRIP_HOLD_MS) / 500;
      if (alpha <= 0) continue;
      const reveal = Math.min(1, age / 350);
      const shown = Math.ceil(st.vals.length * reveal);
      let m = 0;
      for (const v of st.vals) m = Math.max(m, Math.abs(v));
      if (!m) m = 1;
      for (let i = 0; i < shown; i++) {
        const v = st.vals[i];
        const mag = Math.abs(v) / m;
        ctx.globalAlpha = alpha * (0.35 + 0.65 * mag);
        ctx.fillStyle = v >= 0 ? this.color("--tt-brand") : this.color("--tt-warn-fg");
        const bh = Math.max(1.5, mag * maxH);
        const bx = x0 + i * (barW + 2);
        if (v >= 0) ctx.fillRect(bx, ty - bh, barW, bh);
        else ctx.fillRect(bx, ty, barW, bh);
      }
      ctx.globalAlpha = alpha * 0.5;
      ctx.fillStyle = this.color(DOC_TYPES[st.type as keyof typeof DOC_TYPES]?.color ?? "--tt-fg-muted");
      ctx.fillRect(x0, ty - 0.5, STRIP_BARS * (barW + 2), 1);
    }
    ctx.globalAlpha = 1;
  }

  private drawMap(now: number) {
    if (!this.map) return;
    const s = this.prep(this.map);
    if (!s) return;
    const { ctx, w, h } = s;

    ctx.strokeStyle = this.color("--tt-border");
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(w / 2, 8); ctx.lineTo(w / 2, h - 8);
    ctx.moveTo(8, h / 2); ctx.lineTo(w - 8, h / 2);
    ctx.stroke();

    for (const p of this.points) {
      const [px, py] = this.toMap(p, w, h);
      ctx.fillStyle = this.color(docTypeMeta(p.type).color);
      ctx.globalAlpha = 0.85;
      ctx.beginPath();
      ctx.arc(px, py, 3, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;

    for (const pu of this.pulses) {
      const t = (now - pu.t0) / PULSE_MS;
      const [px, py] = this.toMap(pu.p, w, h);
      ctx.strokeStyle = this.color(docTypeMeta(pu.p.type).color);
      ctx.globalAlpha = Math.max(0, 1 - t);
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(px, py, 3 + 12 * ease(Math.min(1, t)), 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

    if (this.hover) {
      const [px, py] = this.toMap(this.hover, w, h);
      ctx.strokeStyle = this.color("--tt-fg");
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(px, py, 6, 0, Math.PI * 2);
      ctx.stroke();
    }
  }
}
