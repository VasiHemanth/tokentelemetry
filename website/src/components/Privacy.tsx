import Link from "next/link";
import { Lock, BarChart3, FileCode } from "lucide-react";
import { Reveal, Stagger, StaggerItem } from "@/components/motion";

/**
 * Honest privacy section. The source mockup said "No usage tracking / no
 * telemetry hidden anywhere" — that is false now that the app ships opt-out
 * anonymous telemetry (see docs/design/product-telemetry.md). This section keeps
 * the strong local-first promise for user DATA while disclosing the telemetry
 * truthfully, so the page can't be diffed against reality.
 *
 * Motion: quietest section by design. Header reveal, 24px card rise on an
 * 80ms stagger, and a static devtools-style network row whose only movement
 * is the CSS `tt-pulse` on the trailing ellipsis (stilled under
 * prefers-reduced-motion by the global override).
 */
const CARDS = [
  {
    icon: Lock,
    title: "Local & read-only",
    body: (
      <>
        Reads session logs from your filesystem and serves a UI on localhost. Your{" "}
        <strong className="text-[var(--tt-fg-muted)]">logs, prompts, tokens, and costs never leave your
        computer</strong>. The app never writes to your agent files.
      </>
    ),
  },
  {
    icon: BarChart3,
    title: "Anonymous usage stats",
    body: (
      <>
        To know what to build next, the app sends <strong className="text-[var(--tt-fg-muted)]">anonymous,
        content-free</strong> stats (which pages/features you use — never your code, prompts, paths, or costs). On by
        default; see the exact payload and turn it off in <strong className="text-[var(--tt-fg-muted)]">Settings →
        Usage &amp; privacy</strong> or with <code className="font-mono text-[12px] text-[var(--tt-fg-muted)] bg-[var(--tt-sunken)] px-1.5 py-0.5 rounded">DO_NOT_TRACK=1</code>.
      </>
    ),
  },
  {
    icon: FileCode,
    title: "MIT open source",
    body: (
      <>
        Read every line. Fork it. Replace it with something better — up to you. 180 commits, public on GitHub, and the
        telemetry pipeline is in the source with an allowlist test.
      </>
    ),
  },
];

export default function Privacy() {
  return (
    <section className="relative border-t border-[var(--tt-border)]"
      style={{ background: "radial-gradient(900px 420px at 50% 0%, rgba(16,185,129,0.06), transparent 65%)" }}>
      <div className="max-w-[1180px] mx-auto px-5 py-12 sm:py-[72px]">
        <Reveal y={16} className="text-center max-w-[680px] mx-auto mb-10">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#34d399] mb-3">
            Built for people who read the source
          </p>
          <h2 className="text-[clamp(26px,3.6vw,42px)] leading-[1.08] tracking-[-0.025em] font-semibold text-[var(--tt-fg)]">
            Your data stays on{" "}
            <span className="bg-gradient-to-r from-[#86efac] to-[#34d399] bg-clip-text text-transparent">your machine.</span>
          </h2>
          <p className="mt-3.5 text-[15.5px] text-[var(--tt-fg-muted)] leading-relaxed">
            No cloud, no accounts. Your logs, prompts, and costs never leave your computer — the only things that go
            out are anonymous, content-free usage stats (one-click off) and an optional update check.{" "}
            <Link href="/privacy" className="text-[var(--tt-fg)] underline underline-offset-2 hover:text-[var(--tt-brand)] transition-colors">
              Read the policy
            </Link>.
          </p>
        </Reveal>
        {/* Devtools-style network row: static content, pure CSS. */}
        <div className="mb-6 flex justify-center">
          <div className="inline-flex items-center rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-sunken)] px-4 py-1.5 font-mono text-[11.5px] text-[var(--tt-fg-dim)]">
            <span>
              outbound requests: <span className="text-[var(--tt-success)] font-semibold">0</span>
              <span className="mx-2 text-[var(--tt-fg-faint)]">·</span>
              listening<span className="tt-pulse">…</span>
            </span>
          </div>
        </div>
        <Stagger gap={80} y={24} className="grid grid-cols-1 md:grid-cols-3 gap-3 sm:gap-4">
          {CARDS.map(({ icon: Icon, title, body }) => (
            <StaggerItem key={title}>
              <div className="h-full p-6 rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)]">
                <div className="w-[38px] h-[38px] rounded-[var(--tt-radius)] grid place-items-center mb-4 bg-[rgba(16,185,129,0.1)] border border-[rgba(16,185,129,0.25)]">
                  <Icon size={18} className="text-[var(--tt-success-fg,#10b981)]" />
                </div>
                <h3 className="text-[16px] font-semibold tracking-[-0.01em] text-[var(--tt-fg)] mb-2">{title}</h3>
                <p className="text-[13.5px] text-[var(--tt-fg-muted)] leading-relaxed">{body}</p>
              </div>
            </StaggerItem>
          ))}
        </Stagger>
      </div>
    </section>
  );
}
