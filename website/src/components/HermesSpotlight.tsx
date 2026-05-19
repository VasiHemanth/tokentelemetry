import Link from "next/link";
import {
  Send, Bell, Clock, Webhook, Terminal, MessageSquare, Hash,
  ArrowRight,
} from "lucide-react";
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

const PLATFORM_CHIPS = [
  { icon: Terminal,       label: "CLI" },
  { icon: Send,           label: "Telegram" },
  { icon: MessageSquare,  label: "Discord" },
  { icon: Hash,           label: "Slack" },
  { icon: Bell,           label: "DingTalk" },
  { icon: Clock,          label: "Cron" },
  { icon: Webhook,        label: "Webhook" },
];

const STATS = [
  { label: "Source platforms", value: "38" },
  { label: "Skills observable", value: "90+" },
  { label: "Per-call latency", value: "tracked" },
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

            <div className="flex flex-wrap gap-1.5 mb-7">
              {PLATFORM_CHIPS.map(({ icon: Icon, label }) => (
                <span
                  key={label}
                  className="inline-flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-tight text-[var(--tt-fg-muted)] bg-[var(--tt-panel)] border border-[var(--tt-border)] px-2 py-1 rounded"
                >
                  <Icon size={11} /> {label}
                </span>
              ))}
              <span className="inline-flex items-center text-[11px] font-medium text-[var(--tt-fg-dim)] px-1.5 py-1 italic">
                +31 more
              </span>
            </div>

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

          {/* Right: signals + previews */}
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
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

            <div className="rounded-[var(--tt-radius-lg)] border border-[#eab308]/30 bg-[var(--tt-panel)] p-5">
              <div className="flex items-center gap-2 mb-3">
                <span className="h-6 w-6 grid place-items-center rounded-md bg-[#eab308]/15 text-[#eab308]">
                  <Caduceus size={12} />
                </span>
                <span className="text-[11px] font-mono text-[var(--tt-fg-muted)]">
                  /hermes <span className="text-[var(--tt-fg-dim)]">·</span> dashboard
                </span>
              </div>
              <ul className="space-y-2.5 text-[13px] text-[var(--tt-fg-muted)] leading-relaxed">
                <li className="flex gap-2.5">
                  <span className="text-[#eab308] mt-0.5">▸</span>
                  <span><strong className="text-[var(--tt-fg)]">Gateway health pill</strong> — running / stale / stopped, per-platform status</span>
                </li>
                <li className="flex gap-2.5">
                  <span className="text-[#eab308] mt-0.5">▸</span>
                  <span><strong className="text-[var(--tt-fg)]">Cron health tile</strong> — "did my 8am cron run?" answered, at-risk flagged</span>
                </li>
                <li className="flex gap-2.5">
                  <span className="text-[#eab308] mt-0.5">▸</span>
                  <span><strong className="text-[var(--tt-fg)]">Per-API-call latency + cache hit</strong> parsed from agent.log</span>
                </li>
                <li className="flex gap-2.5">
                  <span className="text-[#eab308] mt-0.5">▸</span>
                  <span><strong className="text-[var(--tt-fg)]">delegate_task subagents</strong> rendered inline with summary, tokens, tool trace</span>
                </li>
                <li className="flex gap-2.5">
                  <span className="text-[#eab308] mt-0.5">▸</span>
                  <span><strong className="text-[var(--tt-fg)]">Skills + memory pages</strong> — 90 loaded skills, MEMORY.md / USER.md</span>
                </li>
                <li className="flex gap-2.5">
                  <span className="text-[#eab308] mt-0.5">▸</span>
                  <span><strong className="text-[var(--tt-fg)]">Cost anomaly detection</strong> — silent thinking-token waste flagged</span>
                </li>
              </ul>
            </div>

            {/* Plugin callout — embeds inside Hermes Dashboard */}
            <div className="space-y-3">
              <p className="text-[13px] text-[var(--tt-fg-muted)] leading-relaxed">
                <strong className="text-[var(--tt-fg)]">One port to remember.</strong>{" "}
                Install the plugin and TokenTelemetry shows up as a tab inside Hermes&apos;s own web dashboard — deep-link cards open Overview, Skills, Memory, Analytics, and Projects in a new tab.
              </p>
              <PluginInstallBlock />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
