import { ArrowRight } from "lucide-react";
import ContributorWall, { CONTRIBUTING_URL, contributorCounts } from "@/components/ContributorWall";

/**
 * Landing-page community section. Every number here comes from
 * src/data/contributors.json (see scripts/fetch-contributors.mjs), so the copy
 * can't drift from the people actually shown.
 */
export default function Contributors() {
  const { total, code } = contributorCounts;
  const rest = total - code;

  return (
    <section id="contributors" className="relative overflow-hidden border-t border-[var(--tt-border)]">
      <div aria-hidden className="pointer-events-none absolute inset-0"
        style={{ background: "radial-gradient(640px 420px at 85% 50%, rgba(96,165,250,0.08), transparent 70%)" }} />
      <div className="relative max-w-[1180px] mx-auto px-5 py-12 sm:py-[72px] grid gap-10 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
        <div className="max-w-[460px]">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--tt-fg-dim)] mb-3">Community</p>
          <h2 className="text-[clamp(26px,3.6vw,42px)] leading-[1.08] tracking-[-0.025em] font-semibold text-[var(--tt-fg)]">
            Built in the open by <span className="text-[var(--tt-brand)]">{total} people.</span>
          </h2>
          <p className="mt-3.5 text-[15.5px] text-[var(--tt-fg-muted)] leading-relaxed">
            {code} of them wrote code. The other {rest} reported bugs, opened pull requests, or shaped features in
            Discussions.
          </p>
          <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-3">
            <a
              href={CONTRIBUTING_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 h-11 px-4 rounded-[var(--tt-radius)] text-[14px] font-semibold bg-[var(--tt-raised)] text-[var(--tt-fg)] border border-[var(--tt-border-strong)] hover:border-[var(--tt-brand)] hover:bg-[var(--tt-overlay)] transition-colors"
            >
              Join us <ArrowRight size={15} />
            </a>
            <span className="inline-flex items-center gap-2 text-[12.5px] text-[var(--tt-fg-dim)]">
              <span aria-hidden className="h-3 w-3 rounded-full ring-2 ring-[var(--tt-brand)] ring-offset-2 ring-offset-[var(--tt-canvas)]" />
              wrote code
            </span>
          </div>
        </div>

        <ContributorWall columns={7} size={38} className="mx-auto sm:hidden" />
        <ContributorWall columns={9} size={44} className="mx-auto hidden sm:grid lg:hidden" />
        <ContributorWall columns={10} size={48} className="hidden lg:grid" />
      </div>
    </section>
  );
}
