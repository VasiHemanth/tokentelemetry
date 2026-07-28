"use client";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Copy, Check, Star, Lock, Monitor, TrendingUp } from "lucide-react";
import { track } from "@/lib/track";
import { useGithubStats } from "@/lib/useGithubStats";
import {
  CountUp,
  Reveal,
  Stagger,
  useDrawable,
  motionOk,
  EASE,
  DUR,
  SPRING,
} from "@/components/motion";

const GITHUB_URL = "https://github.com/VasiHemanth/tokentelemetry";

const INSTALL: Record<"mac" | "win", string> = {
  mac: "curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash",
  win: "irm https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.ps1 | iex",
};

/**
 * Boot script for the hero's scan overlay. The spec names this BOOT_SCRIPT in
 * terminal-script.ts; it lives here because the hero is its only consumer and
 * that data file belongs to the LiveTrace slice. Move it there if both end up
 * needing it.
 */
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
      className="hidden lg:inline-flex items-center gap-1.5 absolute z-20 bottom-[16%] -right-4 px-2.5 py-1.5 rounded-[var(--tt-radius)] text-[11.5px] font-semibold text-[#fbbf24] border border-[var(--tt-border-strong)] backdrop-blur shadow-[0_12px_30px_-14px_rgba(0,0,0,0.7)]"
      style={{ background: "color-mix(in srgb, var(--tt-overlay) 92%, transparent)" }}
    >
      <TrendingUp size={13} className="text-[var(--tt-warn)]" />
      <span>
        <CountUp key={run} to={599} prefix="$" duration={1100} /> burned · last 90 days
      </span>
      <svg
        ref={sparkRef}
        width="34"
        height="12"
        viewBox="0 0 34 12"
        fill="none"
        aria-hidden
        className="ml-0.5 shrink-0"
      >
        <path
          d="M1 10 L6 8.5 L11 9 L16 5.5 L21 6.5 L26 3 L33 1.5"
          stroke="var(--tt-brand)"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </motion.span>
  );
}

