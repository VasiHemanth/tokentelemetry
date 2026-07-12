import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Privacy Policy — TokenTelemetry",
  description:
    "How TokenTelemetry handles privacy: your logs, prompts, and costs stay on your machine; the app sends only anonymous, content-free usage stats (on by default, one-click off).",
  alternates: { canonical: "https://tokentelemetry.com/privacy" },
  robots: { index: true, follow: true },
};

const UPDATED = "June 15, 2026";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-10">
      <h2 className="text-[18px] font-semibold tracking-[-0.01em] text-[var(--tt-fg)] mb-3">{title}</h2>
      <div className="space-y-3 text-[14px] leading-relaxed text-[var(--tt-fg-muted)]">{children}</div>
    </section>
  );
}

export default function PrivacyPage() {
  return (
    <main className="max-w-[760px] mx-auto px-5 sm:px-8 py-16 sm:py-24">
      <p className="text-[12px] font-mono uppercase tracking-[0.18em] text-[var(--tt-fg-dim)]">Legal</p>
      <h1 className="mt-2 text-[30px] sm:text-[36px] font-semibold tracking-[-0.02em] text-[var(--tt-fg)]">
        Privacy Policy
      </h1>
      <p className="mt-3 text-[13px] text-[var(--tt-fg-dim)]">Last updated: {UPDATED}</p>

      <div className="mt-8 text-[15px] leading-relaxed text-[var(--tt-fg-muted)] space-y-3">
        <p>
          TokenTelemetry respects your privacy. As the product evolves, we need to understand how people
          actually use it — which features deliver value and which don&apos;t — so we can make it better
          for everyone. To do that we collect a small, anonymous set of usage signals. This data carries
          nothing about your work. And if you&apos;d rather not share it, or you&apos;re in a restricted
          environment, you can turn it off completely.
        </p>
      </div>

      <Section title="What we collect">
        <p>Anonymous usage signals only — nothing about your code, prompts, or work:</p>
        <ul className="list-disc pl-5 space-y-2 mt-2">
          <li>Which pages you open in the app</li>
          <li>Which features you use (e.g. trace summaries, analytics filters, the Hermes dashboard)</li>
          <li>Whether a summary succeeded or failed, and which summarizer engine was used</li>
          <li>Your OS family, CPU architecture, and the app version</li>
          <li>
            Your approximate country — derived at Cloudflare&apos;s edge from the request, not from your
            IP (we never receive or store your IP)
          </li>
          <li>Which AI agents are detected on your machine (e.g. Claude, Codex), as a generic list</li>
          <li>
            Which model families each agent uses (e.g. claude-opus, gpt) — a fixed set of family
            names only, never the exact model id or a custom model name
          </li>
          <li>
            A random session id that is regenerated every launch and is never linked to you across
            sessions
          </li>
        </ul>
      </Section>

      <Section title="What we never collect">
        <ul className="list-disc pl-5 space-y-2">
          <li>Your code, prompts, or any model output</li>
          <li>File paths, directory names, project or repository names</li>
          <li>Token counts or cost data</li>
          <li>Your IP address</li>
          <li>Any stable user or device identifier</li>
        </ul>
      </Section>

      <Section title="How it's handled">
        <p>
          Events go to a Cloudflare Worker that writes anonymous, aggregate-friendly data points to
          Cloudflare Analytics Engine. No analytics key ships in the app. Telemetry is on by default so
          the data is representative, but turning it off is one click and always available.
        </p>
      </Section>

      <Section title="How to turn it off">
        <ul className="list-disc pl-5 space-y-2">
          <li>
            <strong className="text-[var(--tt-fg)]">In the app:</strong> Settings → &ldquo;Usage &amp;
            privacy&rdquo; → toggle it off.
          </li>
          <li>
            <strong className="text-[var(--tt-fg)]">For restricted or enterprise environments:</strong>{" "}
            set <code>DO_NOT_TRACK=1</code> or <code>TT_NO_TELEMETRY=1</code> and telemetry is forced
            off. It is also automatically disabled in CI and non-interactive runs.
          </li>
        </ul>
      </Section>

      <Section title="This website">
        <p>
          The marketing site (tokentelemetry.com) loads{" "}
          <strong className="text-[var(--tt-fg)]">Google Analytics 4</strong> and{" "}
          <strong className="text-[var(--tt-fg)]">Microsoft Clarity</strong> — but only after you press
          Accept on the cookie banner. If you decline, neither tool loads and no analytics cookies are
          set. We do not sell your data or use it for advertising.
        </p>
      </Section>

      <Section title="Contact">
        <p>
          Questions or concerns? Open an issue on{" "}
          <a
            href="https://github.com/VasiHemanth/tokentelemetry/issues"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[var(--tt-fg)] underline underline-offset-2 hover:text-[var(--tt-brand)] transition-colors"
          >
            GitHub
          </a>
          .
        </p>
      </Section>

      <div className="mt-14 pt-8 border-t border-[var(--tt-border)]">
        <Link
          href="/"
          className="text-[13px] text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] transition-colors"
        >
          ← Back to home
        </Link>
      </div>
    </main>
  );
}
