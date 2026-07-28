"use client";
/**
 * BootShowcase — 02 · SCAN. The install boot sequence, full width: a typed
 * `tokentelemetry`, agent discovery lines in identity colors, then the frame
 * resolves into the real dashboard. Replays on demand. SSR / no-JS / reduced
 * motion render the resolved final state; the effect only rewinds it when the
 * frame is in view and motion is allowed.
 */
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { AnimatePresence, motion, useInView, useReducedMotion } from "motion/react";
import { Lock, TrendingUp } from "lucide-react";
import { track } from "@/lib/track";
import SectionHead from "@/components/SectionHead";
import { CountUp, useDrawable, motionOk, EASE, DUR, SPRING } from "@/components/motion";

const BOOT_CMD = "tokentelemetry";
type BootLine = { at: number; text: string; dot?: string; url?: boolean };
const BOOT_LINES: BootLine[] = [
  { at: 450, text: "Claude Code · ~/.claude/projects · 218 sessions", dot: "var(--agent-claude)" },
  { at: 900, text: "Codex · ~/.codex/sessions · 96 sessions", dot: "var(--agent-codex)" },
  { at: 1350, text: "11 more agents found", dot: "var(--tt-brand)" },
  { at: 1750, text: "13 agents · 510 sessions", dot: "var(--tt-brand)" },
  { at: 2100, text: "http://localhost:3000", url: true },
];
const RESOLVE_AT = 2400;
const TAGS_AT = 2750;
const REPLAY_AT = 3200;

