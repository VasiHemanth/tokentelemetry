"use client";
/**
 * Ledger — 01 · BURN. Ninety days of one machine's agent spend as oversized
 * tabular numerals. The figures match the demo dashboard in the hero
 * screenshot; the zero is the point.
 */
import CountUp from "@/components/motion/CountUp";
import Reveal from "@/components/motion/Reveal";
import SectionHead from "@/components/SectionHead";

const ROWS = [
  {
    value: <CountUp to={599.85} prefix="$" duration={1100} format={(n) => n.toFixed(2)} />,
    label: "burned across every agent",
    tone: "text-[var(--tt-warn)]",
  },
  {
    value: <CountUp to={931.8} suffix="M" duration={1000} format={(n) => n.toFixed(1)} />,
    label: "tokens metered, in and out",
    tone: "text-[var(--tt-fg)]",
  },
  {
    value: <CountUp to={510} duration={900} />,
    label: "sessions traced end to end",
    tone: "text-[var(--tt-fg)]",
  },
  {
    value: <span>0</span>,
    label: "bytes uploaded anywhere",
    tone: "text-[#34d399]",
  },
];

export default function Ledger() {
  return (
    <section className="py-16 sm:py-24">
      <div className="max-w-[1180px] mx-auto px-5">
      <SectionHead
        index="01"
        label="burn"
        title={
          <>
            The bill is real.{" "}
            <span className="text-[var(--tt-fg-dim)]">Now it&apos;s visible.</span>
          </>
        }
        sub="Ninety days on one machine, straight off the demo dashboard below. Your numbers will be your own — that's the point."
      />
        <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
          {ROWS.map((r, i) => (
            <Reveal key={r.label} y={24} delay={i * 0.08} className="group border-t lg:border-t-0 lg:border-l border-[var(--tt-border)] first:border-t-0 first:lg:border-l-0 py-7 lg:py-2 lg:px-7 first:lg:pl-0">
              <dd className={`tabular font-semibold tracking-[-0.04em] leading-none whitespace-nowrap text-[clamp(40px,4.6vw,64px)] ${r.tone}`}>
                {r.value}
              </dd>
              <dt className="mt-3 font-mono text-[11.5px] tracking-[0.14em] uppercase text-[var(--tt-fg-dim)]">
                {r.label}
              </dt>
            </Reveal>
          ))}
        </dl>
      </div>
    </section>
  );
}
