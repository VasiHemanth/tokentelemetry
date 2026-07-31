"use client";
/**
 * TokenField — the hero's full-bleed canvas. Every visual property carries
 * information: each supported agent owns ONE fixed origin point on the
 * left/top edge, its particles use that agent's identity color, and stream
 * density is proportional to a per-agent session count (demo data below).
 * Tokens travel bezier paths into the localhost core on the right; on
 * arrival the core flashes and `onArrival` reports a token amount so the
 * Hero's DOM counter can tick up. Reduced motion: one static frame of thin
 * gradient stream lines already converging on the core. The loop stops
 * while the hero is off-screen or the tab is hidden.
 */
import { useEffect, useRef } from "react";
import { motionOk } from "@/components/motion";
import { AGENTS } from "@/data/agents";

const BG = "#0a0c10"; // must match --tt-canvas: the canvas IS the section bg
const CORE = "52,211,153"; // emerald-400 — matches the DOM node's live dot

export type Origin = {
  name: string;
  color: string;
  /** Edge anchor as viewport fractions: x===0 → left edge, y===0 → top edge. */
  x: number;
  y: number;
  /** DEMO DATA: plausible relative session count; drives stream density. */
  sessions: number;
  /** Origins the Hero renders a faint mono label next to. */
  labeled?: boolean;
};

// Fixed per-agent origins. Coordinates are fractions of the canvas;
// `sessions` values are demo data (plausible relative volumes, not real
// telemetry) so heavier agents visibly emit denser streams.
const SPEC: Array<[string, number, number, number, boolean?]> = [
  ["Cline",          0,    0.07, 230],
  ["Claude Code",    0,    0.18, 1240, true],
  ["Codex",          0,    0.34, 860,  true],
  ["Cursor",         0,    0.50, 640,  true],
  ["Gemini CLI",     0,    0.66, 540,  true],
  ["GitHub Copilot", 0,    0.82, 410],
  ["Vibe",           0,    0.93, 120],
  ["Hermes Agent",   0.10, 0,    380,  true],
  ["Antigravity",    0.20, 0,    260],
  ["OpenCode",       0.30, 0,    190],
  ["Qwen CLI",       0.39, 0,    150],
  ["Grok Build",     0.48, 0,    130],
  ["SmallCode",      0.56, 0,    80],
  ["Pi",             0.63, 0,    90],
];

/** Exported so the Hero can place DOM source labels at the same anchors. */
export const ORIGINS: Origin[] = SPEC.map(([name, x, y, sessions, labeled]) => ({
  name,
  x,
  y,
  sessions,
  labeled,
  color: AGENTS.find((a) => a.name === name)?.hex ?? "#60a5fa",
}));

const TOTAL_SESSIONS = ORIGINS.reduce((s, o) => s + o.sessions, 0);

type P = {
  o: Origin;
  // bezier: start → (ctrl) → core
  sx: number; sy: number; cx: number; cy: number;
  t: number; speed: number; size: number;
};

/** Core position matching the hero's layout. Below lg the node is anchored a
    fixed distance above the section bottom (Hero uses bottom-10), so the core
    tracks pixels-from-bottom, not a fraction — content height varies. */
function corePos(w: number, h: number) {
  return w >= 1024 ? { x: w * 0.74, y: h * 0.5 } : { x: w * 0.5, y: h - 78 };
}

/** Signed per-origin bow so each agent's stream forms its own corridor. */
function bowFor(i: number) {
  return (i % 2 === 0 ? 1 : -1) * (0.08 + (i % 3) * 0.04);
}

function spawn(o: Origin, i: number, w: number, h: number, t0 = 0): P {
  // Fixed origin with a small jitter along the edge → a stream, not a line.
  const jitter = (Math.random() - 0.5) * 26;
  const sx = o.x === 0 ? -6 : o.x * w + jitter;
  const sy = o.y === 0 ? -6 : o.y * h + jitter;
  const core = corePos(w, h);
  const mx = (sx + core.x) / 2, my = (sy + core.y) / 2;
  // Perpendicular bow (per-origin, stable sign) + mild per-particle scatter.
  const dx = core.x - sx, dy = core.y - sy;
  const bow = bowFor(i);
  return {
    o, sx, sy,
    cx: mx - dy * bow + (Math.random() - 0.5) * 40,
    cy: my + dx * bow + (Math.random() - 0.5) * 40,
    t: t0,
    speed: 0.0016 + Math.random() * 0.0028,
    size: 1.1 + Math.random() * 1.5,
  };
}

