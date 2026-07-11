"use client";
import { useState } from "react";
import { Copy, Check, Star, Lock, Monitor, TrendingUp } from "lucide-react";
import { track } from "@/lib/track";
import { useGithubStats } from "@/lib/useGithubStats";

const GITHUB_URL = "https://github.com/VasiHemanth/tokentelemetry";

const INSTALL: Record<"mac" | "win", string> = {
  mac: "curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash",
  win: "irm https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.ps1 | iex",
};

export default function Hero() {
  const [os, setOs] = useState<"mac" | "win">("mac");
  const [copied, setCopied] = useState(false);
  const { stars } = useGithubStats();

  const chooseOs = (k: "mac" | "win") => { setOs(k); track("os_toggle", { os: k }); };
  const copy = () => {
    navigator.clipboard?.writeText(INSTALL[os]);
    setCopied(true);
    track("copy_install_command", { os });
    setTimeout(() => setCopied(false), 1500);
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
            <div className="flex flex-wrap gap-1.5 mb-5 justify-center lg:justify-start">
              <span className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-full text-[11.5px] font-medium text-[var(--tt-fg-muted)] bg-[var(--tt-panel)] border border-[var(--tt-border)]">
                <span className="relative flex w-1.5 h-1.5">
                  <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
                  <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-400" />
                </span>
                100% local
              </span>
              {["MIT open source", "13 agents", "No signup"].map((c) => (
                <span key={c} className="inline-flex items-center h-7 px-2.5 rounded-full text-[11.5px] font-medium text-[var(--tt-fg-muted)] bg-[var(--tt-panel)] border border-[var(--tt-border)]">
                  {c}
                </span>
              ))}
            </div>

            {/* Headline */}
            <h1 className="text-[clamp(33px,5.4vw,58px)] leading-[1.04] tracking-[-0.028em] font-semibold text-[var(--tt-fg)] mb-4 text-balance">
              See what your AI coding agents{" "}
              <span className="text-[var(--tt-brand)]">cost, think, and do</span> —{" "}
              <span className="bg-gradient-to-r from-[#86efac] to-[#34d399] bg-clip-text text-transparent">
                100% on your machine.
              </span>
            </h1>

            {/* Subhead */}
            <p className="text-[clamp(15px,1.7vw,17px)] text-[var(--tt-fg-muted)] leading-relaxed max-w-[540px] mx-auto lg:mx-0 mb-6">
              Read-only observability for Claude Code, Codex, Cursor, Gemini CLI &amp; 9 more. It reads the logs
              your agents already write — no SDK, no signup, and your data never leaves your computer.
            </p>

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

          {/* ── Hero visual ── */}
          <div className="relative max-w-[620px] mx-auto lg:max-w-none w-full lg:scale-[1.04] lg:origin-left">
            <div aria-hidden className="absolute -inset-x-5 -inset-y-8 z-0 pointer-events-none blur-[40px]"
              style={{ background: "radial-gradient(closest-side, rgba(96,165,250,0.2), transparent 75%)" }} />
            <div className="relative z-10 rounded-[var(--tt-radius-lg)] overflow-hidden border border-[var(--tt-border-strong)] bg-[var(--tt-panel)] shadow-[0_40px_120px_-36px_rgba(96,165,250,0.32)]">
              <div className="flex items-center gap-1.5 h-9 px-3 bg-[var(--tt-raised)] border-b border-[var(--tt-border)]">
                <span className="w-2.5 h-2.5 rounded-full bg-rose-400/50" />
                <span className="w-2.5 h-2.5 rounded-full bg-amber-400/50" />
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-400/50" />
                <span className="ml-2.5 inline-flex items-center gap-1.5 h-[21px] px-2.5 rounded-md bg-[var(--tt-sunken)] font-mono text-[10.5px] text-[var(--tt-fg-dim)]">
                  <Lock size={10} className="text-[var(--tt-success-fg,#10b981)]" /> localhost:3000
                </span>
              </div>
              <div className="aspect-[16/12] sm:aspect-[16/11] overflow-hidden bg-[var(--tt-sunken)]">
                <img src="/screenshots/dashboard.png" width={3200} height={3000}
                  alt="TokenTelemetry dashboard showing live token usage across detected agents"
                  className="block w-full h-auto object-cover object-top" loading="eager" decoding="async" />
              </div>
            </div>
            {/* Floating tags (desktop) */}
            <span className="hidden lg:inline-flex items-center gap-1.5 absolute z-20 top-[14%] -left-5 px-2.5 py-1.5 rounded-[var(--tt-radius)] text-[11.5px] font-semibold text-[#86efac] border border-[var(--tt-border-strong)] backdrop-blur shadow-[0_12px_30px_-14px_rgba(0,0,0,0.7)]"
              style={{ background: "color-mix(in srgb, var(--tt-overlay) 92%, transparent)" }}>
              <Lock size={13} className="text-[var(--tt-success-fg,#10b981)]" /> 0 bytes leave your machine
            </span>
            <span className="hidden lg:inline-flex items-center gap-1.5 absolute z-20 bottom-[16%] -right-4 px-2.5 py-1.5 rounded-[var(--tt-radius)] text-[11.5px] font-semibold text-[#fbbf24] border border-[var(--tt-border-strong)] backdrop-blur shadow-[0_12px_30px_-14px_rgba(0,0,0,0.7)]"
              style={{ background: "color-mix(in srgb, var(--tt-overlay) 92%, transparent)" }}>
              <TrendingUp size={13} className="text-[var(--tt-warn)]" /> $599 burned · last 90 days
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}
