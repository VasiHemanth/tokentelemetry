"use client";
/**
 * useDrawable — one-shot SVG stroke draw via animejs `svg.createDrawable`.
 * Fires once when the ref'd SVG is 50% in view; the animejs instance is
 * created inside the in-view effect, never on mount. Gated by `motionOk()`:
 * when motion is reduced the paths simply render complete as authored.
 * Returns `inView` so callers can sync companion effects.
 */
import { useEffect, useRef, type RefObject } from "react";
import { useInView } from "motion/react";
import { animate, stagger as animeStagger, svg } from "animejs";
import { motionOk } from "./useMotionOk";
import { ANIME_EASE } from "./vocab";

export type DrawableOptions = {
  /** Per-path draw duration in ms (default 800; band 700–900, caduceus 1200). */
  duration?: number;
  /** Stagger between paths in ms (default 0 = all together). */
  stagger?: number;
  /** animejs ease name (default "outQuad"). */
  ease?: string;
  /** Delay in ms before the first path starts (default 0). */
  delay?: number;
  /** In-view threshold (default 0.5). */
  amount?: number;
};

export function useDrawable(
  svgRef: RefObject<SVGSVGElement | null>,
  {
    duration = 800,
    stagger = 0,
    ease = ANIME_EASE.draw,
    delay = 0,
    amount = 0.5,
  }: DrawableOptions = {}
): boolean {
  const inView = useInView(svgRef, { once: true, amount });
  const ran = useRef(false);

  useEffect(() => {
    if (!inView || ran.current) return;
    const el = svgRef.current;
    if (!el) return;
    ran.current = true;
    if (!motionOk()) return; // paths stay fully drawn as authored

    const targets = el.querySelectorAll<SVGGeometryElement>(
      "path, line, polyline, polygon, circle, rect, ellipse"
    );
    if (targets.length === 0) return;

    const drawables = svg.createDrawable(targets);
    animate(drawables, {
      draw: ["0 0", "0 1"],
      duration,
      ease,
      delay: stagger > 0 ? animeStagger(stagger, { start: delay }) : delay,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inView]);

  return inView;
}
