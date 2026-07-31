"use client";
/**
 * LiveTrace — session-trace section between ProofStrip and HowItWorks.
 * Replays a real-shaped session via TerminalReplay; the metric chips under
 * the frame count up when the trace's cost line prints (once per loop,
 * `onCostLine`) and dim back to zero when the replay wraps (`onLoop`).
 * SSR / no-JS / reduced motion all render the final values at full strength.
 */
import { useEffect, useRef, useState } from "react";
import { animate } from "animejs";
import TerminalReplay from "@/components/TerminalReplay";
import SectionHead from "@/components/SectionHead";
import { Reveal, ANIME_EASE, EASE_CSS, motionOk } from "@/components/motion";

const fmtInt = (n: number) => Math.round(n).toLocaleString("en-US");
const fmtCost = (n: number) => `$${n.toFixed(2)}`;

/** Mirrors the script's cost line: "tokens 12,440 · cached 8,210 · cost $0.18". */
const METRICS = [
  { label: "tokens", value: 12440, format: fmtInt },
  { label: "cached", value: 8210, format: fmtInt },
  { label: "cost", value: 0.18, format: fmtCost },
] as const;

type Phase = "static" | "waiting" | "lit";

export default function LiveTrace() {
  // static: SSR / no-JS / reduced motion — final values, full strength.
  // waiting: replay running, cost line not printed yet — dimmed zeros.
  // lit: cost line printed — values counted up, full strength.
  const [phase, setPhase] = useState<Phase>("static");
  const valueRefs = useRef<(HTMLSpanElement | null)[]>([]);
  const animsRef = useRef<ReturnType<typeof animate>[]>([]);

  useEffect(() => {
    if (motionOk()) setPhase("waiting");
  }, []);

  useEffect(() => {
    if (phase !== "waiting") return;
    animsRef.current.forEach((a) => a.pause());
    animsRef.current = [];
    valueRefs.current.forEach((el, i) => {
      if (el) el.textContent = METRICS[i].format(0);
    });
  }, [phase]);

  const onCostLine = () => {
    setPhase("lit");
    animsRef.current.forEach((a) => a.pause());
    animsRef.current = METRICS.map((m, i) => {
      const el = valueRefs.current[i];
      const state = { v: 0 };
      return animate(state, {
        v: m.value,
        duration: 700,
        ease: ANIME_EASE.countUp,
        onUpdate: () => {
          if (el) el.textContent = m.format(state.v);
        },
        onComplete: () => {
          if (el) el.textContent = m.format(m.value);
        },
      });
    });
  };

  const onLoop = () => setPhase("waiting");

  return (
    <section id="trace" className="scroll-mt-[82px] relative max-w-[1180px] mx-auto px-5 py-16 sm:py-24">
      <SectionHead
        index="03"
        label="trace"
        title={
          <>
            See what your agent{" "}
            <span className="text-[var(--tt-brand)]">actually did.</span>
          </>
        }
        sub="Every session becomes a replayable trace: prompts, tool calls, reasoning steps, and the exact token cost."
      />

      <Reveal y={24} className="max-w-[820px] mx-auto">
        <TerminalReplay onCostLine={onCostLine} onLoop={onLoop} />
        <div className="mt-4 flex flex-wrap justify-center gap-3">
          {METRICS.map((m, i) => (
            <div
              key={m.label}
              className="flex items-baseline gap-2 rounded-full border border-[var(--tt-border)] bg-[var(--tt-raised)] px-4 py-2"
              style={{
                opacity: phase === "waiting" ? 0.45 : 1,
                transition: `opacity 250ms ${EASE_CSS}`,
              }}
            >
              <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--tt-fg-dim)]">
                {m.label}
              </span>
              <span className="font-mono text-[13px] tabular-nums text-[var(--tt-fg)]">
                <span className="relative inline-block">
                  {/* Sizer: reserves the final width so counting never shifts layout. */}
                  <span aria-hidden="true" className="invisible">
                    {m.format(m.value)}
                  </span>
                  <span
                    ref={(el) => {
                      valueRefs.current[i] = el;
                    }}
                    aria-hidden="true"
                    className="absolute inset-0 text-right"
                  >
                    {m.format(m.value)}
                  </span>
                  <span className="sr-only">{m.format(m.value)}</span>
                </span>
              </span>
            </div>
          ))}
        </div>
      </Reveal>
    </section>
  );
}
