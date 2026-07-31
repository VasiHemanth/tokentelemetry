import type { ReactNode } from "react";
import Reveal from "@/components/motion/Reveal";

/**
 * SectionHead — the numbered instrument chrome every section shares.
 * Hairline rule, mono index (`03 · TRACE`), then an oversized editorial
 * headline. Left-aligned; sections keep their own inner layouts below it.
 * Server component: Reveal is the only client child.
 */
export default function SectionHead({
  index,
  label,
  title,
  sub,
  id,
}: {
  index: string;
  label: string;
  title: ReactNode;
  sub?: ReactNode;
  id?: string;
}) {
  return (
    // scroll-mt = 58px sticky header + 24px breathing room
    <div id={id} className="scroll-mt-[82px]">
      <div className="border-t border-[var(--tt-border)] pt-5 mb-10 sm:mb-14">
        <div className="flex items-baseline justify-between gap-4 mb-6 sm:mb-9 font-mono text-[11.5px] tracking-[0.16em] uppercase">
          <span className="text-[var(--tt-fg-dim)]">
            <span className="text-[var(--tt-brand)]">{index}</span> · {label}
          </span>
          <span aria-hidden className="hidden sm:block text-[var(--tt-fg-faint)] select-none">
            tokentelemetry
          </span>
        </div>
        <Reveal y={16}>
          <h2 className="text-[clamp(32px,6vw,72px)] leading-[0.98] tracking-[-0.04em] font-semibold text-[var(--tt-fg)] text-balance max-w-[900px]">
            {title}
          </h2>
          {sub && (
            <p className="mt-5 text-[clamp(15px,1.7vw,17.5px)] text-[var(--tt-fg-muted)] leading-relaxed max-w-[560px]">
              {sub}
            </p>
          )}
        </Reveal>
      </div>
    </div>
  );
}
