"use client";
/**
 * CountUp — animejs count-up with zero layout shift.
 * Renders `prefix` + a tabular-nums span pre-sized to the FORMATTED final
 * value (hidden sizer) + `suffix`. Counts 0→to with `outExpo` once the
 * element is 50% in view. Server/no-JS render and reduced motion both show
 * the final value; keep unit glyphs (`+`, `k`, `★`, `$`) in prefix/suffix,
 * never inside the counted number.
 */
import { useEffect, useRef } from "react";
import { useInView } from "motion/react";
import { animate } from "animejs";
import { motionOk } from "./useMotionOk";
import { ANIME_EASE } from "./vocab";

export type CountUpProps = {
  /** Final numeric value. May arrive late (e.g. fetched star count). */
  to: number;
  /** Duration in ms (default 1000; band is 900–1100 for stats, 300–700 for small counts). */
  duration?: number;
  /** Static text before the number (e.g. "$"). Not animated. */
  prefix?: string;
  /** Static text after the number (e.g. "k", "+", " sessions"). Not animated. */
  suffix?: string;
  /** Formats the in-flight (fractional) and final value. Default: Math.round + toLocaleString("en-US"). */
  format?: (n: number) => string;
  /** Delay in ms after entering view (default 0). */
  delay?: number;
  className?: string;
};

const defaultFormat = (n: number) => Math.round(n).toLocaleString("en-US");

export default function CountUp({
  to,
  duration = 1000,
  prefix,
  suffix,
  format,
  delay = 0,
  className,
}: CountUpProps) {
  const rootRef = useRef<HTMLSpanElement>(null);
  const valueRef = useRef<HTMLSpanElement>(null);
  const ran = useRef(false);
  const inView = useInView(rootRef, { once: true, amount: 0.5 });

  const fmt = format ?? defaultFormat;
  const final = fmt(to);

  useEffect(() => {
    const el = valueRef.current;
    if (!el || !inView) return;
    // `to` arrived/changed after the animation already ran: snap to final.
    if (ran.current || !motionOk()) {
      ran.current = true;
      el.textContent = final;
      return;
    }
    ran.current = true;
    const state = { v: 0 };
    animate(state, {
      v: to,
      duration,
      delay,
      ease: ANIME_EASE.countUp,
      onUpdate: () => {
        el.textContent = fmt(state.v);
      },
      onComplete: () => {
        el.textContent = final;
      },
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inView, to]);

  return (
    <span ref={rootRef} className={`tabular ${className ?? ""}`.trim()}>
      {prefix}
      <span className="relative inline-block">
        {/* Sizer: reserves the final width so counting never shifts layout. */}
        <span aria-hidden="true" className="invisible">
          {final}
        </span>
        {/* Counted layer. Initial content = final value (no-JS / SSR / SEO);
            the first animation frame overwrites it with the formatted 0. */}
        <span
          ref={valueRef}
          className="absolute inset-0 text-right"
          aria-hidden="true"
        >
          {final}
        </span>
        {/* Accessible value, never animated. */}
        <span className="sr-only">{final}</span>
      </span>
      {suffix}
    </span>
  );
}
