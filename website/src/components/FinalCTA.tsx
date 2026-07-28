"use client";
import { useState } from "react";
import { Star, Copy, Check } from "lucide-react";
import { track } from "@/lib/track";
import { useGithubStats } from "@/lib/useGithubStats";
import { BorderBeam, CountUp, Reveal } from "@/components/motion";

const GITHUB_URL = "https://github.com/VasiHemanth/tokentelemetry";
const INSTALL = "curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash";

/**
 * Final CTA: headline + buttons reveal at 40% in view, star count counts up
 * once (same recipe as ProofStrip), and the install block gets one 1200ms
 * BorderBeam revolution then goes static. Background glow stays static — the
 * page ends at rest. Reduced motion: no beam, final star number, opacity fade.
 */
export default function FinalCTA() {
  const [copied, setCopied] = useState(false);
  const { stars } = useGithubStats();
  const copy = () => {
    navigator.clipboard?.writeText(INSTALL);
    setCopied(true);
    track("copy_install_command", { os: "mac", location: "final" });
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <section className="relative overflow-hidden border-t border-[var(--tt-border)] text-center">
      <div aria-hidden className="pointer-events-none absolute inset-0 z-0"
        style={{ background: "radial-gradient(800px 380px at 50% 120%, rgba(96,165,250,0.14), transparent 62%)" }} />
      <Reveal y={16} amount={0.4} className="relative z-10 max-w-[680px] mx-auto px-5 py-14 sm:py-[72px]">
        <h2 className="text-[clamp(28px,4vw,46px)] leading-[1.06] tracking-[-0.028em] font-semibold text-[var(--tt-fg)] mb-4">
          Stop guessing what your agents cost.
        </h2>
        <p className="text-[16px] text-[var(--tt-fg-muted)] mb-7">
          Free, open source, 100% local. One command and you&apos;re looking at the numbers.
        </p>
        <div className="flex flex-wrap gap-3 justify-center max-w-[540px] mx-auto">
          <a
            href={GITHUB_URL}
            target="_blank" rel="noopener noreferrer"
            onClick={() => track("click_github", { location: "final" })}
            className="inline-flex items-center justify-center gap-2.5 h-12 px-5 rounded-[var(--tt-radius)] text-[14.5px] font-semibold bg-[var(--tt-raised)] text-[var(--tt-fg)] border border-[var(--tt-border-strong)] hover:border-[var(--tt-brand)] hover:bg-[var(--tt-overlay)] transition-colors"
          >
            <Star size={17} className="text-[var(--tt-warn)]" fill="currentColor" /> Star on GitHub
            <span className="pl-2.5 ml-0.5 border-l border-[rgba(255,255,255,0.1)] text-[13px] font-medium text-[var(--tt-fg-muted)]">
              <CountUp to={stars} duration={900} /> ★
            </span>
          </a>
          <BorderBeam className="flex-1 min-w-[280px] rounded-[var(--tt-radius-lg)]">
            <div className="flex items-center gap-1.5 p-1 rounded-[var(--tt-radius-lg)] border border-[var(--tt-border-strong)] bg-[var(--tt-sunken)]">
              <code className="flex-1 min-w-0 px-3 py-2 font-mono text-[13px] text-[var(--tt-fg)] overflow-x-auto whitespace-nowrap [scrollbar-width:none]">
                <span className="text-[var(--tt-fg-faint)] select-none mr-2">$</span>{INSTALL}
              </code>
              <button onClick={copy}
                className="shrink-0 inline-flex items-center gap-1.5 h-[38px] px-3.5 rounded-[var(--tt-radius)] bg-[var(--tt-brand-strong)] hover:bg-[var(--tt-brand)] text-white text-[12.5px] font-semibold shadow-[0_8px_22px_-12px_var(--tt-brand-glow)] transition-colors"
                aria-label={copied ? "Copied" : "Copy install command"}>
                {copied ? <Check size={14} /> : <Copy size={14} />}{copied ? "Copied" : "Copy"}
              </button>
            </div>
          </BorderBeam>
        </div>
      </Reveal>
    </section>
  );
}
