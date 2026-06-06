"use client";

import Link from "next/link";
import { useEffect } from "react";
import { ArrowRight, ExternalLink, Sparkles, X } from "lucide-react";
import type { UpdateHighlight, UpdateRelease } from "@/lib/version";

interface Props {
  open: boolean;
  onClose: () => void;
  releases: UpdateRelease[];
  releaseUrl: string;
  repo: string;
  currentSha: string | null;
  latestSha: string | null;
}

/**
 * Neutralize hrefs whose data originates from the remote /version feed (which
 * can be poisoned via a compromised update cache or MITM). Only http(s) and
 * in-app absolute paths pass through; `javascript:`, `data:`, and any other
 * scheme collapse to "#" so a crafted release_url / highlight href can't
 * execute script when clicked (#56).
 */
function safeHref(url: string | null | undefined): string {
  if (!url) return "#";
  if (url.startsWith("/") || url.startsWith("https://") || url.startsWith("http://")) {
    return url;
  }
  return "#";
}

/**
 * Side-drawer that lists all curated releases from UPDATE.json — newest first.
 * The first release gets a "Latest" pill; older releases are shown as history
 * so users who fell behind by several updates can read everything they missed
 * in one panel without leaving the dashboard.
 */
export default function WhatsChangedDrawer({
  open, onClose, releases, releaseUrl, repo, currentSha, latestSha,
}: Props) {
  // Esc-to-close + body-scroll-lock — standard drawer ergonomics.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="whats-changed-title"
      className="fixed inset-0 z-[100]"
    >
      {/* Backdrop */}
      <div
        aria-hidden
        className="absolute inset-0 bg-black/55 backdrop-blur-[2px] animate-[tt-fade-in_120ms_ease-out]"
        onClick={onClose}
      />

      {/* Panel */}
      <aside
        className="absolute right-0 top-0 bottom-0 w-full max-w-[500px] bg-[var(--tt-panel)] border-l border-[var(--tt-border-strong)] shadow-[-24px_0_60px_-20px_rgba(0,0,0,0.6)] flex flex-col animate-[tt-slide-in_180ms_ease-out]"
      >
        {/* Header */}
        <div className="shrink-0 flex items-start justify-between gap-3 px-5 py-4 border-b border-[var(--tt-border)]">
          <div className="min-w-0">
            <div className="inline-flex items-center gap-1.5 text-[10.5px] font-extrabold uppercase tracking-[0.16em] text-[var(--tt-brand)] mb-1.5">
              <Sparkles size={11} /> What&apos;s new
            </div>
            <h2 id="whats-changed-title" className="text-[17px] font-semibold tracking-[-0.01em] text-[var(--tt-fg)]">
              Update available
            </h2>
            <p className="text-[12px] text-[var(--tt-fg-muted)] mt-0.5">
              Run <code className="font-mono text-[var(--tt-fg)]">git pull &amp;&amp; ./start.sh</code> to install everything below.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 h-8 w-8 grid place-items-center rounded-md text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] hover:bg-[var(--tt-sunken)] transition-colors"
          >
            <X size={15} />
          </button>
        </div>

        {/* Releases — newest first */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          {releases.length === 0 ? (
            <div className="rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-sunken)] px-4 py-5 text-[13px] text-[var(--tt-fg-muted)]">
              No curated highlights for this update. Use the link at the bottom
              to see the full commit history on GitHub.
            </div>
          ) : (
            releases.map((rel, i) => (
              <ReleaseSection
                key={(rel.tag ?? "") + i}
                release={rel}
                isLatest={i === 0}
                onLinkClick={onClose}
              />
            ))
          )}
        </div>

        {/* Footer */}
        <div className="shrink-0 border-t border-[var(--tt-border)] px-5 py-3 text-[11.5px] text-[var(--tt-fg-dim)] flex items-center justify-between gap-3 flex-wrap">
          <span className="font-mono">
            {currentSha?.slice(0, 7) ?? "?"} → {latestSha?.slice(0, 7) ?? "?"}
            <span className="ml-2 text-[var(--tt-fg-faint)]">on {repo}</span>
          </span>
          <a
            href={safeHref(releaseUrl)}
            target="_blank" rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] transition-colors"
          >
            Commit history on GitHub <ExternalLink size={11} />
          </a>
        </div>
      </aside>

      <style>{`
        @keyframes tt-fade-in {
          from { opacity: 0; }
          to   { opacity: 1; }
        }
        @keyframes tt-slide-in {
          from { transform: translateX(8%); opacity: 0; }
          to   { transform: translateX(0);  opacity: 1; }
        }
        @media (prefers-reduced-motion: reduce) {
          [aria-labelledby="whats-changed-title"] *[class*="animate-"] {
            animation: none !important;
          }
        }
      `}</style>
    </div>
  );
}

function ReleaseSection({
  release, isLatest, onLinkClick,
}: {
  release: UpdateRelease;
  isLatest: boolean;
  onLinkClick: () => void;
}) {
  const heading = release.title ?? release.tag ?? (isLatest ? "Latest" : "Earlier");
  return (
    <section>
      <header className="flex items-baseline gap-2 mb-2">
        <h3 className="text-[12px] font-semibold uppercase tracking-[0.12em] text-[var(--tt-fg-muted)]">
          {heading}
        </h3>
        {release.tag && release.title && (
          <span className="text-[10.5px] font-mono text-[var(--tt-fg-dim)]">{release.tag}</span>
        )}
        {isLatest && (
          <span className="ml-auto inline-flex items-center gap-1 rounded-full border border-[var(--tt-brand)]/40 bg-[var(--tt-brand)]/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--tt-brand)]">
            Latest
          </span>
        )}
      </header>
      <div className="space-y-2">
        {release.highlights.map((h, i) => (
          <HighlightCard key={i} highlight={h} onLinkClick={onLinkClick} dim={!isLatest} />
        ))}
      </div>
    </section>
  );
}

function HighlightCard({
  highlight: h, onLinkClick, dim,
}: {
  highlight: UpdateHighlight;
  onLinkClick: () => void;
  dim: boolean;
}) {
  return (
    <article
      className={
        "rounded-[var(--tt-radius-lg)] border px-4 py-3.5 " +
        (dim
          ? "border-[var(--tt-border)] bg-[var(--tt-canvas)]/60"
          : "border-[var(--tt-border)] bg-[var(--tt-sunken)]")
      }
    >
      <h4 className="text-[13.5px] font-semibold tracking-[-0.005em] text-[var(--tt-fg)]">
        {h.title}
      </h4>
      {h.description && (
        <p className="mt-1.5 text-[12.5px] leading-relaxed text-[var(--tt-fg-muted)]">
          {h.description}
        </p>
      )}
      {h.href && (
        h.href.startsWith("/") ? (
          <Link
            href={h.href}
            onClick={onLinkClick}
            className="mt-2.5 inline-flex items-center gap-1 text-[12px] font-medium text-[var(--tt-brand)] hover:text-[var(--tt-brand-strong)] transition-colors"
          >
            Open feature <ArrowRight size={12} />
          </Link>
        ) : (
          <a
            href={safeHref(h.href)}
            target="_blank" rel="noopener noreferrer"
            className="mt-2.5 inline-flex items-center gap-1 text-[12px] font-medium text-[var(--tt-brand)] hover:text-[var(--tt-brand-strong)] transition-colors"
          >
            Open <ExternalLink size={11} />
          </a>
        )
      )}
    </article>
  );
}
