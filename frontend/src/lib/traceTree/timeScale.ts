/**
 * Piecewise-linear time scale for the trace view. Idle stretches longer than
 * IDLE_GAP_MS collapse into a fixed-width band so a session that sat overnight
 * does not squash the busy parts into a sliver. All clock math uses local
 * components; toISOString() would shift day boundaries for non-UTC users.
 */

export const IDLE_GAP_MS = 10 * 60 * 1000;

export interface Piece {
  t0: number;
  t1: number;
  /** Position in the 0..1 scale space. */
  u0: number;
  u1: number;
  gap: boolean;
}

export interface TimeScale {
  pieces: Piece[];
  t0: number;
  t1: number;
  /** Total time inside busy pieces (idle gaps excluded). */
  busyMs: number;
  /** Epoch ms to 0..1 scale position. */
  u(t: number): number;
  /** 0..1 scale position back to epoch ms. */
  tOf(x: number): number;
}

export function buildScale(intervals: Array<[number, number]>, gapMs = IDLE_GAP_MS): TimeScale {
  const iv = intervals
    .filter(([a, b]) => Number.isFinite(a) && Number.isFinite(b))
    .map(([a, b]): [number, number] => [a, Math.max(b, a + 1)])
    .sort((x, y) => x[0] - y[0]);
  if (!iv.length) {
    return { pieces: [], t0: 0, t1: 1, busyMs: 0, u: () => 0, tOf: () => 0 };
  }

  const busy: Array<[number, number]> = [];
  for (const [a, b] of iv) {
    const last = busy[busy.length - 1];
    if (last && a - last[1] < gapMs) last[1] = Math.max(last[1], b);
    else busy.push([a, b]);
  }
  const busyMs = busy.reduce((s, [a, b]) => s + (b - a), 0);
  // Each idle band takes 5% of busy time, capped so many gaps cannot exceed ~30% of the axis.
  const gapCount = busy.length - 1;
  const gapWeight = gapCount > 0 ? busyMs * Math.min(0.05, 0.3 / gapCount) : 0;

  const raw: Array<{ t0: number; t1: number; w: number; gap: boolean }> = [];
  busy.forEach(([a, b], i) => {
    if (i > 0) raw.push({ t0: busy[i - 1][1], t1: a, w: gapWeight, gap: true });
    raw.push({ t0: a, t1: b, w: b - a, gap: false });
  });
  const wTotal = raw.reduce((s, p) => s + p.w, 0);
  let acc = 0;
  const pieces: Piece[] = raw.map((p) => {
    const u0 = acc / wTotal;
    acc += p.w;
    return { t0: p.t0, t1: p.t1, u0, u1: acc / wTotal, gap: p.gap };
  });
  const t0 = pieces[0].t0;
  const t1 = pieces[pieces.length - 1].t1;

  function u(t: number): number {
    if (t <= t0) return 0;
    if (t >= t1) return 1;
    let lo = 0;
    let hi = pieces.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (t <= pieces[mid].t1) hi = mid;
      else lo = mid + 1;
    }
    const p = pieces[lo];
    return p.u0 + (p.u1 - p.u0) * ((t - p.t0) / Math.max(1, p.t1 - p.t0));
  }

  function tOf(x: number): number {
    if (x <= 0) return t0;
    for (const p of pieces) {
      if (x <= p.u1) return p.t0 + (p.t1 - p.t0) * ((x - p.u0) / Math.max(1e-9, p.u1 - p.u0));
    }
    return t1;
  }

  return { pieces, t0, t1, busyMs, u, tOf };
}

export interface AxisMark {
  /** Position within the visible window, 0..1. */
  x: number;
  label: string;
  kind: "tick" | "day" | "idle";
}

const TICK_STEPS_S = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function localMidnight(t: number, plusDays = 0): number {
  const d = new Date(t);
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + plusDays).getTime();
}

/**
 * Axis marks for the window [w0, w1] in scale space. Tick step is chosen from
 * the busy time inside the window and its pixel width, and ticks sit on local
 * clock boundaries. A "day" mark is placed at every local midnight crossed.
 */
export function axisMarks(scale: TimeScale, w0: number, w1: number, pxWidth: number): AxisMark[] {
  if (!scale.pieces.length || w1 <= w0) return [];
  const ta = scale.tOf(w0);
  const tb = scale.tOf(w1);
  let visBusy = 0;
  for (const p of scale.pieces) {
    if (!p.gap) visBusy += Math.max(0, Math.min(p.t1, tb) - Math.max(p.t0, ta));
  }
  const want = Math.max(2, Math.floor(pxWidth / 90));
  const stepMs = (TICK_STEPS_S.find((s) => visBusy / (s * 1000) <= want) ?? TICK_STEPS_S[TICK_STEPS_S.length - 1]) * 1000;
  const span = w1 - w0;
  const out: AxisMark[] = [];

  for (const p of scale.pieces) {
    if (p.gap) {
      const a = (p.u0 - w0) / span;
      const b = (p.u1 - w0) / span;
      if (b > 0 && a < 1 && (b - a) * pxWidth > 36) {
        out.push({ x: (a + b) / 2, label: `${fmtDur(p.t1 - p.t0)} idle`, kind: "idle" });
      }
      continue;
    }
    const lo = Math.max(p.t0, ta);
    const hi = Math.min(p.t1, tb);
    if (hi <= lo) continue;

    const midnights = new Set<number>();
    for (let m = localMidnight(lo, 1); m < hi; m = localMidnight(m, 1)) {
      midnights.add(m);
      const x = (scale.u(m) - w0) / span;
      if (x >= 0.03 && x <= 0.97) {
        const d = new Date(m);
        out.push({ x, label: `${MONTHS[d.getMonth()]} ${d.getDate()}`, kind: "day" });
      }
    }

    const base = localMidnight(lo);
    for (let t = base + Math.ceil((lo - base) / stepMs) * stepMs; t <= hi; t += stepMs) {
      if (midnights.has(t)) continue;
      const x = (scale.u(t) - w0) / span;
      if (x < 0.03 || x > 0.97) continue;
      out.push({ x, label: stepMs < 60000 ? fmtClock(t) : fmtHm(t), kind: "tick" });
    }
  }
  return out;
}

const pad = (n: number) => String(n).padStart(2, "0");

export function fmtClock(t: number): string {
  const d = new Date(t);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export function fmtHm(t: number): string {
  const d = new Date(t);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function fmtDur(ms: number): string {
  if (!(ms > 0)) return "0s";
  if (ms < 1000) return `${(ms / 1000).toFixed(1)}s`;
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${pad(s % 60)}s`;
  return `${Math.floor(m / 60)}h ${pad(m % 60)}m`;
}

export function fmtTokens(n: number): string {
  if (!n) return "-";
  if (n >= 1e6) return `${(n / 1e6).toFixed(n >= 1e7 ? 1 : 2)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(n >= 1e4 ? 0 : 1)}k`;
  return String(n);
}

export function fmtCost(c: number): string {
  return `$${c.toFixed(c > 0 && c < 0.1 ? 3 : 2)}`;
}
