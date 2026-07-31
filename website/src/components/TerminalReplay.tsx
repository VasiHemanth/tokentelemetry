"use client";
import { useEffect, useRef, useState } from "react";
import { Activity } from "lucide-react";
import { motion, useInView, useReducedMotion } from "motion/react";
import { DUR } from "@/components/motion";
import {
  TERMINAL_SCRIPT,
  SCRIPT_DURATION_MS,
  REPLAY_HOLD_MS,
  COST_LINE_DELAY_MS,
  type ScriptLine,
} from "@/data/terminal-script";

const COLOR: Record<ScriptLine["kind"], string> = {
  header:    "text-[var(--tt-fg-faint)]",
  user:      "text-[#60a5fa]",
  reasoning: "text-[var(--tt-warn-fg)] italic",
  tool:      "text-[var(--tt-info-fg)]",
  result:    "text-[var(--tt-fg-dim)]",
  cost:      "text-[var(--tt-success-fg)]",
};

export type TerminalReplayProps = {
  /** Fires each time the cost line prints (once per loop). */
  onCostLine?: () => void;
  /** Fires when the replay wraps back to the start of the script. */
  onLoop?: () => void;
};

/**
 * Replays the session script while at least 40% in view; pauses off-screen and
 * resumes where it left off. Under reduced motion the full script renders
 * statically with a static cursor.
 */
export default function TerminalReplay({ onCostLine, onLoop }: TerminalReplayProps) {
  const frameRef = useRef<HTMLDivElement>(null);
  const inView = useInView(frameRef, { amount: 0.4 });
  const reduced = useReducedMotion();

  const [elapsed, setElapsed] = useState(0);
  const [loop, setLoop] = useState(0);
  const [pageVisible, setPageVisible] = useState(true);
  const elapsedRef = useRef(0);
  const costFiredRef = useRef(false);
  // Keep callbacks in a ref so the timer effect doesn't restart when the parent re-renders.
  const callbacksRef = useRef({ onCostLine, onLoop });
  callbacksRef.current = { onCostLine, onLoop };

  // Pause on a hidden tab, not just off-screen; the elapsed-resume math below
  // otherwise keeps advancing the replay (and firing callbacks) in background.
  useEffect(() => {
    const onVis = () => setPageVisible(!document.hidden);
    onVis();
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);

  useEffect(() => {
    if (reduced || !inView || !pageVisible) return;
    const cycle = SCRIPT_DURATION_MS + REPLAY_HOLD_MS;
    const start = Date.now() - elapsedRef.current;
    const id = setInterval(() => {
      const t = (Date.now() - start) % cycle;
      if (t < elapsedRef.current) {
        // Wrapped: new loop.
        costFiredRef.current = false;
        setLoop((n) => n + 1);
        callbacksRef.current.onLoop?.();
      }
      if (!costFiredRef.current && t >= COST_LINE_DELAY_MS) {
        costFiredRef.current = true;
        callbacksRef.current.onCostLine?.();
      }
      elapsedRef.current = t;
      setElapsed(t);
    }, 60);
    return () => clearInterval(id);
  }, [inView, reduced, pageVisible]);

  const visible = reduced ? TERMINAL_SCRIPT : TERMINAL_SCRIPT.filter((l) => l.delay <= elapsed);

  return (
    <div
      ref={frameRef}
      className="rounded-[var(--tt-radius-xl)] border border-[var(--tt-border-strong)] bg-[var(--tt-sunken)] overflow-hidden shadow-[0_30px_120px_-30px_rgba(96,165,250,0.35)]"
    >
      <div className="flex items-center gap-1.5 px-4 h-9 bg-[var(--tt-raised)] border-b border-[var(--tt-border)]">
        <span className="w-2.5 h-2.5 rounded-full bg-rose-400/50" />
        <span className="w-2.5 h-2.5 rounded-full bg-amber-400/50" />
        <span className="w-2.5 h-2.5 rounded-full bg-emerald-400/50" />
        <span className="ml-3 inline-flex items-center gap-1.5 text-[11px] font-mono text-[var(--tt-fg-dim)] truncate">
          <Activity size={11} className="text-[var(--tt-brand)]" /> tokentelemetry · session-trace
        </span>
      </div>
      <div className="p-5 sm:p-6 font-mono text-[12px] sm:text-[13px] leading-relaxed min-h-[320px] sm:min-h-[360px] space-y-1.5">
        {visible.map((line, i) =>
          reduced ? (
            <div key={i} className={COLOR[line.kind]}>
              {line.text}
            </div>
          ) : (
            <motion.div
              key={`${loop}-${i}`}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: DUR.line }}
              className={COLOR[line.kind]}
            >
              {line.text}
            </motion.div>
          ),
        )}
        <span className="inline-block w-2 h-4 bg-[var(--tt-success-fg)] align-middle animate-pulse motion-reduce:animate-none" />
      </div>
    </div>
  );
}
