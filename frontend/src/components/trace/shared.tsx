import type { CSSProperties } from "react";
import type { TraceSpan } from "@/lib/traceTree/types";
import type { AxisMark } from "@/lib/traceTree/timeScale";

export type ColorOf = (agentType: string | undefined) => string;

const AGENT_COLORS = [
  "var(--tt-violet-fg)",
  "var(--tt-warn-fg)",
  "var(--tt-success-fg)",
  "var(--tt-info-fg)",
];

/** Skills own the cyan token; the agent palette above avoids it. */
export const SKILL_COLOR = "var(--tt-cyan-fg)";

/** Stable color per agent type, assigned in order of first appearance. */
export function makeColorOf(types: string[]): ColorOf {
  const map = new Map<string, string>();
  for (const t of types) if (!map.has(t)) map.set(t, AGENT_COLORS[map.size % AGENT_COLORS.length]);
  return (t) => (t && map.get(t)) || "var(--tt-fg-muted)";
}

/** Hatched fill for collapsed idle stretches. */
export const HATCH: CSSProperties = {
  backgroundImage: "repeating-linear-gradient(135deg, var(--tt-border-strong) 0 1px, transparent 1px 6px)",
  backgroundColor: "var(--tt-sunken)",
};

const CHIP = "inline-flex shrink-0 items-center rounded px-1.5 py-px text-[9px] font-semibold uppercase tracking-[0.12em] leading-4";

export function KindChip({ span, color }: { span: TraceSpan; color?: string }) {
  if (span.error) {
    return <span className={`${CHIP} border border-[var(--tt-danger-bd)] bg-[var(--tt-danger-bg)] text-[var(--tt-danger-fg)]`}>{span.kind}</span>;
  }
  if (span.kind === "agent" || span.kind === "skill") {
    return (
      <span className={`${CHIP} text-[var(--tt-canvas)]`} style={{ background: span.kind === "skill" ? SKILL_COLOR : color }}>
        {span.kind}
      </span>
    );
  }
  const tone =
    span.kind === "turn"
      ? "border-[var(--tt-brand-glow)] bg-[var(--tt-brand-glow)] text-[var(--tt-brand)]"
      : span.kind === "llm"
        ? "border-[var(--tt-border)] bg-[var(--tt-raised)] text-[var(--tt-fg-muted)]"
        : "border-[var(--tt-border)] bg-[var(--tt-sunken)] text-[var(--tt-fg-dim)]";
  return <span className={`${CHIP} border ${tone}`}>{span.kind}</span>;
}

export function Tag({ children, color, title }: { children: React.ReactNode; color?: string; title?: string }) {
  return (
    <span
      title={title}
      className="inline-flex shrink-0 items-center rounded border border-[var(--tt-border-strong)] px-1 text-[9px] leading-4 text-[var(--tt-fg-muted)]"
      style={color ? { color, borderColor: color } : undefined}
    >
      {children}
    </span>
  );
}

export function Axis({ marks, className = "" }: { marks: AxisMark[]; className?: string }) {
  return (
    <div className={`relative h-5 ${className}`}>
      {marks.map((m, i) =>
        m.kind === "idle" ? (
          <span
            key={`i${i}`}
            className="absolute top-0.5 -translate-x-1/2 whitespace-nowrap rounded bg-[var(--tt-sunken)] px-1 text-[9px] italic leading-4 text-[var(--tt-fg-dim)]"
            style={{ left: `${m.x * 100}%` }}
          >
            {m.label}
          </span>
        ) : (
          <span
            key={`${m.kind}${i}`}
            className={`absolute top-1 -translate-x-1/2 whitespace-nowrap font-mono text-[9px] leading-4 ${m.kind === "day" ? "font-semibold text-[var(--tt-fg-muted)]" : "text-[var(--tt-fg-dim)]"}`}
            style={{ left: `${m.x * 100}%` }}
          >
            {m.label}
          </span>
        ),
      )}
    </div>
  );
}

export const SECTION_LABEL = "text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--tt-fg-dim)]";