/** "$599 burned" floating tag — pops in, counts up, draws its sparkline. */
function CostTag({ run, delay }: { run: number; delay: number }) {
  const reduced = useReducedMotion();
  const sparkRef = useRef<SVGSVGElement>(null);
  useDrawable(sparkRef, { duration: 700 });
  return (
    <motion.span
      initial={reduced ? false : { opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={reduced ? { duration: DUR.fade } : { ...SPRING.pop, delay }}
      className="hidden lg:inline-flex items-center gap-1.5 absolute z-20 bottom-[16%] -right-5 px-2.5 py-1.5 rounded-[var(--tt-radius)] text-[11.5px] font-semibold text-[#fbbf24] border border-[var(--tt-border-strong)] backdrop-blur shadow-[0_12px_30px_-14px_rgba(0,0,0,0.7)]"
      style={{ background: "color-mix(in srgb, var(--tt-overlay) 92%, transparent)" }}
    >
      <TrendingUp size={13} className="text-[var(--tt-warn)]" />
      <span>
        <CountUp key={run} to={599} prefix="$" duration={1100} /> burned · last 90 days
      </span>
      <svg ref={sparkRef} width="34" height="12" viewBox="0 0 34 12" fill="none" aria-hidden className="ml-0.5 shrink-0">
        <path d="M1 10 L6 8.5 L11 9 L16 5.5 L21 6.5 L26 3 L33 1.5" stroke="var(--tt-brand)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </motion.span>
  );
}

export default function BootShowcase() {
  const frameRef = useRef<HTMLDivElement>(null);
  const inView = useInView(frameRef, { once: true, amount: 0.45 });

  const [run, setRun] = useState(0);
  const [armed, setArmed] = useState(false);
  const [typedLen, setTypedLen] = useState(BOOT_CMD.length);
  const [lineCount, setLineCount] = useState(BOOT_LINES.length);
  const [resolved, setResolved] = useState(true);
  const [tagsOn, setTagsOn] = useState(true);
  const [replayReady, setReplayReady] = useState(false);

  // First run waits for the frame to scroll into view; replays fire directly.
  useEffect(() => {
    if (inView && motionOk()) setArmed(true);
  }, [inView]);

  useEffect(() => {
    if (!armed) return;
    setResolved(false);
    setTagsOn(false);
    setReplayReady(false);
    setTypedLen(0);
    setLineCount(0);
    const timers: number[] = [];
    for (let i = 1; i <= BOOT_CMD.length; i++) {
      timers.push(window.setTimeout(() => setTypedLen(i), i * 28));
    }
    BOOT_LINES.forEach((l, i) => {
      timers.push(window.setTimeout(() => setLineCount(i + 1), l.at));
    });
    timers.push(window.setTimeout(() => setResolved(true), RESOLVE_AT));
    timers.push(window.setTimeout(() => setTagsOn(true), TAGS_AT));
    timers.push(window.setTimeout(() => setReplayReady(true), REPLAY_AT));
    return () => timers.forEach((t) => clearTimeout(t));
  }, [armed, run]);

  const replay = () => {
    track("feature_used", { name: "boot_replay" });
    setRun((r) => r + 1);
  };

  return (
    <section className="py-16 sm:py-24">
      <div className="max-w-[1180px] mx-auto px-5">
      <SectionHead
        index="02"
        label="scan"
        title={
          <>
            One command finds{" "}
            <span className="text-[var(--tt-brand)]">every agent you run.</span>
          </>
        }
        sub="No SDK, no config, no signup. The installer scans the logs your agents already write — read-only — and opens the dashboard on localhost."
      />
        <div ref={frameRef} className="relative max-w-[1000px] mx-auto">
          <div aria-hidden className="absolute -inset-x-8 -inset-y-10 z-0 pointer-events-none blur-[48px]"
            style={{ background: "radial-gradient(closest-side, rgba(96,165,250,0.16), transparent 75%)" }} />
          <div className="relative z-10 rounded-[var(--tt-radius-lg)] overflow-hidden border border-[var(--tt-border-strong)] bg-[var(--tt-panel)] shadow-[0_40px_120px_-36px_rgba(96,165,250,0.32)]">
            <div className="flex items-center gap-1.5 h-9 px-3 bg-[var(--tt-raised)] border-b border-[var(--tt-border)]">
              <span className="w-2.5 h-2.5 rounded-full bg-rose-400/50" />
              <span className="w-2.5 h-2.5 rounded-full bg-amber-400/50" />
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-400/50" />
              <span className="ml-2.5 inline-flex items-center gap-1.5 h-[21px] px-2.5 rounded-md bg-[var(--tt-sunken)] font-mono text-[10.5px] text-[var(--tt-fg-dim)]">
                {resolved ? (
                  <>
                    <Lock size={10} className="text-[var(--tt-success-fg,#10b981)]" /> localhost:3000
                  </>
                ) : (
                  <>~ tokentelemetry</>
                )}
              </span>
            </div>
            <div className="relative aspect-[16/11] sm:aspect-[16/9] overflow-hidden bg-[var(--tt-sunken)]">
              {/* No `initial` on the screenshot: SSR/no-JS paint it at full
                  opacity; the boot only dims it after hydration in view. */}
              <motion.img
                src="/screenshots/dashboard.png" width={3200} height={3000}
                alt="TokenTelemetry dashboard showing live token usage across detected agents"
                className="block w-full h-auto object-cover object-top"
                loading="lazy" decoding="async"
                animate={{ opacity: resolved ? 1 : 0.25, scale: resolved ? 1 : 0.985 }}
                transition={{ type: "spring", stiffness: 260, damping: 32 }}
              />
              <AnimatePresence>
                {!resolved && (
                  <motion.div
                    key={`boot-${run}`}
                    aria-hidden
                    initial={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.4, ease: EASE }}
                    className="pointer-events-none absolute inset-0 p-4 sm:p-6 font-mono text-[12px] sm:text-[13px] leading-[2.05] text-left"
                    style={{ background: "color-mix(in srgb, var(--tt-sunken) 82%, transparent)" }}
                  >
                    <div className="text-[var(--tt-fg)]">
                      <span className="text-[var(--tt-fg-faint)] select-none mr-2">$</span>
                      {BOOT_CMD.slice(0, typedLen)}
                      <span className="inline-block w-[7px] h-[13px] ml-0.5 align-middle bg-[var(--tt-fg-muted)]" />
                    </div>
                    {BOOT_LINES.slice(0, lineCount).map((l, i) => (
                      <motion.div
                        key={`${run}-${i}`}
                        initial={{ opacity: 0, x: -12 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: DUR.line, ease: EASE }}
                        className="flex items-center gap-2 text-[var(--tt-fg-muted)]"
                      >
                        {l.url ? (
                          <span className="text-[var(--tt-brand)]">→ {l.text}</span>
                        ) : (
                          <>
                            <span
                              className="tt-glow-ping w-1.5 h-1.5 rounded-full shrink-0"
                              style={{ backgroundColor: l.dot, "--tt-glow": l.dot } as CSSProperties}
                            />
                            <span>
                              <span className="text-[var(--tt-success-fg,#10b981)] mr-1.5">✓</span>
                              {l.text}
                            </span>
                          </>
                        )}
                      </motion.div>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
            {replayReady && (
              <motion.button
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: DUR.fade }}
                onClick={replay}
                aria-label="Replay the boot sequence"
                className="absolute z-20 bottom-2.5 right-3 font-mono text-[11px] text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)] transition-colors"
              >
                ↻ replay
              </motion.button>
            )}
          </div>
          {tagsOn && (
            <>
              <motion.span
                key={`tag-lock-${run}`}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={SPRING.pop}
                className="hidden lg:inline-flex items-center gap-1.5 absolute z-20 top-[14%] -left-6 px-2.5 py-1.5 rounded-[var(--tt-radius)] text-[11.5px] font-semibold text-[#86efac] border border-[var(--tt-border-strong)] backdrop-blur shadow-[0_12px_30px_-14px_rgba(0,0,0,0.7)]"
                style={{ background: "color-mix(in srgb, var(--tt-overlay) 92%, transparent)" }}
              >
                <Lock size={13} className="text-[var(--tt-success-fg,#10b981)]" /> 0 bytes leave your machine
              </motion.span>
              <CostTag key={`tag-cost-${run}`} run={run} delay={0.15} />
            </>
          )}
        </div>
      </div>
    </section>
  );
}