export default function Hero() {
  const [os, setOs] = useState<"mac" | "win">("mac");
  const [copied, setCopied] = useState(false);
  const { stars } = useGithubStats();
  const reduced = useReducedMotion();

  // Boot sequence state. SSR / no-JS / reduced motion all render the resolved
  // final state (screenshot at full opacity, tags mounted) — the effect below
  // only rewinds and replays it when motion is allowed.
  const [run, setRun] = useState(0);
  const [typedLen, setTypedLen] = useState(BOOT_CMD.length);
  const [lineCount, setLineCount] = useState(BOOT_LINES.length);
  const [resolved, setResolved] = useState(true);
  const [tagsOn, setTagsOn] = useState(true);
  const [replayReady, setReplayReady] = useState(false);

  useEffect(() => {
    if (!motionOk()) return; // reduced motion: final state, no replay button
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
  }, [run]);

  const chooseOs = (k: "mac" | "win") => { setOs(k); track("os_toggle", { os: k }); };
  const copy = () => {
    navigator.clipboard?.writeText(INSTALL[os]);
    setCopied(true);
    track("copy_install_command", { os });
    setTimeout(() => setCopied(false), 1500);
  };
  const replay = () => {
    track("feature_used", { name: "hero_replay" });
    setRun((r) => r + 1);
  };

  return (
    <section className="relative overflow-hidden">
      {/* Atmospheric glow + masked grid */}
      <div aria-hidden className="pointer-events-none absolute inset-0 z-0"
        style={{ background: "radial-gradient(900px 460px at 78% -8%, rgba(96,165,250,0.10), transparent 60%), radial-gradient(700px 420px at 8% 8%, rgba(168,85,247,0.055), transparent 62%)" }} />
      <div aria-hidden className="pointer-events-none absolute inset-0 z-0 opacity-50 tt-grid"
        style={{ maskImage: "radial-gradient(800px 500px at 50% 0%, #000, transparent 75%)", WebkitMaskImage: "radial-gradient(800px 500px at 50% 0%, #000, transparent 75%)" }} />

      <div className="relative z-10 max-w-[1180px] mx-auto px-5">
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,0.88fr)_minmax(0,1.12fr)] gap-8 lg:gap-10 lg:items-center pt-9 sm:pt-14 pb-6 sm:pb-10 text-center lg:text-left">
          {/* ── Copy + CTA ── */}
          <div>
            {/* Chips */}
            <Stagger gap={60} y={8} delay={0.1} className="flex flex-wrap gap-1.5 mb-5 justify-center lg:justify-start">
              <Stagger.Item>
                <span className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-full text-[11.5px] font-medium text-[var(--tt-fg-muted)] bg-[var(--tt-panel)] border border-[var(--tt-border)]">
                  <span className="relative flex w-1.5 h-1.5">
                    <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
                    <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-400" />
                  </span>
                  100% local
                </span>
              </Stagger.Item>
              {["MIT open source", "13 agents", "No signup"].map((c) => (
                <Stagger.Item key={c}>
                  <span className="inline-flex items-center h-7 px-2.5 rounded-full text-[11.5px] font-medium text-[var(--tt-fg-muted)] bg-[var(--tt-panel)] border border-[var(--tt-border)]">
                    {c}
                  </span>
                </Stagger.Item>
              ))}
            </Stagger>

            {/* Headline + subhead rise as one block. The CTA below stays
                static so it is interactive (and visible) at first paint. */}
            <Reveal y={16}>
              <h1 className="text-[clamp(33px,5.4vw,58px)] leading-[1.04] tracking-[-0.028em] font-semibold text-[var(--tt-fg)] mb-4 text-balance">
                See what your AI coding agents{" "}
                <span className="text-[var(--tt-brand)]">cost, think, and do</span> —{" "}
                <span className="bg-gradient-to-r from-[#86efac] to-[#34d399] bg-clip-text text-transparent">
                  100% on your machine.
                </span>
              </h1>
              <p className="text-[clamp(15px,1.7vw,17px)] text-[var(--tt-fg-muted)] leading-relaxed max-w-[540px] mx-auto lg:mx-0 mb-6">
                Read-only observability for Claude Code, Codex, Cursor, Gemini CLI &amp; 9 more. It reads the logs
                your agents already write — no SDK, no signup, and your data never leaves your computer.
              </p>
            </Reveal>

            {/* CTA — mobile: star primary; desktop: install primary */}
            <div id="install" className="scroll-mt-20 flex flex-col gap-3.5 max-w-[560px] mx-auto lg:mx-0">
              {/* Star button — order-1 on mobile, order-2 on desktop */}
              <a
                href={GITHUB_URL}
                target="_blank" rel="noopener noreferrer"
                onClick={() => track("click_github", { location: "hero" })}
                className="order-1 lg:order-2 self-stretch lg:self-start inline-flex items-center justify-center gap-2.5 h-[52px] lg:h-12 px-5 rounded-[var(--tt-radius)] text-[15px] lg:text-[14.5px] font-semibold transition-colors
                  bg-[var(--tt-brand-strong)] lg:bg-[var(--tt-raised)] text-white lg:text-[var(--tt-fg)] border border-transparent lg:border-[var(--tt-border-strong)] hover:bg-[var(--tt-brand)] lg:hover:bg-[var(--tt-overlay)] lg:hover:border-[var(--tt-brand)] shadow-[0_12px_30px_-14px_var(--tt-brand-glow)] lg:shadow-none"
              >
                <Star size={17} className="text-[#fde68a] lg:text-[var(--tt-warn)]" fill="currentColor" />
                Star on GitHub
                <span className="inline-flex items-center gap-1 pl-2.5 ml-0.5 border-l border-white/25 lg:border-[var(--tt-border2,rgba(255,255,255,0.1))] text-[13px] font-medium text-white/85 lg:text-[var(--tt-fg-muted)]">
                  {stars} ★
                </span>
              </a>

              {/* Install block — order-2 on mobile, order-1 on desktop */}
              <div className="order-2 lg:order-1 w-full">
                <div className="flex gap-1 mb-2 justify-center lg:justify-start">
                  {(["mac", "win"] as const).map((k) => (
                    <button key={k} onClick={() => chooseOs(k)}
                      className={`h-7 px-3 rounded-[var(--tt-radius-sm)] text-[11.5px] font-medium tracking-[-0.01em] transition-colors ${
                        os === k ? "bg-white/[0.07] text-[var(--tt-fg)]" : "text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)]"
                      }`}>
                      {k === "mac" ? "macOS / Linux" : "Windows"}
                    </button>
                  ))}
                </div>
                <div className="flex items-center gap-1.5 p-1 rounded-[var(--tt-radius-lg)] border border-[var(--tt-border-strong)] bg-[var(--tt-sunken)] max-sm:border-dashed">
                  <code className="flex-1 min-w-0 px-3 py-2 font-mono text-[13px] text-[var(--tt-fg)] overflow-x-auto whitespace-nowrap [scrollbar-width:none]">
                    <span className="text-[var(--tt-fg-faint)] select-none mr-2">$</span>{INSTALL[os]}
                  </code>
                  <button onClick={copy}
                    className="shrink-0 inline-flex items-center gap-1.5 h-[38px] px-3.5 rounded-[var(--tt-radius)] text-[12.5px] font-semibold transition-colors
                      bg-[var(--tt-brand-strong)] text-white hover:bg-[var(--tt-brand)] shadow-[0_8px_22px_-12px_var(--tt-brand-glow)]
                      max-sm:bg-[var(--tt-raised)] max-sm:text-[var(--tt-fg)] max-sm:border max-sm:border-[var(--tt-border-strong)] max-sm:shadow-none"
                    aria-label={copied ? "Copied" : "Copy install command"}>
                    {copied ? <Check size={14} /> : <Copy size={14} />}
                    {copied ? "Copied" : "Copy"}
                  </button>
                </div>
                <p className="mt-2 font-mono text-[11px] text-[var(--tt-fg-dim)] text-center lg:text-left">
                  MIT · runs offline · needs Node 18+, Python 3.9+
                </p>
                <div className="hidden max-sm:flex items-center gap-1.5 mt-2 text-[12px] text-[var(--tt-fg-dim)]">
                  <Monitor size={13} className="text-[var(--tt-brand)] shrink-0" />
                  <span>Runs on your desktop — copy it now, paste it when you&apos;re back at your machine.</span>
                </div>
              </div>
            </div>
          </div>

          {/* ── Hero visual: boot sequence resolves into the dashboard ── */}
          <div className="relative max-w-[620px] mx-auto lg:max-w-none w-full lg:scale-[1.04] lg:origin-left">
            <div aria-hidden className="absolute -inset-x-5 -inset-y-8 z-0 pointer-events-none blur-[40px]"
              style={{ background: "radial-gradient(closest-side, rgba(96,165,250,0.2), transparent 75%)" }} />
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
              <div className="relative aspect-[16/12] sm:aspect-[16/11] overflow-hidden bg-[var(--tt-sunken)]">
                {/* No `initial` on the screenshot: SSR/no-JS paint it at full
                    opacity (it's the LCP element); the boot only dims it after
                    hydration when motion is allowed. */}
                <motion.img
                  src="/screenshots/dashboard.png" width={3200} height={3000}
                  alt="TokenTelemetry dashboard showing live token usage across detected agents"
                  className="block w-full h-auto object-cover object-top"
                  loading="eager" decoding="async"
                  animate={{ opacity: resolved ? 1 : 0.25, scale: resolved ? 1 : 0.985 }}
                  transition={{ type: "spring", stiffness: 260, damping: 32 }}
                />
                {/* Scan overlay */}
                <AnimatePresence>
                  {!resolved && (
                    <motion.div
                      key={`boot-${run}`}
                      aria-hidden
                      initial={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.4, ease: EASE }}
                      className="pointer-events-none absolute inset-0 p-4 sm:p-5 font-mono text-[12px] sm:text-[12.5px] leading-[2] text-left"
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
              {/* Ghost replay affordance — only after the sequence finishes */}
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
            {/* Floating tags (desktop) */}
            {tagsOn && (
              <>
                <motion.span
                  key={`tag-lock-${run}`}
                  initial={reduced ? false : { opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={reduced ? { duration: DUR.fade } : SPRING.pop}
                  className="hidden lg:inline-flex items-center gap-1.5 absolute z-20 top-[14%] -left-5 px-2.5 py-1.5 rounded-[var(--tt-radius)] text-[11.5px] font-semibold text-[#86efac] border border-[var(--tt-border-strong)] backdrop-blur shadow-[0_12px_30px_-14px_rgba(0,0,0,0.7)]"
                  style={{ background: "color-mix(in srgb, var(--tt-overlay) 92%, transparent)" }}
                >
                  <Lock size={13} className="text-[var(--tt-success-fg,#10b981)]" /> 0 bytes leave your machine
                </motion.span>
                <CostTag key={`tag-cost-${run}`} run={run} delay={0.15} />
              </>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
