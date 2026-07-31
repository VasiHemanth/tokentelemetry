"use client";
/**
 * 08 · ZERO — the emotional peak of the page. The source mockup said "No usage
 * tracking / no telemetry hidden anywhere" — that is false now that the app
 * ships opt-out anonymous telemetry (see docs/design/product-telemetry.md), so
 * every zero here is scoped truthfully to user DATA ("your logs, prompts &
 * costs"), and the telemetry disclosure stays on the page.
 *
 * Left: a giant SVG "0" that draws its stroke on scroll-in (useDrawable) with
 * a slow shimmer riding the stroke. Right: a terminal-style network monitor —
 * INBOUND file reads stream in, OUTBOUND stays empty, and every few seconds a
 * line tries to cross a dashed "your machine" boundary and is blocked with a
 * red flash. The whole product thesis in one animation.
 *
 * Loops run only while the panel is in view AND the document is visible.
 * Reduced motion / SSR / no-JS: static final state — inbound populated,
 * outbound empty, counter 0, boundary static, stroke fully drawn.
 */
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useInView } from "motion/react";
import { Lock, BarChart3, FileCode } from "lucide-react";
import { Reveal, Stagger, StaggerItem, useDrawable, useMotionOk, EASE_CSS } from "@/components/motion";

const INBOUND_READS = [
  "~/.claude/projects/acme/session.jsonl",
  "~/.codex/sessions/rollout-07-30.jsonl",
  "~/.gemini/tmp/chat-9f2c.json",
  "~/.hermes/kanban.db",
  "~/.claude/projects/acme/subagents.jsonl",
  "~/.opencode/storage/message/msg_512.json",
  "~/.hermes/logs/agent.log",
  "~/.codex/sessions/meta.json",
] as const;

const ATTEMPTS = ["session.jsonl", "prompt history", "cost report"] as const;

/** Static fill for SSR / no-JS / reduced motion. */
const STATIC_LINES = INBOUND_READS.slice(0, 6).map((text, i) => ({ id: i, text }));

const COMPACT_CARDS = [
  {
    icon: Lock,
    title: "Local & read-only",
    body: "Reads session logs from your filesystem, serves a UI on localhost, and never writes to your agent files.",
  },
  {
    icon: BarChart3,
    title: "Anonymous usage stats",
    body: "Content-free feature counts, on by default, one-click off. The exact payload is visible in Settings → Usage & privacy.",
  },
  {
    icon: FileCode,
    title: "MIT open source",
    body: "Read every line. The telemetry pipeline ships in the source with an allowlist test.",
  },
] as const;

type AttemptPhase = "advance" | "blocked" | "retreat";
type Attempt = { label: string; phase: AttemptPhase };
type LogLine = { id: number; text: string };

/** Giant "0": stroke draws itself on scroll-in, then a shimmer rides the stroke. */
function ZeroGlyph() {
  const svgRef = useRef<SVGSVGElement>(null);
  const inView = useDrawable(svgRef, { duration: 1100, amount: 0.5 });

  return (
    <div
      aria-hidden
      className="relative select-none"
      style={{ width: "clamp(130px, 20vw, 250px)" }}
    >
      <svg ref={svgRef} viewBox="0 0 200 280" fill="none" className="block w-full h-auto">
        <defs>
          <linearGradient id="tt-zero-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#86efac" />
            <stop offset="100%" stopColor="#34d399" />
          </linearGradient>
        </defs>
        <ellipse cx="100" cy="140" rx="76" ry="116" stroke="url(#tt-zero-grad)" strokeWidth="22" />
      </svg>
      {/* Shimmer overlay lives in its own SVG so useDrawable's createDrawable
          never touches its dasharray. Hidden entirely under reduced motion. */}
      <svg viewBox="0 0 200 280" fill="none" className="absolute inset-0 block w-full h-auto pointer-events-none">
        <ellipse
          cx="100"
          cy="140"
          rx="76"
          ry="116"
          pathLength={100}
          stroke="rgba(240,253,244,0.55)"
          strokeWidth="22"
          strokeLinecap="round"
          strokeDasharray="10 90"
          className={inView ? "tt-zero-shimmer" : "opacity-0"}
        />
      </svg>
    </div>
  );
}

