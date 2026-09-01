"use client";

import Link from "next/link";
import { useEffect } from "react";
import { ArrowRight, ExternalLink, Megaphone, Rocket, X } from "lucide-react";
import type { UpdateRelease } from "@/lib/version";

interface Props {
  open: boolean;
  onClose: () => void;
  release: UpdateRelease;
  onSeeAll: () => void;
}

function safeHref(url: string | null | undefined): string {
  if (!url) return "#";
  if (url.startsWith("/") || url.startsWith("https://") || url.startsWith("http://")) return url;
  return "#";
}

/**
 * Hero modal for a FEATURED release. Big changes (desktop app, Settings
 * redesign, keyboard shortcuts) get a centered, attention-grabbing "What's new"
 * dialog on open, showing the release title + highlights + the pull-and-restart
 * command. It's acknowledged per-release (like the banner), so it shows once
 * and never re-pops until a new featured release lands.
 */
export default function WhatsNewModal({ open, onClose, release, onSeeAll }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  const title = release.title ?? release.tag ?? "What's new";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="whats-new-modal-title"
      className="fixed inset-0 z-[110] grid place-items-center p-4"
    >
      <div
        aria-hidden
        className="absolute inset-0 bg-black/60 backdrop-blur-[3px] animate-[tt-fade-in_120ms_ease-out]"
        onClick={onClose}
      />
      <div className="relative w-full max-w-[560px] bg-[var(--tt-panel)] border border-[var(--tt-border-strong)] rounded-[var(--tt-radius-lg)] shadow-[0_32px_80px_-20px_rgba(0,0,0,0.7)] overflow-hidden animate-[tt-modal-in_180ms_ease-out]">
        {/* Brand accent bar */}
        <div aria-hidden className="h-1.5 w-full bg-[linear-gradient(90deg,var(--tt-brand),#a78bfa,#60a5fa)]" />

        {/* Header */}
        <div className="flex items-start justify-between gap-3 px-6 pt-5">
          <div className="flex items-center gap-2.5">
            <span className="h-9 w-9 grid place-items-center rounded-[var(--tt-radius)] bg-[var(--tt-brand)]/15 text-[var(--tt-brand)]">
              <Rocket size={18} />
            </span>
            <div>
              <div className="flex items-center gap-1.5 text-[10.5px] font-extrabold uppercase tracking-[0.16em] text-[var(--tt-brand)]">
                <Megaphone size={11} /> Big new release
              </div>
              <h2 id="whats-new-modal-title" className="text-[19px] font-semibold tracking-[-0.01em] text-[var(--tt-fg)] leading-tight">
                {title}
              </h2>
            </div>
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

        {/* Highlights */}
        <div className="px-6 py-5 space-y-3">
          {release.highlights.length === 0 ? (
            <p className="text-[13px] text-[var(--tt-fg-muted)]">
              A new version is available. Pull and restart to get it.
            </p>
          ) : (
            release.highlights.slice(0, 4).map((h, i) => (
              <div
                key={i}
                className="flex gap-3 rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-sunken)] px-4 py-3"
              >
                <span aria-hidden className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--tt-brand)]" />
                <div className="min-w-0">
                  <p className="text-[13.5px] font-semibold text-[var(--tt-fg)]">{h.title}</p>
                  {h.description && (
                    <p className="mt-1 text-[12.5px] leading-relaxed text-[var(--tt-fg-muted)]">
                      {h.description}
                    </p>
                  )}
                  {h.href && (h.href.startsWith("/") ? (
                    <Link
                      href={h.href}
                      onClick={onClose}
                      className="mt-1 inline-flex items-center gap-1 text-[12px] font-medium text-[var(--tt-brand)] hover:text-[var(--tt-brand-strong)]"
                    >
                      Open feature <ArrowRight size={11} />
                    </Link>
                  ) : (
                    <a
                      href={safeHref(h.href)}
                      target="_blank" rel="noopener noreferrer"
                      className="mt-1 inline-flex items-center gap-1 text-[12px] font-medium text-[var(--tt-brand)] hover:text-[var(--tt-brand-strong)]"
                    >
                      Learn more <ExternalLink size={11} />
                    </a>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--tt-border)] px-6 py-4">
          <div className="text-[11px] text-[var(--tt-fg-dim)]">
            Update command: <code className="font-mono text-[var(--tt-fg)]">git pull &amp;&amp; ./start.sh</code>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onSeeAll}
              className="inline-flex items-center gap-1.5 rounded-md border border-[var(--tt-border-strong)] px-3 py-1.5 text-[12px] font-medium text-[var(--tt-fg)] hover:bg-[var(--tt-sunken)] transition-colors"
            >
              See everything <ArrowRight size={12} />
            </button>
            <button
              type="button"
              onClick={onClose}
              className="inline-flex items-center gap-1.5 rounded-md bg-[var(--tt-brand)] px-3 py-1.5 text-[12px] font-semibold text-white hover:bg-[var(--tt-brand-strong)] transition-colors"
            >
              Got it
            </button>
          </div>
        </div>

        <style>{`
          @keyframes tt-fade-in {
            from { opacity: 0; }
            to   { opacity: 1; }
          }
          @keyframes tt-modal-in {
            from { transform: translateY(10px) scale(0.97); opacity: 0; }
            to   { transform: translateY(0) scale(1);       opacity: 1; }
          }
          @media (prefers-reduced-motion: reduce) {
            [aria-labelledby="whats-new-modal-title"] *[style*="tt-"] {
              animation: none !important;
            }
          }
        `}</style>
      </div>
    </div>
  );
}
