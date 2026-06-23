"use client";

import { useEffect, useState } from "react";
import { X, Copy, Check, RefreshCw, ArrowRight } from "lucide-react";
import WhatsChangedDrawer from "./WhatsChangedDrawer";
import { getVersion, type VersionInfo } from "@/lib/version";

/**
 * Top-of-app update banner.
 *
 * Renders only when the user's local checkout is behind the remote main. Pulls
 * the diff state + curated highlights from `GET /version` (backend in turn
 * compares local `git HEAD` to GitHub and reads UPDATE.json from the repo
 * root for the 1-3 highlights of what's new).
 *
 * "What's changed" opens an in-app slide-over with the highlights expanded
 * (title + description + optional href to the feature), keeping users inside
 * the dashboard instead of redirecting to a commit-list page on GitHub.
 *
 * Dismissal is keyed on the newest curated *release* id (`latest_release`,
 * "tag|title" from UPDATE.json) — NOT the commit SHA. So the banner only
 * re-surfaces when a new *feature* release lands; routine fix:/chore: commits
 * to main (which don't touch UPDATE.json) never re-pop it. Dismissal is a
 * one-time per-release acknowledgement — there is no time-based snooze.
 *
 * `behind` is computed server-side via git ancestry (not a SHA inequality), so
 * feature-branch / ahead / just-pulled checkouts don't show a false positive.
 * No GitHub API calls from the browser; backend handles all fetching + caching.
 */

const STORAGE_KEY = "tt-update-dismissed-release";
const GIT_PULL = "git pull && ./start.sh";

export default function WhatsNewBanner() {
  const [info, setInfo] = useState<VersionInfo | null>(null);
  const [dismissedRelease, setDismissedRelease] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    try { setDismissedRelease(window.localStorage.getItem(STORAGE_KEY)); }
    catch { setDismissedRelease(null); }

    let cancelled = false;
    getVersion()
      .then((d) => { if (!cancelled) setInfo(d); })
      .catch(() => { /* backend down or endpoint missing — silent */ });

    // Keep tabs in sync: if another tab dismisses, hide here too (and vice versa).
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) setDismissedRelease(e.newValue);
    };
    window.addEventListener("storage", onStorage);
    return () => { cancelled = true; window.removeEventListener("storage", onStorage); };
  }, []);

  // Render gates: need info, need to genuinely be behind, need a curated release
  // (so fix:/chore: pushes with no UPDATE.json entry stay silent), and that
  // release must not already be acknowledged.
  const isVisible =
    !!info && info.behind && !!info.latest_release && dismissedRelease !== info.latest_release;

  function dismiss() {
    if (!info?.latest_release) return;
    try { window.localStorage.setItem(STORAGE_KEY, info.latest_release); }
    catch { /* private mode etc. — banner just re-appears next visit */ }
    setDismissedRelease(info.latest_release);
    setDrawerOpen(false);
  }

  async function copyCmd() {
    try {
      await navigator.clipboard.writeText(GIT_PULL);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* clipboard blocked */ }
  }

  if (!isVisible || !info) return null;

  return (
    <>
      <div
        role="status"
        aria-label="TokenTelemetry update available"
        className="relative overflow-hidden border-b border-[var(--tt-brand)]/20 bg-[linear-gradient(90deg,rgba(96,165,250,0.18)_0%,rgba(96,165,250,0.08)_45%,rgba(96,165,250,0.02)_100%)]"
      >
        <div aria-hidden className="absolute inset-y-0 left-0 w-[3px] bg-[var(--tt-brand)]" />
        <div
          aria-hidden
          className="absolute inset-y-0 left-0 w-1/3 pointer-events-none opacity-30"
          style={{
            background: "linear-gradient(90deg, transparent 0%, rgba(96,165,250,0.25) 50%, transparent 100%)",
            animation: "tt-update-shimmer 6s linear infinite",
          }}
        />

        <div className="relative flex items-center gap-3 px-5 sm:px-7 py-2.5 flex-wrap">
          {/* Headline: "Update available for TokenTelemetry" — single source of
              meaning. Bullet details live inside the drawer. */}
          <span className="inline-flex items-center gap-1.5 shrink-0 text-[12.5px] font-semibold text-[var(--tt-fg)]">
            <RefreshCw
              size={13}
              className="text-[var(--tt-brand)]"
              style={{ animation: "tt-update-spin 3s linear infinite" }}
            />
            Update available for TokenTelemetry
          </span>

          {/* Spacer pushes the actions to the right when there's room. */}
          <div className="flex-1 min-w-0" />

          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={copyCmd}
              title={`Copy: ${GIT_PULL}`}
              className="inline-flex items-center gap-1.5 rounded-md border border-[var(--tt-border-strong)] bg-[var(--tt-panel)] px-2.5 py-1.5 text-[11.5px] font-mono font-medium text-[var(--tt-fg)] hover:border-[var(--tt-brand)]/40 hover:bg-[var(--tt-brand)]/10 transition-colors"
            >
              {copied ? <Check size={12} className="text-[var(--tt-success-fg)]" /> : <Copy size={12} />}
              <span>{copied ? "Copied" : GIT_PULL}</span>
            </button>

            {/* "What's changed" — outlined chip that fills with brand on hover.
                Reads as clickable (border + arrow) without competing with the
                brand-tinted banner background by being a solid filled button. */}
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              className="group inline-flex items-center gap-1.5 rounded-md border border-[var(--tt-brand)]/60 bg-[var(--tt-brand)]/10 px-3 py-1.5 text-[11.5px] font-semibold text-[var(--tt-brand)] hover:bg-[var(--tt-brand)] hover:text-white hover:border-[var(--tt-brand)] transition-colors"
            >
              What&apos;s changed
              <ArrowRight
                size={12}
                className="transition-transform group-hover:translate-x-0.5"
              />
            </button>

            <button
              type="button"
              onClick={dismiss}
              aria-label="Dismiss update banner"
              className="shrink-0 h-7 w-7 grid place-items-center rounded-md text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] hover:bg-[var(--tt-panel)] transition-colors"
            >
              <X size={14} />
            </button>
          </div>
        </div>

        <style>{`
          @keyframes tt-update-shimmer {
            0%   { transform: translateX(-100%); }
            100% { transform: translateX(400%); }
          }
          @keyframes tt-update-spin {
            0%   { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
          }
          @media (prefers-reduced-motion: reduce) {
            [aria-label="TokenTelemetry update available"] *[style*="tt-update"] {
              animation: none !important;
            }
          }
        `}</style>
      </div>

      <WhatsChangedDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        releases={info.releases}
        releaseUrl={info.release_url}
        repo={info.repo}
        currentSha={info.current}
        latestSha={info.latest}
      />
    </>
  );
}