/** Terminal-style live proof panel: inbound reads vs an empty outbound column. */
function ZeroOutboundMonitor() {
  const frameRef = useRef<HTMLDivElement>(null);
  const inView = useInView(frameRef, { amount: 0.3 });
  const motionOn = useMotionOk();

  const [lines, setLines] = useState<LogLine[]>([]);
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [flash, setFlash] = useState(false);
  const [blockedCount, setBlockedCount] = useState(0);
  const [pageVisible, setPageVisible] = useState(true);

  const readIdxRef = useRef(0);
  const attemptIdxRef = useRef(0);
  const lineIdRef = useRef(100); // offset from STATIC_LINES ids

  useEffect(() => {
    const onVis = () => setPageVisible(!document.hidden);
    onVis();
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);

  const live = motionOn && inView && pageVisible;

  useEffect(() => {
    if (!live) return;
    let tick = 0;
    const timeouts: number[] = [];
    const id = window.setInterval(() => {
      tick += 1;
      const text = INBOUND_READS[readIdxRef.current % INBOUND_READS.length];
      readIdxRef.current += 1;
      const lineId = lineIdRef.current++;
      setLines((prev) => [...prev, { id: lineId, text }].slice(-7));

      if (tick % 5 === 0) {
        const label = ATTEMPTS[attemptIdxRef.current % ATTEMPTS.length];
        attemptIdxRef.current += 1;
        setAttempt({ label, phase: "advance" });
        timeouts.push(
          window.setTimeout(() => {
            setAttempt((a) => (a ? { ...a, phase: "blocked" } : a));
            setFlash(true);
            setBlockedCount((n) => n + 1);
          }, 560)
        );
        timeouts.push(
          window.setTimeout(() => {
            setFlash(false);
            setAttempt((a) => (a ? { ...a, phase: "retreat" } : a));
          }, 940)
        );
        timeouts.push(window.setTimeout(() => setAttempt(null), 1450));
      }
    }, 1100);
    return () => {
      window.clearInterval(id);
      timeouts.forEach(window.clearTimeout);
    };
  }, [live]);

  const shownLines = motionOn ? lines : STATIC_LINES;

  const chipStyle: React.CSSProperties =
    attempt?.phase === "blocked"
      ? { transform: "translateX(5px)", opacity: 1, transition: "transform 120ms ease-out" }
      : attempt?.phase === "retreat"
        ? { transform: "translateX(-72px)", opacity: 0, transition: `transform 420ms ${EASE_CSS}, opacity 380ms ease-out` }
        : { transform: "translateX(0)", opacity: 1 };

  return (
    <div
      ref={frameRef}
      role="img"
      aria-label="Live illustration: local file reads stream in; outbound requests carrying your logs, prompts, or costs stay at zero, blocked at the machine boundary."
      className="rounded-[var(--tt-radius-xl)] border border-[var(--tt-border-strong)] bg-[var(--tt-sunken)] overflow-hidden shadow-[0_30px_120px_-30px_rgba(16,185,129,0.3)]"
    >
      <div className="flex items-center gap-1.5 px-4 h-9 bg-[var(--tt-raised)] border-b border-[var(--tt-border)]" aria-hidden>
        <span className="w-2.5 h-2.5 rounded-full bg-rose-400/50" />
        <span className="w-2.5 h-2.5 rounded-full bg-amber-400/50" />
        <span className="w-2.5 h-2.5 rounded-full bg-emerald-400/50" />
        <span className="ml-2 font-mono text-[11px] text-[var(--tt-fg-dim)]">tt-network-monitor — localhost</span>
      </div>

      <div className="relative flex font-mono text-[11.5px] leading-[1.9]" aria-hidden>
        {/* INBOUND */}
        <div className="flex-1 min-w-0 px-4 py-3 flex flex-col h-[272px]">
          <p className="text-[10px] tracking-[0.16em] uppercase text-[var(--tt-fg-dim)] mb-1 shrink-0">
            inbound · local reads
          </p>
          <div className="flex-1 min-h-0 overflow-hidden flex flex-col justify-end pb-8">
            {shownLines.map((l) => (
              <p key={l.id} className={`truncate text-[var(--tt-fg-muted)] ${motionOn ? "tt-line-in" : ""}`}>
                <span className="text-[var(--tt-fg-faint)]">read </span>
                {l.text}
                <span className="text-[var(--tt-success)]"> ok</span>
              </p>
            ))}
          </div>
        </div>

        {/* Boundary */}
        <div className="relative w-10 shrink-0 flex items-center justify-center">
          <svg className="absolute inset-y-0 left-1/2 -translate-x-1/2 h-full w-[2px] overflow-visible">
            <line
              x1="1"
              y1="0"
              x2="1"
              y2="100%"
              strokeWidth="2"
              strokeDasharray="6 6"
              className={live ? "tt-dash-live" : ""}
              style={{
                stroke: flash ? "var(--tt-danger)" : "rgba(148,163,184,0.45)",
                transition: "stroke 150ms ease-out",
              }}
            />
          </svg>
          {/* Red flash glow when an attempt is blocked. */}
          <div
            className="absolute inset-y-0 -inset-x-3 pointer-events-none"
            style={{
              background: "radial-gradient(60px 140px at 50% 55%, rgba(244,63,94,0.35), transparent 70%)",
              opacity: flash ? 1 : 0,
              transition: "opacity 160ms ease-out",
            }}
          />
          <span
            className="relative z-10 px-0.5 py-2 bg-[var(--tt-sunken)] text-[9.5px] tracking-[0.2em] uppercase text-[var(--tt-fg-dim)]"
            style={{ writingMode: "vertical-rl" }}
          >
            your machine
          </span>
        </div>

        {/* OUTBOUND */}
        <div className="flex-1 min-w-0 px-4 py-3 flex flex-col h-[272px]">
          <p className="text-[10px] tracking-[0.16em] uppercase text-[var(--tt-fg-dim)] mb-1 shrink-0">
            outbound · leaves this machine
          </p>
          <div className="flex-1 min-h-0 flex flex-col">
            <p className="text-[var(--tt-fg-faint)] italic mt-1">
              no entries{" "}
              <span className="not-italic inline-block w-[7px] h-[12px] align-middle bg-[var(--tt-success)] tt-pulse" />
            </p>
            <div className="mt-auto">
              <p className="text-[var(--tt-fg-muted)]">
                your logs, prompts &amp; costs:{" "}
                <span className="text-[var(--tt-success)] font-semibold">0</span>
              </p>
              <p className="text-[var(--tt-fg-faint)]">
                blocked at boundary: <span className="tabular-nums">{blockedCount}</span>
              </p>
            </div>
          </div>
        </div>

        {/* The escaping line, blocked at the boundary. Anchored so its right
            edge sits just left of the dashed line at translateX(0). */}
        {attempt && (
          <div
            className={`absolute top-[52%] whitespace-nowrap rounded border px-2 py-0.5 text-[10.5px] ${
              attempt.phase === "advance" ? "tt-chip-in" : ""
            } ${
              attempt.phase === "blocked"
                ? "border-[rgba(244,63,94,0.6)] text-[#fda4af] bg-[rgba(244,63,94,0.12)]"
                : "border-[var(--tt-border-strong)] text-[var(--tt-fg-muted)] bg-[var(--tt-raised)]"
            }`}
            style={{ right: "calc(50% + 26px)", ...chipStyle }}
          >
            {attempt.label} → cloud{attempt.phase === "blocked" ? "  ✕" : " …"}
          </div>
        )}
      </div>

      <style>{`
        .tt-zero-shimmer { opacity: 0; }
        @media (prefers-reduced-motion: no-preference) {
          .tt-zero-shimmer {
            opacity: 1;
            animation: tt-zero-shimmer 3.8s linear 1.1s infinite;
          }
          .tt-dash-live { animation: tt-dash-march 1.2s linear infinite; }
          .tt-line-in { animation: tt-line-in 0.2s ${EASE_CSS} both; }
          .tt-chip-in { animation: tt-chip-in 0.5s ${EASE_CSS} both; }
        }
        @keyframes tt-zero-shimmer { from { stroke-dashoffset: 100; } to { stroke-dashoffset: 0; } }
        @keyframes tt-dash-march { from { stroke-dashoffset: 0; } to { stroke-dashoffset: -24; } }
        @keyframes tt-line-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes tt-chip-in { from { opacity: 0; transform: translateX(-64px); } to { opacity: 1; transform: translateX(0); } }
      `}</style>
    </div>
  );
}

export default function Privacy() {
  return (
    <section
      id="zero"
      className="scroll-mt-[82px] relative border-t border-[var(--tt-border)]"
      style={{ background: "radial-gradient(900px 420px at 50% 0%, rgba(16,185,129,0.06), transparent 65%)" }}
    >
      <div className="max-w-[1180px] mx-auto px-5 py-16 sm:py-24">
        <div className="border-t border-[var(--tt-border)] pt-5">
          <p className="font-mono text-[11.5px] tracking-[0.16em] uppercase text-[var(--tt-fg-dim)] mb-6 sm:mb-9">
            <span className="text-[#34d399]">08</span> · zero
          </p>

          <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)] gap-x-12 gap-y-10 items-center">
            {/* The number IS the headline. */}
            <Reveal y={16}>
              <ZeroGlyph />
              <h2 className="mt-6 text-[clamp(28px,3.6vw,44px)] leading-[1.02] tracking-[-0.035em] font-semibold text-[var(--tt-fg)] text-balance">
                <span className="sr-only">Zero </span>
                Logs, prompts, and costs that leave your machine.
              </h2>
              <p className="mt-4 text-[clamp(15px,1.7vw,17px)] text-[var(--tt-fg-muted)] leading-relaxed max-w-[480px]">
                No cloud, no accounts. The app reads your agent logs from disk
                and serves a dashboard on localhost. That&apos;s the whole
                architecture.
              </p>
            </Reveal>

            <Reveal y={24} delay={0.1}>
              <ZeroOutboundMonitor />
              <p className="mt-4 text-[13px] text-[var(--tt-fg-dim)] leading-relaxed">
                Honest exception: the app sends anonymous, content-free usage
                stats (which features you use — never code, prompts, paths, or
                costs). One-click off in Settings → Usage &amp; privacy, or set{" "}
                <code className="font-mono text-[12px] text-[var(--tt-fg-muted)] bg-[var(--tt-sunken)] px-1.5 py-0.5 rounded">DO_NOT_TRACK=1</code>.{" "}
                <Link
                  href="/privacy"
                  className="text-[var(--tt-fg)] underline underline-offset-2 hover:text-[var(--tt-brand)] transition-colors"
                >
                  Read the policy
                </Link>
                .
              </p>
            </Reveal>
          </div>
        </div>

        <Stagger gap={80} y={16} className="mt-10 sm:mt-14 grid grid-cols-1 md:grid-cols-3 gap-3 sm:gap-4">
          {COMPACT_CARDS.map(({ icon: Icon, title, body }) => (
            <StaggerItem key={title}>
              <div className="h-full flex items-start gap-3 p-4 rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)]">
                <div className="w-[30px] h-[30px] shrink-0 rounded-[var(--tt-radius)] grid place-items-center bg-[rgba(16,185,129,0.1)] border border-[rgba(16,185,129,0.25)]">
                  <Icon size={15} className="text-[var(--tt-success-fg,#10b981)]" />
                </div>
                <div>
                  <h3 className="text-[13.5px] font-semibold tracking-[-0.01em] text-[var(--tt-fg)] mb-1">{title}</h3>
                  <p className="text-[12.5px] text-[var(--tt-fg-muted)] leading-relaxed">{body}</p>
                </div>
              </div>
            </StaggerItem>
          ))}
        </Stagger>
      </div>
    </section>
  );
}
