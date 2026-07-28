/**
 * Motion vocabulary — the single source of truth for durations, easings,
 * distances, and stagger gaps across the landing page. Import from
 * "@/components/motion". CSS twin: `--tt-ease` in globals.css.
 */
import type { Transition } from "motion/react";

/** The one entrance curve. Same values as `--tt-ease` in globals.css. */
export const EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];
export const EASE_CSS = "cubic-bezier(0.22, 1, 0.36, 1)";

/** Durations in SECONDS (motion/react convention). animejs wants ms — multiply by 1000. */
export const DUR = {
  /** hover, tab color, copy button */
  micro: 0.18,
  /** standard reveal */
  reveal: 0.55,
  /** count-ups (900–1100ms band; default midpoint) */
  countUp: 1.0,
  /** SVG path draws (700–900ms band; default midpoint) */
  draw: 0.8,
  /** caduceus draw */
  caduceus: 1.2,
  /** terminal line arrival */
  line: 0.15,
  /** reduced-motion opacity fade */
  fade: 0.2,
} as const;

/** Springs. Only where things move between states. */
export const SPRING = {
  /** reveals — settles ~550ms, no overshoot */
  reveal: { type: "spring", stiffness: 300, damping: 34 } as Transition,
  /** pop-ins (floating tags, badges) — slight bounce */
  pop: { type: "spring", stiffness: 300, damping: 26 } as Transition,
  /** shared-layout tab underline */
  tab: { type: "spring", stiffness: 400, damping: 36 } as Transition,
} as const;

/** Rise distances in px. Transforms + opacity only; never width/height/layout/filter. */
export const RISE = {
  text: 16,
  card: 24,
  chip: 8,
} as const;

/** Stagger gaps in ms (animejs) — divide by 1000 for motion's staggerChildren. */
export const GAP = {
  /** rows of ≤6 siblings */
  row: 80,
  /** dense grids (AgentsGrid) */
  grid: 40,
  /** chip rows */
  chip: 60,
} as const;

/** Default in-view trigger for below-fold reveals. */
export const VIEWPORT = { once: true, amount: 0.3 } as const;
/** Trigger for count-ups and SVG draws (numbers finish while readable). */
export const VIEWPORT_NUM = { once: true, amount: 0.5 } as const;

/** animejs ease names. */
export const ANIME_EASE = {
  countUp: "outExpo",
  draw: "outQuad",
} as const;
