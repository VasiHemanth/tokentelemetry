"use client";
import { AGENTS } from "@/data/agents";
import { useGithubStats } from "@/lib/useGithubStats";

export default function ProofStrip() {
  const { stars, forks } = useGithubStats();
  // Derive the count from the source of truth so it never goes stale when an
  // agent is added. Hermes is the autonomous agent, counted separately from the
  // coding-agent headline used across the site.
  const codingAgentCount = AGENTS.filter((a) => a.name !== "Hermes Agent").length;
  const STATS = [
    { value: String(codingAgentCount), unit: "agents", label: "auto-detected, zero config", green: false },
    { value: "0", unit: "bytes uploaded", label: "fully local · read-only", green: true },
    { value: String(stars), unit: `★ · ${forks} forks`, label: "open source · MIT", green: false },
    { value: "1", unit: "command", label: "no SDK · no signup", green: false },
  ];
  // Duplicate the agent chips so the CSS translateX(-50%) loop is seamless.
  const chips = [...AGENTS, ...AGENTS];
  return (
    <div className="border-y border-[var(--tt-border)] bg-[var(--tt-sunken)]">
      <div className="max-w-[1180px] mx-auto px-5">
        <div className="flex flex-wrap">
          {STATS.map((s, i) => (
            <div key={i} className="flex-1 min-w-[150px] py-5 px-6 border-[var(--tt-border)] [&:not(:last-child)]:border-r max-sm:basis-1/2 max-sm:border-b">
              <div className={`flex items-baseline gap-1.5 text-[26px] font-semibold tracking-[-0.02em] mb-0.5 tabular ${s.green ? "text-[#34d399]" : "text-[var(--tt-fg)]"}`}>
                {s.value} <span className="text-[12px] text-[var(--tt-fg-dim)] font-medium">{s.unit}</span>
              </div>
              <div className="text-[11px] uppercase tracking-[0.14em] text-[var(--tt-fg-dim)] font-medium">{s.label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Agents marquee */}
      <div className="overflow-hidden border-t border-[var(--tt-border)] py-[15px]"
        style={{ maskImage: "linear-gradient(90deg,transparent,#000 8%,#000 92%,transparent)", WebkitMaskImage: "linear-gradient(90deg,transparent,#000 8%,#000 92%,transparent)" }}>
        <div className="flex gap-2.5 w-max tt-marquee-track">
          {chips.map((a, i) => (
            <span key={i} className="inline-flex items-center gap-2 h-[34px] px-3.5 rounded-full border border-[var(--tt-border)] bg-[var(--tt-panel)] text-[12.5px] font-medium text-[var(--tt-fg-muted)] whitespace-nowrap">
              <span className="w-[7px] h-[7px] rounded-full" style={{ backgroundColor: a.hex }} />
              {a.name}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
