"use client";
import { useRef, useState } from "react";
import {
  motion,
  useMotionValueEvent,
  useReducedMotion,
  useScroll,
  type Variants,
} from "motion/react";
import { CountUp, DUR, GAP, RISE, SPRING } from "@/components/motion";
import SectionHead from "@/components/SectionHead";

const STEPS = [
  {
    n: "1",
    title: "Run one command",
    body: "Paste it into your terminal. Installs in seconds, opens automatically — no account, no API keys.",
    code: <><span className="text-[var(--tt-fg-faint)]">$ </span>curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash</>,
  },
  {
    n: "2",
    title: "It finds your agents",
    body: "Scans the log files Claude Code, Codex, Cursor & co. already write to your disk. Read-only. Nothing is sent anywhere.",
    code: <><span className="text-[var(--tt-success-fg,#10b981)]">✓</span> detected <CountUp to={13} duration={500} delay={900} /> agents · <CountUp to={510} duration={700} delay={900} /> sessions</>,
  },
  {
    n: "3",
    title: "Open the dashboard",
    body: "Tokens, cost, traces, and reasoning — for every agent, in one local dashboard.",
    code: <><span className="text-[var(--tt-fg-faint)]">→ </span>http://localhost:3000</>,
  },
];

/** Badge fill thresholds along the section's scroll progress. */
const FILL_AT = [0.15, 0.5, 0.85];

export default function HowItWorks() {
  const sectionRef = useRef<HTMLElement>(null);
  const reduced = useReducedMotion();

  // Scroll-linked effect #2 (page-wide budget: header chrome + this connector).
  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start 0.8", "end 0.5"],
  });
  const [filledCount, setFilledCount] = useState(0);
  useMotionValueEvent(scrollYProgress, "change", (v) => {
    const n = v >= FILL_AT[2] ? 3 : v >= FILL_AT[1] ? 2 : v >= FILL_AT[0] ? 1 : 0;
    setFilledCount((prev) => (prev === n ? prev : n));
  });

  const gridVariants: Variants = {
    hidden: {},
    visible: { transition: { staggerChildren: reduced ? 0 : GAP.row / 1000 } },
  };
  const cardVariants: Variants = reduced
    ? {
        hidden: { opacity: 0 },
        visible: { opacity: 1, transition: { duration: DUR.fade } },
      }
    : {
        hidden: { opacity: 0, y: RISE.card },
        // delayChildren = card settle (~550ms) + 200ms before its code line fades in.
        visible: { opacity: 1, y: 0, transition: { ...SPRING.reveal, delayChildren: 0.75 } },
      };
  const codeVariants: Variants = {
    hidden: { opacity: 0 },
    visible: { opacity: 1, transition: { duration: DUR.fade } },
  };

  return (
    <section ref={sectionRef} className="relative max-w-[1180px] mx-auto px-5 py-16 sm:py-24">
      <SectionHead
        index="04"
        label="setup"
        title={
          <>
            No instrumentation.{" "}
            <span className="text-[var(--tt-brand)]">No code changes.</span>
          </>
        }
        sub={
          <>
            Your agents already write logs. TokenTelemetry just reads them — so
            setup is one line, and there&apos;s nothing to wire into your codebase.
          </>
        }
      />
      <div className="relative">
        <motion.div
          className="grid grid-cols-1 md:grid-cols-3 gap-3 sm:gap-4"
          variants={gridVariants}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.3 }}
        >
          {STEPS.map((s, i) => (
            <motion.div
              key={s.n}
              variants={cardVariants}
              className="p-6 rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)]"
            >
              <div
                className="relative z-[1] inline-flex items-center justify-center w-[30px] h-[30px] rounded-lg mb-3.5 font-mono text-[12px] font-semibold border bg-[var(--tt-panel)] transition-[color,background-color,border-color,box-shadow] duration-200 ease-[var(--tt-ease)]"
                style={
                  reduced || filledCount > i
                    ? {
                        color: "var(--tt-brand)",
                        backgroundColor: "var(--tt-brand-glow)",
                        borderColor: "color-mix(in srgb, var(--tt-brand) 25%, transparent)",
                        boxShadow: "0 0 16px var(--tt-brand-glow)",
                      }
                    : {
                        color: "var(--tt-fg-dim)",
                        borderColor: "var(--tt-border-strong)",
                        boxShadow: "none",
                      }
                }
              >
                {s.n}
              </div>
              <h3 className="text-[16px] font-semibold tracking-[-0.01em] text-[var(--tt-fg)] mb-1.5">{s.title}</h3>
              <p className="text-[13.5px] text-[var(--tt-fg-muted)] leading-relaxed">{s.body}</p>
              <motion.div
                variants={codeVariants}
                className="mt-3 px-3 py-2 rounded-lg bg-[var(--tt-sunken)] border border-[var(--tt-border)] font-mono text-[11.5px] text-[var(--tt-fg-muted)] overflow-x-auto whitespace-nowrap"
              >
                {s.code}
              </motion.div>
            </motion.div>
          ))}
        </motion.div>
        {/* Connector line through the step badges (desktop only). Spans badge-1
            center → badge-3 center: badge center sits 39px (24px card padding +
            half the 30px badge) from each card edge; card width = (100% - 2×16px
            gaps) / 3. Sits above card panels, below the z-[1] badges. */}
        <div
          aria-hidden
          className="pointer-events-none absolute top-[39px] left-[39px] right-[calc((100%-32px)/3-39px)] hidden md:block h-0.5"
        >
          <svg className="w-full h-full" viewBox="0 0 100 2" preserveAspectRatio="none" fill="none">
            <line
              x1="0" y1="1" x2="100" y2="1"
              stroke="var(--tt-border-strong)"
              strokeWidth="1.5"
              vectorEffect="non-scaling-stroke"
            />
            <motion.line
              x1="0" y1="1" x2="100" y2="1"
              stroke="var(--tt-brand)"
              strokeWidth="1.5"
              strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
              style={{ pathLength: reduced ? 1 : scrollYProgress, opacity: 0.8 }}
            />
          </svg>
        </div>
      </div>
    </section>
  );
}
