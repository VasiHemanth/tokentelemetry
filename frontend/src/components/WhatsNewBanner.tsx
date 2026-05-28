"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Sparkles, X, ArrowUpRight } from "lucide-react";

/**
 * Top-of-app "What's new" banner.
 *
 * Curated, hand-maintained — bump `RELEASE_TAG` whenever the highlights below
 * change, and the banner re-appears for everyone (including users who
 * dismissed the previous tag). Per-tag dismissal lives in localStorage so a
 * user only sees each set of highlights once.
 *
 * Intentionally lightweight: no network calls, no GitHub API. Just a friendly
 * pointer at the newest user-facing surfaces. When we want a true update
 * checker (GitHub releases polling) this component can be replaced or extended.
 *
 * Visual: vibrant brand-tinted gradient with a left accent rail, a glow-pulsed
 * "NEW" pill, and pill-styled feature chips. Stands out without being noisy.
 */

const RELEASE_TAG = "2026-05-28b";  // bumped: dropped session-traces, redesigned
const STORAGE_KEY = "tt-whats-new-dismissed";

interface Highlight {
  label: string;
  href: string;
}

const HIGHLIGHTS: Highlight[] = [
  { label: "Summarizer settings", href: "/settings" },
  { label: "Hermes dashboard",    href: "/hermes" },
];

export default function WhatsNewBanner() {
  // `null` = haven't read localStorage yet → render nothing (avoids SSR/CSR
  // flash where the banner appears for a frame before being dismissed).
  const [visible, setVisible] = useState<boolean | null>(null);

  useEffect(() => {
    try {
      const dismissedTag = window.localStorage.getItem(STORAGE_KEY);
      setVisible(dismissedTag !== RELEASE_TAG);
    } catch {
      // Storage blocked (Safari ITP, private mode). Show it; we just can't
      // remember the dismissal across sessions.
      setVisible(true);
    }
  }, []);

  function dismiss() {
    try { window.localStorage.setItem(STORAGE_KEY, RELEASE_TAG); } catch { /* ignore */ }
    setVisible(false);
  }

  if (!visible) return null;

  return (
    <div
      role="status"
      aria-label="What's new in TokenTelemetry"
      className="relative overflow-hidden border-b border-[var(--tt-brand)]/20 bg-[linear-gradient(90deg,rgba(96,165,250,0.18)_0%,rgba(96,165,250,0.08)_45%,rgba(96,165,250,0.02)_100%)]"
    >
      {/* Left accent rail — saturated brand stripe so the eye picks it up immediately. */}
      <div aria-hidden className="absolute inset-y-0 left-0 w-[3px] bg-[var(--tt-brand)]" />

      {/* Subtle moving shimmer across the bar; pure cosmetic, masked by opacity. */}
      <div
        aria-hidden
        className="absolute inset-y-0 left-0 w-1/3 pointer-events-none opacity-30"
        style={{
          background: "linear-gradient(90deg, transparent 0%, rgba(96,165,250,0.25) 50%, transparent 100%)",
          animation: "tt-whatsnew-shimmer 6s linear infinite",
        }}
      />

      <div className="relative flex items-center gap-4 px-5 sm:px-7 py-2.5">
        <span className="inline-flex items-center gap-1.5 shrink-0 rounded-full bg-[var(--tt-brand)]/15 border border-[var(--tt-brand)]/40 px-2.5 py-1 text-[10.5px] font-extrabold uppercase tracking-[0.16em] text-[var(--tt-brand)]">
          <span
            className="grid place-items-center"
            style={{ animation: "tt-whatsnew-pulse 2.4s ease-in-out infinite" }}
          >
            <Sparkles size={11} />
          </span>
          New
        </span>

        <div className="flex flex-wrap items-center gap-2 min-w-0 flex-1">
          <span className="text-[12.5px] font-medium text-[var(--tt-fg)] mr-1">
            Just shipped:
          </span>
          {HIGHLIGHTS.map((h) => (
            <Link
              key={h.href}
              href={h.href}
              className="group inline-flex items-center gap-1.5 rounded-full border border-[var(--tt-brand)]/30 bg-[var(--tt-panel)]/70 backdrop-blur px-3 py-1 text-[12px] font-semibold text-[var(--tt-fg)] hover:bg-[var(--tt-brand)]/15 hover:border-[var(--tt-brand)]/50 transition-colors"
            >
              {h.label}
              <ArrowUpRight
                size={12}
                className="opacity-60 transition-transform group-hover:opacity-100 group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
              />
            </Link>
          ))}
        </div>

        <button
          type="button"
          onClick={dismiss}
          aria-label="Dismiss what's new"
          className="shrink-0 h-7 w-7 grid place-items-center rounded-md text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] hover:bg-[var(--tt-panel)] transition-colors"
        >
          <X size={14} />
        </button>
      </div>

      {/* Inline keyframes — kept here so the banner is self-contained and removable. */}
      <style>{`
        @keyframes tt-whatsnew-shimmer {
          0%   { transform: translateX(-100%); }
          100% { transform: translateX(400%); }
        }
        @keyframes tt-whatsnew-pulse {
          0%, 100% { transform: scale(1);   opacity: 1; }
          50%      { transform: scale(1.15); opacity: 0.75; }
        }
        @media (prefers-reduced-motion: reduce) {
          [aria-label="What's new in TokenTelemetry"] *[style*="tt-whatsnew"] {
            animation: none !important;
          }
        }
      `}</style>
    </div>
  );
}
