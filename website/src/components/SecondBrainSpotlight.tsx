import Link from "next/link";
import { ArrowRight, Network } from "lucide-react";

const BRAIN_HEX = "#a78bfa";

// Numbers from the measured A/B benchmark (28 headless sessions) — see
// /docs/second-brain/evidence for the full method and the negative results.
const STATS = [
  { label: "Turns, covered questions", value: "~½" },
  { label: "Cost, covered questions", value: "~½" },
  { label: "Overall cost", value: "−18%" },
];

export default function SecondBrainSpotlight() {
  return (
    <section
      id="second-brain"
      className="relative overflow-hidden border-y border-[var(--tt-border)] bg-[radial-gradient(ellipse_at_top,rgba(167,139,250,0.08),transparent_70%)]"
    >
      <div className="max-w-[1320px] mx-auto px-5 sm:px-8 py-16 sm:py-24">
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] gap-10 lg:gap-16 items-center">
          {/* Left: copy */}
          <div>
            <div className="inline-flex items-center gap-2 mb-5 px-2.5 h-7 rounded-full text-[11px] font-medium tracking-tight text-[#a78bfa] bg-[#a78bfa]/8 border border-[#a78bfa]/30">
              <Network size={11} />
              New · Second Brain plugin
            </div>

            <h2 className="text-[28px] sm:text-[44px] lg:text-[50px] leading-[1.05] tracking-[-0.025em] font-semibold text-[var(--tt-fg)] mb-5">
              A wiki your agents read{" "}
              <span style={{ color: BRAIN_HEX }}>instead of your codebase.</span>
            </h2>

            <p className="text-[15px] sm:text-[17px] text-[var(--tt-fg-muted)] leading-relaxed mb-6 max-w-xl">
              The plugin compiles your project into a small typed wiki at{" "}
              <code className="font-mono text-[14px] text-[var(--tt-fg)]">docs/wiki/</code>: short
              pages for subsystems, decisions, conventions, and playbooks that agents answer from
              instead of re-exploring the code. It compiles with Claude Code but works with{" "}
              <strong className="text-[var(--tt-fg)]">every supported coding agent</strong>: a
              pointer block in <code className="font-mono text-[14px] text-[var(--tt-fg)]">AGENTS.md</code>{" "}
              routes them to the wiki, and a stdlib-only{" "}
              <code className="font-mono text-[14px] text-[var(--tt-fg)]">status.py</code> checks
              freshness from any harness.
            </p>

            <div className="flex flex-wrap gap-3">
              <Link
                href="/docs/second-brain"
                className="inline-flex items-center gap-2 px-4 h-10 rounded-[var(--tt-radius)] text-[13px] font-medium bg-[#a78bfa] text-black hover:bg-[#c4b5fd] transition-colors"
              >
                Read the docs <ArrowRight size={14} />
              </Link>
              <Link
                href="/docs/second-brain/evidence"
                className="inline-flex items-center gap-2 px-4 h-10 rounded-[var(--tt-radius)] text-[13px] font-medium text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] border border-[var(--tt-border)] hover:border-[var(--tt-border-strong)] transition-colors"
              >
                See the evidence <ArrowRight size={14} />
              </Link>
            </div>

            <p className="mt-5 text-[13px] text-[var(--tt-fg-dim)] leading-relaxed">
              There is much more in{" "}
              <Link
                href="/docs/second-brain"
                className="text-[var(--tt-fg-muted)] underline underline-offset-2 hover:text-[var(--tt-fg)] transition-colors"
              >
                the docs
              </Link>
              : the full command surface, the agent-driven exploration loop, and the measured
              evidence including the negative results.
            </p>
          </div>

          {/* Right: wiki graph + measured numbers */}
          <div className="space-y-4">
            <Link
              href="/docs/second-brain"
              className="block rounded-[var(--tt-radius-lg)] overflow-hidden border border-[var(--tt-border)] hover:border-[var(--tt-border-strong)] bg-[var(--tt-panel)] transition-colors"
            >
              <img
                src="/screenshots/second-brain-graph.png"
                alt="Second brain wiki graph of the TokenTelemetry repo, one node per page, clustered by page type (light theme)"
                className="block w-full h-auto dark:hidden"
                loading="lazy"
                decoding="async"
              />
              <img
                src="/screenshots/second-brain-graph-dark.png"
                alt="Second brain wiki graph of the TokenTelemetry repo, one node per page, clustered by page type (dark theme)"
                className="hidden w-full h-auto dark:block"
                loading="lazy"
                decoding="async"
              />
            </Link>

            <div className="grid grid-cols-3 gap-3">
              {STATS.map((s) => (
                <Link
                  key={s.label}
                  href="/docs/second-brain/evidence"
                  className="rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] hover:border-[var(--tt-border-strong)] bg-[var(--tt-panel)] p-4 transition-colors"
                >
                  <div className="text-[10px] font-medium uppercase tracking-[0.18em] text-[var(--tt-fg-dim)] mb-1">
                    {s.label}
                  </div>
                  <div className="text-[24px] font-semibold tracking-[-0.02em] text-[var(--tt-fg)] tabular">
                    {s.value}
                  </div>
                </Link>
              ))}
            </div>
            <p className="text-[12px] text-[var(--tt-fg-dim)]">
              From a 28-session A/B benchmark on a real project.{" "}
              <Link
                href="/docs/second-brain/evidence"
                className="underline underline-offset-2 hover:text-[var(--tt-fg-muted)] transition-colors"
              >
                Method and full results
              </Link>
              .
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
