"use client";
import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import { motion, useInView, useReducedMotion } from "motion/react";
import { animate, stagger } from "animejs";
import { AGENTS } from "@/data/agents";
import { track } from "@/lib/track";
import { motionOk } from "@/components/motion";
import SectionHead from "@/components/SectionHead";

/**
 * Interactive agent cards. The CRO audit (D3) found visitors tapping the old
 * static agent cards expecting them to *do* something — dead clicks. Now each
 * card is a real button that expands to reveal what TokenTelemetry captures and
 * where it reads from, so the click pays off.
 *
 * Motion: grid cascade on first in-view (animejs, grid stagger from the first
 * cell), status dots pulse on staggered delays so the grid reads as a bank of
 * live indicators, and expansion animates height to "auto" via motion/react so
 * long capture lists never clip.
 */
export default function AgentsGrid() {
  const [open, setOpen] = useState<number | null>(null);
  const reduced = useReducedMotion();
  const gridRef = useRef<HTMLDivElement>(null);
  const inView = useInView(gridRef, { once: true, amount: 0.2 });
  const ran = useRef(false);

  // Hide cards just before first client paint. Server/no-JS markup stays fully
  // visible; reduced motion never hides (cards render static).
  useLayoutEffect(() => {
    const grid = gridRef.current;
    if (!grid || !motionOk()) return;
    grid.querySelectorAll<HTMLElement>("[data-agent-card]").forEach((el) => {
      el.style.opacity = "0";
      el.style.transform = "translateY(16px)";
    });
  }, []);

  // Cascade in on first in-view. Inline styles are cleared on complete so the
  // hover translate (CSS) takes over and nothing stays resident.
  useEffect(() => {
    const grid = gridRef.current;
    if (!inView || ran.current || !grid) return;
    ran.current = true;
    const cards = grid.querySelectorAll<HTMLElement>("[data-agent-card]");
    const clear = () => {
      cards.forEach((el) => {
        el.style.opacity = "";
        el.style.transform = "";
      });
    };
    if (!motionOk()) {
      clear();
      return;
    }
    animate(cards, {
      opacity: [0, 1],
      translateY: [16, 0],
      duration: 550,
      ease: "outQuad",
      delay: stagger(40, { grid: [4, 4], from: "first" }),
      onComplete: clear,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inView]);

  return (
    <section id="agents" className="scroll-mt-[82px] border-t border-[var(--tt-border)]">
      <div className="max-w-[1180px] mx-auto px-5 py-12 sm:py-[72px]">
        <SectionHead
          index="06"
          label="coverage"
          title={
            <>
              {AGENTS.length} coding agents,{" "}
              <span className="text-[var(--tt-brand)]">one place.</span>
            </>
          }
          sub="Tap any agent to see what TokenTelemetry captures and where it reads from."
        />

        <div ref={gridRef} className="grid grid-cols-1 min-[480px]:grid-cols-2 lg:grid-cols-4 gap-2.5 items-start">
          {AGENTS.map((a, i) => {
            const isOpen = open === i;
            return (
              <button
                key={a.name}
                data-agent-card
                aria-expanded={isOpen}
                onClick={() => {
                  setOpen(isOpen ? null : i);
                  if (!isOpen) track("feature_used", { name: "agent_expand" });
                }}
                style={{ "--agent-accent": `${a.hex}59` } as CSSProperties}
                className={`group text-left p-4 rounded-[var(--tt-radius-lg)] border bg-[var(--tt-panel)] hover:border-[var(--agent-accent)] hover:bg-[var(--tt-raised)] hover:-translate-y-0.5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--tt-brand)] transition-all relative flex flex-col w-full ${
                  isOpen ? "border-[var(--agent-accent)]" : "border-[var(--tt-border)]"
                }`}
              >
                <span
                  aria-hidden="true"
                  className={`absolute top-4 right-4 text-[14px] transition-[transform,color] duration-200 motion-reduce:transition-none group-hover:text-[var(--tt-fg)] ${
                    isOpen ? "text-[var(--tt-fg)]" : "text-[var(--tt-fg-faint)]"
                  }`}
                  style={{ transform: isOpen ? "rotate(45deg)" : "none" }}
                >
                  +
                </span>
                <span className="flex items-center gap-2.5 mb-1">
                  <span
                    className="tt-pulse w-[9px] h-[9px] rounded-full shrink-0"
                    style={{
                      backgroundColor: a.hex,
                      boxShadow: `0 0 8px ${a.hex}66`,
                      animationDelay: `${i * 150}ms`,
                    }}
                  />
                  <span className="text-[14px] font-semibold tracking-[-0.01em] text-[var(--tt-fg)]">{a.name}</span>
                </span>
                <span className="font-mono text-[11px] text-[var(--tt-fg-dim)] pl-[19px]">{a.vendor}</span>

                <motion.span
                  className="block overflow-hidden pl-[19px]"
                  initial={false}
                  animate={isOpen ? { height: "auto", opacity: 1 } : { height: 0, opacity: 0 }}
                  transition={
                    reduced
                      ? { duration: 0 }
                      : { type: "spring", stiffness: 300, damping: 30 }
                  }
                >
                  <span className="block pt-2">
                    <span className="block text-[11.5px] text-[var(--tt-fg-muted)] leading-relaxed">
                      Reads from <span className="font-mono text-[var(--tt-fg-muted)]">{a.logPath}</span>
                    </span>
                    <span className="flex flex-wrap gap-1 mt-2">
                      {a.captures.map((c) => (
                        <span key={c} className="font-mono text-[10px] px-1.5 py-0.5 rounded-[5px] bg-[var(--tt-sunken)] border border-[var(--tt-border)] text-[var(--tt-fg-dim)]">
                          {c}
                        </span>
                      ))}
                    </span>
                  </span>
                </motion.span>
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}
