"use client";
/**
 * Reveal — the workhorse once-only in-view entrance.
 * opacity 0→1, y→0 on spring 300/34, once-only at `amount` (default 0.15).
 * Reduced motion: 200ms opacity fade, no translate.
 *
 * Visibility safety nets (bug: sections stayed at opacity 0 after instant
 * jumps — hash links, End key — because a tall element can never have a
 * large fraction visible at once, so the in-view threshold never fired):
 *  1. on mount (after one rAF), an element already intersecting the
 *     viewport snaps visible with no transition;
 *  2. an element that has been intersecting for 1200ms without revealing
 *     snaps visible;
 *  3. on hashchange/popstate (and once at mount for hash loads), content
 *     inside the target section snaps visible.
 */
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { motion, useInView, useReducedMotion } from "motion/react";
import { DUR, SPRING } from "./vocab";

const TAGS = {
  div: motion.div,
  section: motion.section,
  header: motion.header,
  span: motion.span,
  p: motion.p,
  ul: motion.ul,
  li: motion.li,
} as const;

/** Element intersects the viewport at all (any pixel). */
function intersectsViewport(el: HTMLElement): boolean {
  const r = el.getBoundingClientRect();
  return (
    r.bottom > 0 &&
    r.top < window.innerHeight &&
    r.right > 0 &&
    r.left < window.innerWidth
  );
}

/**
 * Shared visibility state for Reveal/Stagger: once-only in-view trigger plus
 * the snap failsafes above. `snapped` means "reveal with no transition".
 * Internal to the motion primitives; not re-exported from motion/index.
 */
export function useRevealed(amount: number): {
  setRef: (el: HTMLElement | null) => void;
  revealed: boolean;
  snapped: boolean;
} {
  const ref = useRef<HTMLElement | null>(null);
  const setRef = useCallback((el: HTMLElement | null) => {
    ref.current = el;
  }, []);
  const [snapped, setSnapped] = useState(false);
  const inView = useInView(ref, { once: true, amount });
  // Any-pixel intersection, continuously tracked (for the 1200ms failsafe).
  const touching = useInView(ref);

  const revealed = inView || snapped;
  const revealedRef = useRef(revealed);
  revealedRef.current = revealed;

  // (1) Mount check: already on screen (hash load, restored scroll) → snap.
  useEffect(() => {
    const id = requestAnimationFrame(() => {
      const el = ref.current;
      if (el && !revealedRef.current && intersectsViewport(el)) {
        setSnapped(true);
      }
    });
    return () => cancelAnimationFrame(id);
  }, []);

  // (2) Failsafe: intersecting for 1200ms but still hidden → snap.
  useEffect(() => {
    if (revealed || !touching) return;
    const t = setTimeout(() => setSnapped(true), 1200);
    return () => clearTimeout(t);
  }, [touching, revealed]);

  // (3) Hash/history jumps: force-reveal content inside the target section.
  useEffect(() => {
    const onJump = () => {
      const hash = window.location.hash;
      if (hash.length < 2) return;
      const target = document.getElementById(hash.slice(1));
      const el = ref.current;
      if (
        el &&
        target &&
        !revealedRef.current &&
        (target.contains(el) || el.contains(target))
      ) {
        setSnapped(true);
      }
    };
    onJump(); // initial load with a hash
    window.addEventListener("hashchange", onJump);
    window.addEventListener("popstate", onJump);
    return () => {
      window.removeEventListener("hashchange", onJump);
      window.removeEventListener("popstate", onJump);
    };
  }, []);

  return { setRef, revealed, snapped };
}

export type RevealProps = {
  children: ReactNode;
  /** Rise distance: 8 (chips), 16 (text blocks, default), 24 (cards/media). */
  y?: 8 | 16 | 24;
  /** Delay in seconds. */
  delay?: number;
  /** In-view threshold (default 0.15). */
  amount?: number;
  /** Rendered element (default "div"). */
  as?: keyof typeof TAGS;
  className?: string;
};

export default function Reveal({
  children,
  y = 16,
  delay = 0,
  amount = 0.15,
  as = "div",
  className,
}: RevealProps) {
  const reduced = useReducedMotion();
  const Tag = TAGS[as];
  const { setRef, revealed, snapped } = useRevealed(amount);

  const hidden = reduced ? { opacity: 0 } : { opacity: 0, y };
  const shown = reduced ? { opacity: 1 } : { opacity: 1, y: 0 };
  const transition = snapped
    ? { duration: 0 }
    : reduced
      ? { duration: DUR.fade, delay }
      : { ...SPRING.reveal, delay };

  return (
    <Tag
      ref={setRef}
      initial={hidden}
      animate={revealed ? shown : hidden}
      transition={transition}
      className={className}
    >
      {children}
    </Tag>
  );
}
