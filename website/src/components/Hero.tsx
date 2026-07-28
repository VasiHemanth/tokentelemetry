"use client";
/**
 * Hero — full-viewport mission control. A canvas token-field streams
 * agent-colored tokens into a localhost core on the right; the left column
 * is editorial: massive stacked headline, terse facts, install command.
 * The CTA block renders static so it's interactive at first paint.
 */
import { useState } from "react";
import { Copy, Check, Star } from "lucide-react";
import { track } from "@/lib/track";
import { useGithubStats } from "@/lib/useGithubStats";
import TokenField from "@/components/TokenField";
import { Stagger, StaggerItem } from "@/components/motion";

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
    <section className="relative overflow-hidden min-h-[calc(100svh-3.5rem)] flex flex-col">
      {/* Token stream canvas — the section background */}
      <TokenField className="absolute inset-0 w-full h-full" />
      {/* Legibility scrim over the text column */}
      <div aria-hidden className="pointer-events-none absolute inset-0 z-[1]"
        style={{ background: "radial-gradient(720px 560px at 22% 45%, rgba(10,12,16,0.88), rgba(10,12,16,0.35) 60%, transparent 78%)" }} />

      {/* localhost core label — sits on the canvas ring (74% / 50%, see TokenField) */}
      <div aria-hidden className="hidden lg:flex absolute z-[2] left-[74%] top-1/2 -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-2">
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-[var(--tt-border-strong)] bg-[color-mix(in_srgb,var(--tt-panel)_88%,transparent)] backdrop-blur font-mono text-[11px] text-[var(--tt-fg-muted)]">
          <span className="relative flex w-1.5 h-1.5">
            <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-400" />
          </span>
          localhost:3000
        </span>
      </div>

      <div className="relative z-[3] flex-1 flex items-center max-w-[1180px] w-full mx-auto px-5 py-14 sm:py-16">
        <div className="max-w-[720px]">
          {/* Facts line — mono, no chips */}
          <p className="font-mono text-[11.5px] tracking-[0.16em] uppercase text-[var(--tt-fg-dim)] mb-6 sm:mb-8">
            <span className="text-[var(--tt-brand)]">00 · observe</span>
            <span className="mx-2 text-[var(--tt-fg-faint)]">/</span>
            local-first telemetry for 13 coding agents
          </p>

          {/* Stacked editorial headline */}
          <Stagger gap={80} y={24} className="mb-6 sm:mb-8">
            <h1 className="text-[clamp(46px,9.2vw,118px)] leading-[0.95] tracking-[-0.05em] font-semibold">
              <StaggerItem className="block text-[var(--tt-fg)]">Every token.</StaggerItem>
              <StaggerItem className="block text-[var(--tt-fg)]">Every agent.</StaggerItem>
              <StaggerItem className="block bg-gradient-to-r from-[#86efac] to-[#34d399] bg-clip-text text-transparent pb-[0.08em]">
                Your machine.
              </StaggerItem>
            </h1>
            <StaggerItem y={16}>
              <p className="mt-6 text-[clamp(15px,1.8vw,18px)] text-[var(--tt-fg-muted)] leading-relaxed max-w-[560px]">
                TokenTelemetry reads the logs Claude Code, Codex, Cursor, Gemini CLI
                and 9 other coding agents already write, and turns them into one live
                local dashboard — cost, tokens, traces. No SDK, no signup, and
                nothing leaves your computer.
              </p>
            </StaggerItem>
          </Stagger>

          {/* CTA — static, interactive at first paint */}
          <div id="install" className="scroll-mt-24 max-w-[620px]">
            <div className="flex items-center gap-1 mb-2">
              {(["mac", "win"] as const).map((k) => (
                <button key={k} onClick={() => chooseOs(k)}
                  className={`h-7 px-3 rounded-[var(--tt-radius-sm)] font-mono text-[11.5px] tracking-[-0.01em] transition-colors ${
                    os === k ? "bg-white/[0.07] text-[var(--tt-fg)]" : "text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)]"
                  }`}>
                  {k === "mac" ? "macOS / Linux" : "Windows"}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-1.5 p-1 rounded-[var(--tt-radius-lg)] border border-[var(--tt-border-strong)] bg-[color-mix(in_srgb,var(--tt-sunken)_92%,transparent)] backdrop-blur">
              <code className="flex-1 min-w-0 px-3 py-2.5 font-mono text-[13px] text-[var(--tt-fg)] overflow-x-auto whitespace-nowrap [scrollbar-width:none]">
                <span className="text-[var(--tt-fg-faint)] select-none mr-2">$</span>{INSTALL[os]}
              </code>
              <button onClick={copy}
                className="shrink-0 inline-flex items-center gap-1.5 h-[40px] px-4 rounded-[var(--tt-radius)] text-[12.5px] font-semibold transition-colors bg-[var(--tt-brand-strong)] text-white hover:bg-[var(--tt-brand)] shadow-[0_8px_22px_-12px_var(--tt-brand-glow)]"
                aria-label={copied ? "Copied" : "Copy install command"}>
                {copied ? <Check size={14} /> : <Copy size={14} />}
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
              <a
                href={GITHUB_URL}
                target="_blank" rel="noopener noreferrer"
                onClick={() => track("click_github", { location: "hero" })}
                className="inline-flex items-center gap-2 h-10 px-4 rounded-[var(--tt-radius)] text-[13.5px] font-semibold bg-[color-mix(in_srgb,var(--tt-raised)_88%,transparent)] backdrop-blur text-[var(--tt-fg)] border border-[var(--tt-border-strong)] hover:border-[var(--tt-brand)] transition-colors"
              >
                <Star size={15} className="text-[var(--tt-warn)]" fill="currentColor" />
                Star on GitHub
                <span className="pl-2.5 border-l border-white/10 text-[12.5px] font-medium text-[var(--tt-fg-muted)]">{stars} ★</span>
              </a>
              <p className="font-mono text-[11px] text-[var(--tt-fg-dim)]">
                MIT · runs offline · Node 18+, Python 3.9+
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Scroll cue */}
      <div className="relative z-[3] max-w-[1180px] w-full mx-auto px-5 pb-5">
        <p aria-hidden className="font-mono text-[11px] tracking-[0.16em] uppercase text-[var(--tt-fg-faint)]">
          ↓ 01 · burn
        </p>
      </div>
    </section>
  );
}
