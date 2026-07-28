"use client";
/**
 * BorderBeam — one brand-tinted highlight revolution around the wrapped
 * block's border when it first enters view, then static. CSS does the work
 * (`.tt-border-beam` / `.tt-beam-run` + `@keyframes tt-beam` in globals.css);
 * JS only observes intersection, adds the run class once, and removes it on
 * animationend. No loop. Reduced motion: never runs (JS guard + CSS override).
 *
 * Give the wrapper a border-radius matching its child (the beam ring inherits
 * `border-radius` from this element).
 */
import { useEffect, useRef, type ReactNode } from "react";
import { motionOk } from "./useMotionOk";

export type BorderBeamProps = {
  children: ReactNode;
  /** In-view threshold before the revolution fires (default 0.4). */
  amount?: number;
  /** Extra classes on the wrapper — include the child's border-radius, e.g. "rounded-[var(--tt-radius-lg)]". */
  className?: string;
};

export default function BorderBeam({
  children,
  amount = 0.4,
  className,
}: BorderBeamProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || !motionOk()) return;

    const onEnd = (e: AnimationEvent) => {
      if (e.animationName === "tt-beam") el.classList.remove("tt-beam-run");
    };
    el.addEventListener("animationend", onEnd);

    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          el.classList.add("tt-beam-run");
          io.disconnect();
        }
      },
      { threshold: amount }
    );
    io.observe(el);

    return () => {
      io.disconnect();
      el.removeEventListener("animationend", onEnd);
    };
  }, [amount]);

  return (
    <div ref={ref} className={`tt-border-beam ${className ?? ""}`.trim()}>
      {children}
    </div>
  );
}
