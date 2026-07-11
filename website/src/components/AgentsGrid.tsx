"use client";
import { useState } from "react";
import { AGENTS } from "@/data/agents";
import { track } from "@/lib/track";

/**
 * Interactive agent cards. The CRO audit (D3) found visitors tapping the old
 * static agent cards expecting them to *do* something — dead clicks. Now each
 * card is a real button that expands to reveal what TokenTelemetry captures and
 * where it reads from, so the click pays off.
 */
export default function AgentsGrid() {
  const [open, setOpen] = useState<number | null>(null);

  return (
    <section id="agents" className="border-t border-[var(--tt-border)]">
      <div className="max-w-[1180px] mx-auto px-5 py-12 sm:py-[72px]">
        <div className="text-center max-w-[680px] mx-auto mb-10">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--tt-fg-dim)] mb-3">Coverage</p>
          <h2 className="text-[clamp(26px,3.6vw,42px)] leading-[1.08] tracking-[-0.025em] font-semibold text-[var(--tt-fg)]">
            13 coding agents, <span className="text-[var(--tt-brand)]">one place.</span>
          </h2>
          <p className="mt-3.5 text-[15.5px] text-[var(--tt-fg-muted)] leading-relaxed">
            Tap any agent to see what TokenTelemetry captures and where it reads from.
          </p>
        </div>

        <div className="grid grid-cols-1 min-[480px]:grid-cols-2 lg:grid-cols-4 gap-2.5 items-start">
          {AGENTS.map((a, i) => {
            const isOpen = open === i;
            return (
              <button
                key={a.name}
                aria-expanded={isOpen}
                onClick={() => {
                  setOpen(isOpen ? null : i);
                  if (!isOpen) track("feature_used", { name: "agent_expand" });
                }}
                className="text-left p-4 rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] hover:border-[var(--tt-border-strong)] hover:bg-[var(--tt-raised)] hover:-translate-y-0.5 transition-all relative flex flex-col"
              >
                <span className="absolute top-4 right-4 text-[14px] text-[var(--tt-fg-faint)] transition-transform"
                  style={{ transform: isOpen ? "rotate(45deg)" : "none" }}>
                  +
                </span>
                <span className="flex items-center gap-2.5 mb-1">
                  <span className="w-[9px] h-[9px] rounded-full shrink-0" style={{ backgroundColor: a.hex, boxShadow: `0 0 8px ${a.hex}66` }} />
                  <span className="text-[14px] font-semibold tracking-[-0.01em] text-[var(--tt-fg)]">{a.name}</span>
                </span>
                <span className="font-mono text-[11px] text-[var(--tt-fg-dim)] pl-[19px]">{a.vendor}</span>

                <span className="overflow-hidden transition-all duration-300 ease-out pl-[19px]"
                  style={{ maxHeight: isOpen ? 160 : 0, opacity: isOpen ? 1 : 0, marginTop: isOpen ? 8 : 0 }}>
                  <span className="block text-[11.5px] text-[var(--tt-fg-muted)] leading-relaxed">
                    Reads from <span className="font-mono text-[var(--tt-fg-muted)]">{a.logPath}</span>
                  </span>
                  <span className="flex flex-wrap gap-1 mt-2">
                    {a.captures.map((c) => (
                      <span key={c} className="font-mono text-[10px] px-1.5 py-0.5 rounded-[5px] bg-[var(--tt-sunken)] border border-[var(--tt-border)] text-[var(--tt-fg-dim)]">
                        {c}
                      </span>
                    ))}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}
