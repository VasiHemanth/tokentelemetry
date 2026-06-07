"use client";
import { useEffect, useState } from "react";
import { Copy, Check, GitBranch, ArrowRight } from "lucide-react";
import TerminalReplay from "./TerminalReplay";

const PAINS = [
  "Why did that Codex run cost $4.20?",
  "Which agent actually finished the task?",
  "What was Claude Code thinking for 40 seconds?",
];

const INSTALL: Record<"mac" | "windows", string> = {
  mac:     `curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash`,
  windows: `irm https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.ps1 | iex`,
};

export default function Hero() {
  const [pain, setPain] = useState(0);
  const [copied, setCopied] = useState(false);
  const [os, setOs] = useState<"mac" | "windows">("mac");

  useEffect(() => {
    const id = setInterval(() => setPain((p) => (p + 1) % PAINS.length), 3500);
    return () => clearInterval(id);
  }, []);

  const copy = () => {
    navigator.clipboard?.writeText(INSTALL[os]);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <section className="relative overflow-hidden">
      <div className="max-w-[1320px] mx-auto px-5 sm:px-8 pt-12 sm:pt-24 pb-8 sm:pb-16">
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-12 lg:items-center">
          {/* Left column — copy + install */}
          <div className="lg:text-left text-center">
            {/* Eyebrow */}
            <div className="flex lg:justify-start justify-center mb-3 gap-2 flex-wrap">
              <span className="inline-flex items-center gap-2 px-2.5 h-7 rounded-full text-[11px] font-medium tracking-tight text-[var(--tt-fg-muted)] bg-[var(--tt-panel)] border border-[var(--tt-border)]">
                <span className="relative flex w-1.5 h-1.5">
                  <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
                  <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-400" />
                </span>
                100% local
                <span className="text-[var(--tt-fg-faint)]">·</span>
                open source
                <span className="text-[var(--tt-fg-faint)]">·</span>
                MIT
              </span>
              <a
                href="#hermes"
                className="inline-flex items-center gap-2 px-2.5 h-7 rounded-full text-[11px] font-medium tracking-tight text-[#eab308] bg-[#eab308]/8 border border-[#eab308]/30 hover:bg-[#eab308]/12 transition-colors"
              >
                New
                <span className="text-[#eab308]/50">·</span>
                Hermes Agent observability
                <ArrowRight size={11} />
              </a>
            </div>
            <div className="h-3" />

            {/* Headline */}
            <h1 className="text-[32px] sm:text-[52px] lg:text-[58px] xl:text-[64px] leading-[1.08] sm:leading-[1.04] tracking-[-0.025em] font-semibold text-[var(--tt-fg)] mb-5 max-w-4xl mx-auto lg:mx-0">
              <span className="block text-[13px] sm:text-[14px] font-medium tracking-[0.04em] text-[var(--tt-fg-dim)] uppercase mb-3">
                Token Telemetry
              </span>
              See exactly what your{" "}
              <span className="text-[var(--tt-brand)]">coding &amp; autonomous agents</span>{" "}
              cost, think, and do.
            </h1>

            {/* Subhead */}
            <p className="text-[15px] sm:text-[17px] text-[var(--tt-fg-muted)] max-w-2xl mx-auto lg:mx-0 leading-relaxed mb-3">
              Local, read-only observability for Claude Code, Codex, Gemini CLI, Cursor, Copilot, Antigravity,
              Qwen CLI, OpenCode, Grok Build, Hermes Agent, and Vibe — one command, no signup, your logs never leave your machine.
            </p>
            <p className="text-[13px] sm:text-[14px] text-[var(--tt-fg-dim)] font-mono italic mb-9 transition-opacity">
              &ldquo;{PAINS[pain]}&rdquo;
            </p>

            {/* Install + CTAs */}
            <div className="max-w-2xl mx-auto lg:mx-0">
              <div className="flex lg:justify-start justify-center items-center gap-1 mb-2 text-[11px]">
                {(["mac", "windows"] as const).map((k) => (
                  <button
                    key={k}
                    onClick={() => setOs(k)}
                    className={`h-7 px-3 rounded-md font-medium tracking-tight transition-colors ${
                      os === k
                        ? "tt-tint-2 text-[var(--tt-fg)]"
                        : "text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)]"
                    }`}
                  >
                    {k === "mac" ? "macOS / Linux" : "Windows"}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-1 rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-sunken)] p-1">
                <pre className="flex-1 min-w-0 px-3 sm:px-4 py-2.5 font-mono text-[12px] sm:text-[13px] text-[var(--tt-fg)] overflow-x-auto whitespace-nowrap">
                  <span className="text-[var(--tt-fg-faint)] select-none mr-2">$</span>{INSTALL[os]}
                </pre>
                <button
                  onClick={copy}
                  className="m-1 inline-flex items-center gap-1.5 h-9 px-3 rounded-[var(--tt-radius)] tt-tint-2 hover:tt-tint-3 text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] text-[11px] font-medium transition-colors shrink-0"
                  aria-label={copied ? "Copied" : "Copy install command"}
                >
                  {copied ? <Check size={13} /> : <Copy size={13} />}
                  <span className="hidden sm:inline">{copied ? "Copied" : "Copy"}</span>
                </button>
              </div>
              <p className="mt-2 text-[11px] text-[var(--tt-fg-dim)] font-mono lg:text-left text-center">
                MIT licensed · runs offline · requires Node 18+, Python 3.9+
              </p>

              <div className="mt-6 flex flex-wrap items-center lg:justify-start justify-center gap-2">
                <a
                  href="https://github.com/VasiHemanth/tokentelemetry"
                  target="_blank" rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 h-10 px-4 rounded-[var(--tt-radius)] bg-[var(--tt-brand-strong)] hover:bg-[var(--tt-brand)] text-white font-medium text-[13px] shadow-[0_8px_24px_-12px_var(--tt-brand-glow)] transition-colors"
                >
                  <GitBranch size={14} /> View on GitHub
                </a>
                <a
                  href="#features"
                  className="inline-flex items-center gap-2 h-10 px-4 rounded-[var(--tt-radius)] tt-tint-1 hover:tt-tint-2 text-[var(--tt-fg)] border border-[var(--tt-border-strong)] font-medium text-[13px] transition-colors"
                >
                  See it in action <ArrowRight size={14} />
                </a>
              </div>
            </div>
          </div>

          {/* Right column — animated terminal (desktop only) */}
          <div className="hidden lg:block relative">
            <div aria-hidden className="absolute -inset-x-6 -top-8 -bottom-8 pointer-events-none bg-gradient-to-tr from-[color:var(--tt-brand-glow)] via-transparent to-transparent blur-3xl" />
            <div className="relative">
              <TerminalReplay />
            </div>
          </div>
        </div>

      </div>
    </section>
  );
}
