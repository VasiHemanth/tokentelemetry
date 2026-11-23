"use client";

import { useEffect, useState } from "react";
// lucide-react 1.x dropped brand icons, so generic ones stand in for the platforms.
import { X, SquarePlay, Camera, ArrowUpRight } from "lucide-react";
import { RESEARCH_CHANNELS, RESOURCES_URL } from "@/lib/researchChannels";

const DISMISSED_KEY = "tt-research-card-dismissed";
// Set by TelemetryNotice when the first-run notice is dismissed. The card waits
// for it so two notices never show at once on a first launch.
const TELEMETRY_NOTICE_KEY = "tt-telemetry-notice";
const SHOW_DELAY_MS = 8000;

/**
 * A one-time card pointing to the maker's AI research channels. It appears a
 * few seconds into a later visit, never over the first-run telemetry notice,
 * and closing it hides it for good on this browser. Links only; no tracking.
 */
export default function ResearchChannelsCard() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let dismissed = true;
    let noticeDone = false;
    try {
      dismissed = localStorage.getItem(DISMISSED_KEY) === "1";
      noticeDone = localStorage.getItem(TELEMETRY_NOTICE_KEY) === "seen";
    } catch {
      return; // storage blocked: never show rather than show on every load
    }
    if (dismissed || !noticeDone) return;
    const t = setTimeout(() => setOpen(true), SHOW_DELAY_MS);
    return () => clearTimeout(t);
  }, []);

  const close = () => {
    setOpen(false);
    try {
      localStorage.setItem(DISMISSED_KEY, "1");
    } catch {
      /* ignore */
    }
  };

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-labelledby="tt-research-title"
      className="fixed right-4 bottom-20 z-40 w-[min(340px,calc(100vw-2rem))] rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] shadow-lg p-4"
    >
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--tt-fg-dim)]">From the maker</p>
          <h2 id="tt-research-title" className="mt-1 text-[14px] font-semibold text-[var(--tt-fg)]">
            Follow my AI research
          </h2>
        </div>
        <button
          type="button"
          onClick={close}
          aria-label="Close and don't show again"
          className="shrink-0 p-1 rounded text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)] hover:tt-tint-1"
        >
          <X size={14} />
        </button>
      </div>

      <ul className="mt-3 space-y-1.5">
        {RESEARCH_CHANNELS.map((c) => (
          <li key={c.url}>
            <a
              href={c.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2.5 rounded-[var(--tt-radius)] px-2 py-1.5 hover:tt-tint-1 group"
            >
              {c.platform === "Instagram" ? (
                <Camera size={15} className="shrink-0 text-[var(--tt-fg-muted)]" />
              ) : (
                <SquarePlay size={15} className="shrink-0 text-[var(--tt-fg-muted)]" />
              )}
              <span className="min-w-0 flex-1">
                <span className="block text-[13px] font-medium text-[var(--tt-fg)] group-hover:text-[var(--tt-brand)]">
                  {c.name} <span className="text-[11px] font-normal text-[var(--tt-fg-dim)]">· {c.platform}</span>
                </span>
                <span className="block text-[12px] text-[var(--tt-fg-muted)]">{c.summary}</span>
              </span>
              <ArrowUpRight size={13} className="shrink-0 text-[var(--tt-fg-dim)]" />
            </a>
          </li>
        ))}
      </ul>

      <a
        href={RESOURCES_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-3 inline-block text-[12px] text-[var(--tt-brand)] hover:underline"
      >
        More on the Resources page
      </a>
    </div>
  );
}
