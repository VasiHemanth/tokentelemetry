"use client";
/**
 * TokenField — the hero's full-bleed canvas. Tokens (small colored points in
 * each agent's identity color) stream from the viewport edges along bezier
 * paths into a "localhost core" on the right, leaving short trails. Pure
 * canvas 2d, no deps. Reduced motion: one static scatter frame, no loop.
 * The loop also stops while the hero is off-screen or the tab is hidden.
 */
import { useEffect, useRef } from "react";
import { motionOk } from "@/components/motion";

const AGENT_VARS = [
  "--agent-claude",
  "--agent-codex",
  "--agent-gemini",
  "--agent-antigravity",
  "--agent-qwen",
  "--agent-vibe",
  "--agent-cursor",
  "--agent-copilot",
  "--agent-opencode",
] as const;

const BG = "#0a0c10"; // must match --tt-canvas: the canvas IS the section bg

type P = {
  // bezier: start → (ctrl) → core
  sx: number; sy: number; cx: number; cy: number;
  t: number; speed: number; size: number; color: string;
};

/** Core position as a fraction of the canvas, matching the hero's layout. */
function corePos(w: number, h: number) {
  return w > 1024 ? { x: w * 0.74, y: h * 0.5 } : { x: w * 0.5, y: h * 0.88 };
}

function spawn(w: number, h: number, colors: string[], t0 = 0): P {
  // Spawn on the left / top / bottom edges so streams converge rightward.
  const edge = Math.random();
  let sx: number, sy: number;
  if (edge < 0.5) { sx = -8; sy = Math.random() * h; }
  else if (edge < 0.75) { sx = Math.random() * w * 0.9; sy = -8; }
  else { sx = Math.random() * w * 0.9; sy = h + 8; }
  const core = corePos(w, h);
  // Control point: midway with a perpendicular-ish scatter for varied arcs.
  const mx = (sx + core.x) / 2, my = (sy + core.y) / 2;
  return {
    sx, sy,
    cx: mx + (Math.random() - 0.5) * w * 0.35,
    cy: my + (Math.random() - 0.5) * h * 0.5,
    t: t0,
    speed: 0.0016 + Math.random() * 0.0028,
    size: 0.9 + Math.random() * 1.4,
    color: colors[(Math.random() * colors.length) | 0],
  };
}

export default function TokenField({ className }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const styles = getComputedStyle(document.documentElement);
    const colors = AGENT_VARS
      .map((v) => styles.getPropertyValue(v).trim())
      .filter(Boolean);
    if (!colors.length) colors.push("#60a5fa");

    let w = 0, h = 0, dpr = 1;
    let particles: P[] = [];
    let raf = 0;
    let running = false;
    const animated = motionOk();

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = rect.width; h = rect.height;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const n = w > 1024 ? 110 : 55;
      particles = Array.from({ length: n }, () =>
        spawn(w, h, colors, Math.random()));
      ctx.fillStyle = BG;
      ctx.fillRect(0, 0, w, h);
      if (!animated) drawStatic();
    };

    // Reduced motion: a quiet constellation at rest — the same points, no loop.
    const drawStatic = () => {
      for (const p of particles) {
        const x = q(p.sx, p.cx, coreX(), p.t);
        const y = q(p.sy, p.cy, coreY(), p.t);
        ctx.globalAlpha = 0.35;
        ctx.fillStyle = p.color;
        ctx.beginPath();
        ctx.arc(x, y, p.size, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      drawCore(1);
    };

    const q = (a: number, c: number, b: number, t: number) =>
      (1 - t) * (1 - t) * a + 2 * (1 - t) * t * c + t * t * b;
    const coreX = () => corePos(w, h).x;
    const coreY = () => corePos(w, h).y;

    let pulse = 0;
    const drawCore = (alpha: number) => {
      const x = coreX(), y = coreY();
      const r = 46 + Math.sin(pulse) * 3;
      const g = ctx.createRadialGradient(x, y, 0, x, y, r * 2.6);
      g.addColorStop(0, "rgba(96,165,250,0.16)");
      g.addColorStop(0.55, "rgba(96,165,250,0.05)");
      g.addColorStop(1, "rgba(96,165,250,0)");
      ctx.globalAlpha = alpha;
      ctx.fillStyle = g;
      ctx.fillRect(x - r * 2.6, y - r * 2.6, r * 5.2, r * 5.2);
      ctx.strokeStyle = "rgba(96,165,250,0.35)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.stroke();
      ctx.globalAlpha = 1;
    };

    const frame = () => {
      if (!running) return;
      pulse += 0.03;
      // Translucent wash = particle trails.
      ctx.fillStyle = "rgba(10,12,16,0.22)";
      ctx.fillRect(0, 0, w, h);
      const bx = coreX(), by = coreY();
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        p.t += p.speed * (0.6 + p.t); // ease-in: tokens accelerate toward the core
        if (p.t >= 1) { particles[i] = spawn(w, h, colors); continue; }
        const x = q(p.sx, p.cx, bx, p.t);
        const y = q(p.sy, p.cy, by, p.t);
        ctx.globalAlpha = 0.28 + p.t * 0.5; // brighten as they approach
        ctx.fillStyle = p.color;
        ctx.beginPath();
        ctx.arc(x, y, p.size, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      drawCore(1);
      raf = requestAnimationFrame(frame);
    };

    const start = () => {
      if (running || !animated) return;
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
      ([e]) => (e.isIntersecting ? start() : stop()),
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
