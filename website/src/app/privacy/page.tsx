import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Privacy Policy — TokenTelemetry",
  description:
    "How the TokenTelemetry website handles cookies and analytics. The TokenTelemetry tool itself is 100% local and collects nothing.",
  alternates: { canonical: "https://tokentelemetry.com/privacy" },
  robots: { index: true, follow: true },
};

const UPDATED = "May 25, 2026";

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

      <Section title="The short version">
        <p>
          The <strong className="text-[var(--tt-fg)]">TokenTelemetry tool</strong> is 100% local and read-only. It
          runs on your machine, reads your local agent logs, and never sends your usage data anywhere. There are no
          accounts and no server.
        </p>
        <p>
          This policy is only about the <strong className="text-[var(--tt-fg)]">marketing website</strong> you are
          reading now (tokentelemetry.com), which uses optional analytics cookies to understand how the site is used.
        </p>
      </Section>

      <Section title="Cookies & analytics on this website">
        <p>
          We load two analytics tools, and only after you press <em>Accept</em> on the cookie banner:
        </p>
        <ul className="list-disc pl-5 space-y-2">
          <li>
            <strong className="text-[var(--tt-fg)]">Google Analytics 4</strong> — aggregate, anonymized traffic stats
            (page views, referrers, country). IP addresses are anonymized.
          </li>
          <li>
            <strong className="text-[var(--tt-fg)]">Microsoft Clarity</strong> — anonymized usage analytics such as
            heatmaps and session replays of interactions with the page, to help us improve layout and content.
          </li>
        </ul>
        <p>
          If you press <em>Decline</em>, neither tool loads and no analytics cookies are set. Your choice is stored
          locally in your browser so we only ask once. To change it, clear this site&apos;s data in your browser and
          reload.
        </p>
        <p>We do not sell your data, run ads, or share it for advertising purposes.</p>
      </Section>

      <Section title="What we never collect">
        <p>
          Your prompts, code, agent logs, token counts, and costs stay on your own machine. TokenTelemetry has no
          usage-telemetry endpoint — your data is never collected or transmitted anywhere.
        </p>
        <p>
          The application makes a single outbound network request: an <strong className="text-[var(--tt-fg)]">optional
          update check</strong> that fetches the latest version and release notes from GitHub (about once an hour) so
          you know when new features are available. It sends no usage data — only a version request, which, like any
          web request, exposes your IP address and the app name to GitHub. Disable it in the app under
          Settings → Updates &amp; privacy, or by setting <code>TT_NO_UPDATE_CHECK=1</code> before launching.
        </p>
      </Section>

      <Section title="Third-party policies">
        <p>
          When enabled, the analytics tools are governed by their own policies:{" "}
          <a
            href="https://policies.google.com/privacy"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[var(--tt-fg)] underline underline-offset-2 hover:text-[var(--tt-brand)] transition-colors"
          >
            Google Privacy Policy
          </a>{" "}
          and{" "}
          <a
            href="https://privacy.microsoft.com/privacystatement"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[var(--tt-fg)] underline underline-offset-2 hover:text-[var(--tt-brand)] transition-colors"
          >
            Microsoft Privacy Statement
          </a>
          .
        </p>
      </Section>

      <Section title="Contact">
        <p>
          Questions? Open an issue on{" "}
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
