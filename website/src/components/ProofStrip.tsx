"use client";
import { motion, useReducedMotion } from "motion/react";
import { AGENTS } from "@/data/agents";
import { useGithubStats } from "@/lib/useGithubStats";
import { CountUp, Stagger } from "@/components/motion";

const CELL_CLASS =
  "flex-1 min-w-[150px] py-5 px-6 border-[var(--tt-border)] [&:not(:last-child)]:border-r max-sm:basis-1/2 max-sm:border-b";
const VALUE_CLASS =
  "flex items-baseline gap-1.5 text-[26px] font-semibold tracking-[-0.02em] mb-0.5 tabular";
const UNIT_CLASS = "text-[12px] text-[var(--tt-fg-dim)] font-medium";
const LABEL_CLASS =
  "text-[11px] uppercase tracking-[0.14em] text-[var(--tt-fg-dim)] font-medium";

/**
 * The "0" does NOT count up — it renders instantly with one 2s emerald glow
 * cycle so the zero reads asserted, not computed. Reduced motion: no glow.
 */
function AssertedZero() {
  const reduced = useReducedMotion();
  return (
    <span className="relative inline-block">
      {!reduced && (
        <motion.span
          aria-hidden
          className="absolute -inset-1 rounded-full"
          initial={{ opacity: 0 }}
          whileInView={{ opacity: [0, 1, 0] }}
          viewport={{ once: true, amount: 0.5 }}
          transition={{ duration: 2, ease: "easeInOut" }}
          style={{ boxShadow: "0 0 18px 5px rgba(52,211,153,0.35)" }}
        />
      )}
      <span className="relative">0</span>
    </span>
  );
}

export default function ProofStrip() {
  const { stars, forks } = useGithubStats();
  // Derive the count from the source of truth so it never goes stale when an
  // agent is added. Hermes is the autonomous agent, counted separately from the
  // coding-agent headline used across the site.
  const codingAgentCount = AGENTS.filter((a) => a.name !== "Hermes Agent").length;
  // Duplicate the agent chips so the CSS translateX(-50%) loop is seamless.
  const chips = [...AGENTS, ...AGENTS];
  return (
    <div className="border-y border-[var(--tt-border)] bg-[var(--tt-sunken)]">
      <div className="max-w-[1180px] mx-auto px-5">
        <Stagger gap={80} y={12} className="flex flex-wrap">
          <Stagger.Item className={CELL_CLASS}>
            <div className={`${VALUE_CLASS} text-[var(--tt-fg)]`}>
              <CountUp to={codingAgentCount} duration={700} />
              <span className={UNIT_CLASS}>agents</span>
            </div>
            <div className={LABEL_CLASS}>auto-detected, zero config</div>
          </Stagger.Item>
          <Stagger.Item className={CELL_CLASS}>
            <div className={`${VALUE_CLASS} text-[#34d399]`}>
              <AssertedZero />
              <span className={UNIT_CLASS}>bytes uploaded</span>
            </div>
            <div className={LABEL_CLASS}>fully local · read-only</div>
          </Stagger.Item>
          <Stagger.Item className={CELL_CLASS}>
            <div className={`${VALUE_CLASS} text-[var(--tt-fg)]`}>
              <CountUp to={stars} duration={1100} />
              <span className={UNIT_CLASS}>
                ★ · <CountUp to={forks} duration={1100} /> forks
              </span>
            </div>
            <div className={LABEL_CLASS}>open source · MIT</div>
          </Stagger.Item>
          <Stagger.Item className={CELL_CLASS}>
            <div className={`${VALUE_CLASS} text-[var(--tt-fg)]`}>
              <CountUp to={1} duration={300} />
              <span className={UNIT_CLASS}>command</span>
            </div>
            <div className={LABEL_CLASS}>no SDK · no signup</div>
          </Stagger.Item>
        </Stagger>
      </div>

      {/* Agents marquee — keeps its CSS loop, slowed to 28s; chip dots carry
          the app's agent-identity glow so the colors read as one system. */}
      <div className="overflow-hidden border-t border-[var(--tt-border)] py-[15px]"
        style={{ maskImage: "linear-gradient(90deg,transparent,#000 8%,#000 92%,transparent)", WebkitMaskImage: "linear-gradient(90deg,transparent,#000 8%,#000 92%,transparent)" }}>
        <div className="flex gap-2.5 w-max tt-marquee-track" style={{ animationDuration: "28s" }}>
          {chips.map((a, i) => (
            <span key={i} className="inline-flex items-center gap-2 h-[34px] px-3.5 rounded-full border border-[var(--tt-border)] bg-[var(--tt-panel)] text-[12.5px] font-medium text-[var(--tt-fg-muted)] whitespace-nowrap">
              <span
                className="w-[7px] h-[7px] rounded-full"
                style={{ backgroundColor: a.hex, boxShadow: `0 0 8px ${a.hex}66` }}
              />
              {a.name}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