export default function TokenField({
  className,
  onArrival,
}: {
  className?: string;
  /** Called when a particle reaches the core, with a demo token amount. */
  onArrival?: (tokens: number) => void;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const arrivalRef = useRef(onArrival);
  arrivalRef.current = onArrival;

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let w = 0, h = 0, dpr = 1;
    let particles: P[] = [];
    let raf = 0;
    let running = false;
    let flash = 0; // 0..1, decays; bumped on each particle arrival
    const animated = motionOk();

    const q = (a: number, c: number, b: number, t: number) =>
      (1 - t) * (1 - t) * a + 2 * (1 - t) * t * c + t * t * b;

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = rect.width; h = rect.height;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      // Density ∝ per-agent sessions, within the particle budget.
      const budget = w >= 1024 ? 140 : 60;
      particles = [];
      ORIGINS.forEach((o, i) => {
        const n = Math.max(1, Math.floor((o.sessions / TOTAL_SESSIONS) * budget));
        for (let k = 0; k < n; k++) particles.push(spawn(o, i, w, h, Math.random()));
      });
      ctx.fillStyle = BG;
      ctx.fillRect(0, 0, w, h);
      if (!animated) drawStatic();
    };

    let pulse = 0;
    const drawCore = () => {
      const { x, y } = corePos(w, h);
      const r = 46 + Math.sin(pulse) * 3 + flash * 5;
      const glow = 0.14 + flash * 0.22;
      const g = ctx.createRadialGradient(x, y, 0, x, y, r * 2.6);
      g.addColorStop(0, `rgba(${CORE},${glow})`);
      g.addColorStop(0.55, `rgba(${CORE},${glow * 0.3})`);
      g.addColorStop(1, `rgba(${CORE},0)`);
      ctx.fillStyle = g;
      ctx.fillRect(x - r * 2.6, y - r * 2.6, r * 5.2, r * 5.2);
      ctx.strokeStyle = `rgba(${CORE},${0.32 + flash * 0.35})`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.stroke();
    };

    // Reduced motion: one static frame — thin gradient stream lines from each
    // fixed origin already converging on the core, so the idea still reads.
    const drawStatic = () => {
      const core = corePos(w, h);
      ORIGINS.forEach((o, i) => {
        const sx = o.x === 0 ? 0 : o.x * w;
        const sy = o.y === 0 ? 0 : o.y * h;
        const mx = (sx + core.x) / 2, my = (sy + core.y) / 2;
        const dx = core.x - sx, dy = core.y - sy;
        const bow = bowFor(i);
        const cx = mx - dy * bow, cy = my + dx * bow;
        const grad = ctx.createLinearGradient(sx, sy, core.x, core.y);
        grad.addColorStop(0, `${o.color}26`); // ~15% alpha at the edge
        grad.addColorStop(1, `${o.color}99`); // ~60% alpha at the core
        ctx.strokeStyle = grad;
        ctx.lineWidth = 0.8 + (o.sessions / TOTAL_SESSIONS) * 6;
        ctx.beginPath();
        ctx.moveTo(sx, sy);
        ctx.quadraticCurveTo(cx, cy, core.x, core.y);
        ctx.stroke();
      });
      // A few resting tokens along the streams for texture.
      for (const p of particles) {
        const x = q(p.sx, p.cx, core.x, p.t);
        const y = q(p.sy, p.cy, core.y, p.t);
        ctx.globalAlpha = 0.5;
        ctx.fillStyle = p.o.color;
        ctx.beginPath();
        ctx.arc(x, y, p.size, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      drawCore();
    };

    const frame = () => {
      if (!running) return;
      pulse += 0.03;
      flash *= 0.92;
      // Translucent wash = particle trails.
      ctx.fillStyle = "rgba(10,12,16,0.25)";
      ctx.fillRect(0, 0, w, h);
      const core = corePos(w, h);
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        p.t += p.speed * (0.6 + p.t); // ease-in: tokens accelerate toward the core
        if (p.t >= 1) {
          // Payoff: the core flashes and the DOM counter ticks up.
          flash = Math.min(1, flash + 0.3);
          arrivalRef.current?.(120 + ((Math.random() * 780) | 0));
          const oi = ORIGINS.indexOf(p.o);
          particles[i] = spawn(p.o, oi, w, h);
          continue;
        }
        const x = q(p.sx, p.cx, core.x, p.t);
        const y = q(p.sy, p.cy, core.y, p.t);
        ctx.globalAlpha = 0.45 + p.t * 0.5; // brighten as they approach
        ctx.fillStyle = p.o.color;
        ctx.beginPath();
        ctx.arc(x, y, p.size, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      drawCore();
      raf = requestAnimationFrame(frame);
    };

    // The loop runs only while BOTH hold: canvas on-screen AND tab visible.
    // (A bare visibilitychange restart used to resume the rAF for a hero
    // that had been scrolled away.)
    let onScreen = true;
    const start = () => {
      if (running || !animated || !onScreen || document.hidden) return;
      running = true;
      raf = requestAnimationFrame(frame);
    };
    const stop = () => {
      running = false;
      cancelAnimationFrame(raf);
    };

    resize();
    start();

    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    const io = new IntersectionObserver(
      ([e]) => {
        onScreen = e.isIntersecting;
        if (onScreen) start();
        else stop();
      },
      { threshold: 0 },
    );
    io.observe(canvas);
    const onVis = () => (document.hidden ? stop() : start());
    document.addEventListener("visibilitychange", onVis);

    return () => {
      stop();
      ro.disconnect();
      io.disconnect();
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  return <canvas ref={ref} aria-hidden className={className} />;
}
