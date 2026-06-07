import Link from "next/link";
import { Lock, FileCode, Zap, GitBranch } from "lucide-react";

const ITEMS = [
  { icon: Lock,     title: "100% local",      body: "Your logs never leave your machine. No usage tracking. No accounts. Only an optional update check pings GitHub." },
  { icon: FileCode, title: "MIT open source", body: "Read every line. Fork it. Replace it with something better — up to you." },
  { icon: Zap,      title: "No signup",       body: "One command, browser opens. That is the entire onboarding." },
];

export default function TrustStrip() {
  return (
    <section className="border-t border-[var(--tt-border)]">
      <div className="max-w-[1320px] mx-auto px-5 sm:px-8 py-14 sm:py-20">
        <div className="grid md:grid-cols-3 gap-4 sm:gap-6 mb-10 sm:mb-14">
          {ITEMS.map(({ icon: Icon, title, body }) => (
            <div
              key={title}
              className="rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] p-5"
            >
              <div className="h-9 w-9 rounded-[var(--tt-radius)] grid place-items-center bg-[color:var(--tt-brand-glow)] border border-[color:var(--tt-brand)]/25 mb-4">
                <Icon size={16} className="text-[var(--tt-brand)]" />
              </div>
              <h3 className="text-[15px] font-semibold tracking-[-0.01em] text-[var(--tt-fg)] mb-1">{title}</h3>
              <p className="text-[13px] text-[var(--tt-fg-muted)] leading-relaxed">{body}</p>
            </div>
          ))}
        </div>

        <div className="flex flex-col md:flex-row items-center justify-between gap-4 pt-8 border-t border-[var(--tt-border)]">
          <div className="text-[11.5px] font-mono text-[var(--tt-fg-dim)]">
            tokentelemetry · built by{" "}
            <a
              href="https://www.linkedin.com/in/vasi-hemanth/"
              target="_blank" rel="noopener noreferrer"
              className="text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] transition-colors"
            >
              Hemanth Vasi
            </a>
            <span className="mx-2 text-[var(--tt-fg-faint)]">·</span>
            <Link
              href="/privacy"
              className="text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] transition-colors"
            >
              Privacy
            </Link>
          </div>
          <a
            href="https://github.com/VasiHemanth/tokentelemetry"
            target="_blank" rel="noopener noreferrer"
            className="inline-flex items-center gap-2 h-9 px-3 rounded-[var(--tt-radius)] tt-tint-1 hover:tt-tint-2 border border-[var(--tt-border-strong)] text-[var(--tt-fg)] text-[12px] font-medium transition-colors"
          >
            <GitBranch size={14} />
            <img
              src="https://img.shields.io/github/stars/VasiHemanth/tokentelemetry?style=flat&label=star&color=1f2937&labelColor=0a0c10"
              alt="GitHub stars"
              className="h-4"
            />
          </a>
        </div>
      </div>
    </section>
  );
}
