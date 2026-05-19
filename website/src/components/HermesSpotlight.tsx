import Link from "next/link";
import { ArrowRight } from "lucide-react";
import PluginInstallBlock from "./PluginInstallBlock";

// Inline caduceus — matches the icon shipped in the app's frontend so the
// brand is consistent between the marketing site and the dashboard.
function Caduceus({ size = 24 }: { size?: number }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <line x1="12" y1="3" x2="12" y2="21" />
      <path d="M8 5L4.5 2.5L6.5 6" />
      <path d="M8 5L5.5 6.5L7.5 8" />
      <path d="M16 5L19.5 2.5L17.5 6" />
      <path d="M16 5L18.5 6.5L16.5 8" />
      <path d="M9 9C7.5 11 7.5 13 9 15" />
      <path d="M9 15C10 17 11 17 12 16" />
      <path d="M15 9C16.5 11 16.5 13 15 15" />
      <path d="M15 15C14 17 13 17 12 16" />
    </svg>
  );
}

const HERMES_HEX = "#eab308";

const STATS = [
  { label: "Source platforms", value: "38" },
  { label: "Skills observable", value: "90+" },
  { label: "Hermes stars (★)", value: "153k" },
];

export default function HermesSpotlight() {
  return (
    <section
      id="hermes"
      className="relative overflow-hidden border-y border-[var(--tt-border)] bg-[radial-gradient(ellipse_at_top,rgba(234,179,8,0.08),transparent_70%)]"
    >
      <div className="max-w-[1320px] mx-auto px-5 sm:px-8 py-16 sm:py-24">
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] gap-10 lg:gap-16 items-center">
          {/* Left: copy */}
          <div>
            <div className="inline-flex items-center gap-2 mb-5 px-2.5 h-7 rounded-full text-[11px] font-medium tracking-tight text-[#eab308] bg-[#eab308]/8 border border-[#eab308]/30">
              <Caduceus size={11} />
              New · Hermes Agent
              <span className="text-[#eab308]/50">·</span>
              Nous Research
            </div>

            <h2 className="text-[28px] sm:text-[44px] lg:text-[50px] leading-[1.05] tracking-[-0.025em] font-semibold text-[var(--tt-fg)] mb-5">
              The only observability built for{" "}
              <span style={{ color: HERMES_HEX }}>autonomous agents.</span>
            </h2>

            <p className="text-[15px] sm:text-[17px] text-[var(--tt-fg-muted)] leading-relaxed mb-6 max-w-xl">
              Hermes runs across CLI, Telegram, Discord, Slack, Feishu, DingTalk, cron, webhook —
              <strong className="text-[var(--tt-fg)]"> 38 source platforms in total</strong>. TokenTelemetry is the only tool that observes them as a single agent, with a dedicated dashboard that respects how Hermes actually works.
            </p>

            <div className="flex flex-wrap gap-3">
              <Link
                href="#features"
                className="inline-flex items-center gap-2 px-4 h-10 rounded-[var(--tt-radius)] text-[13px] font-medium bg-[#eab308] text-black hover:bg-[#facc15] transition-colors"
              >
                See it in action <ArrowRight size={14} />
              </Link>
              <a
                href="https://github.com/NousResearch/hermes-agent"
                target="_blank" rel="noreferrer"
                className="inline-flex items-center gap-2 px-4 h-10 rounded-[var(--tt-radius)] text-[13px] font-medium text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] border border-[var(--tt-border)] hover:border-[var(--tt-border-strong)] transition-colors"
              >
                What is Hermes? <ArrowRight size={14} />
              </a>
            </div>
          </div>

          {/* Right: signals + install */}
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-3">
              {STATS.map((s) => (
                <div
                  key={s.label}
                  className="rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] p-4"
                >
                  <div className="text-[10px] font-medium uppercase tracking-[0.18em] text-[var(--tt-fg-dim)] mb-1">
                    {s.label}
                  </div>
                  <div className="text-[24px] font-semibold tracking-[-0.02em] text-[var(--tt-fg)] tabular">
                    {s.value}
                  </div>
                </div>
              ))}
            </div>

            <PluginInstallBlock />
          </div>
        </div>
      </div>
    </section>
  );
}
