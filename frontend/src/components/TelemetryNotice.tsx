"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { BarChart3, X } from "lucide-react";
import { trackEvent, routeOf, agentOf, getTelemetry, setTelemetry, ackTelemetryNotice } from "@/lib/telemetry";

const SEEN_KEY = "tt-telemetry-notice";

/**
 * Two jobs, one mount (in LayoutWrapper):
 *   1. Emit a `page.viewed` event on every route change (the backend decides
 *      whether to actually send, and re-sanitizes — see telemetry.py).
 *   2. Show the one-time first-run notice. Telemetry is ON by default (opt-out),
 *      so this *informs* rather than asks: it states it's on, shows exactly what,
 *      and offers an equal-weight one-click "Turn off". Honoring the brand's
 *      transparency bar (docs/design/product-telemetry.md §5).
 *
 *      The notice is gated server-side via `notice_ack` in the local preferences
 *      DB — so it survives browser cache clears and never reshows after any choice.
 *      A localStorage fast-path avoids a flash-of-banner on repeat visits before
 *      the server round-trip completes.
 */
export default function TelemetryNotice() {
  const pathname = usePathname();
  const [showNotice, setShowNotice] = useState(false);
  const [busy, setBusy] = useState(false);
  const lastRoute = useRef<string | null>(null);

  // 1. Page-view tracking — dedupe consecutive identical routes.
  useEffect(() => {
    if (!pathname) return;
    const route = routeOf(pathname);
    const agent = agentOf(pathname);
    // Dedupe on route *and* agent, or moving between two harness panels would
    // look like one view of "agent-panel".
    const key = agent ? `${route}:${agent}` : route;
    if (key === lastRoute.current) return;
    lastRoute.current = key;
    trackEvent("page.viewed", agent ? { route, agent } : { route });
  }, [pathname]);

  // 2. First-run notice — the server `notice_ack` flag (local preferences DB) is
  // the single source of truth, so the choice survives browser cache clears and
  // never reshows on next launch. No localStorage read-gate: showNotice defaults
  // to false and only flips true once the server confirms, so there's no flash.
  useEffect(() => {
    if (typeof window === "undefined") return;
    let cancelled = false;
    getTelemetry()
      .then((s) => {
        // Show only when the server says it hasn't been acknowledged yet and
        // telemetry is not force-disabled by env or CI.
        if (!cancelled && !s.notice_ack && !s.env_forced_off && !s.is_ci) {
          setShowNotice(true);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const dismiss = async () => {
    // Hide immediately for a snappy feel.
    setShowNotice(false);
    // Write localStorage fast-path.
    try {
      localStorage.setItem(SEEN_KEY, "seen");
    } catch {
      /* ignore */
    }
    // Persist server-side so the banner never reappears after cache clears.
    try {
      await ackTelemetryNotice();
    } catch {
      /* best-effort */
    }
  };

  const turnOff = async () => {
    setBusy(true);
    try {
      await setTelemetry(false);
    } catch {
      /* best-effort */
    }
    setBusy(false);
    await dismiss();
  };

  if (!showNotice) return null;

  return (
    <div
      role="dialog"
      aria-label="Usage stats"
      className="fixed inset-x-0 bottom-0 z-50 px-4 pb-4 sm:px-6 sm:pb-6"
    >
      <div className="mx-auto max-w-[640px] rounded-[var(--tt-radius-lg)] border border-[var(--tt-border-strong)] bg-[var(--tt-panel)] shadow-[0_20px_60px_-20px_rgba(0,0,0,0.8)] backdrop-blur p-4 sm:p-5">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 h-7 w-7 shrink-0 grid place-items-center rounded-[var(--tt-radius)] tt-tint-2">
            <BarChart3 size={14} className="text-[var(--tt-brand)]" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-[13px] leading-relaxed text-[var(--tt-fg-muted)]">
              <strong className="text-[var(--tt-fg)]">TokenTelemetry respects your privacy</strong>{" "}
              — we collect a few anonymous usage stats to understand which features people use most,
              so we can keep improving the product for everyone.{" "}
              <strong className="text-[var(--tt-fg)]">Never</strong> your IP, code, prompts, file
              paths, or costs.
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={dismiss}
                disabled={busy}
                className="h-9 px-4 rounded-[var(--tt-radius)] bg-[var(--tt-brand)] text-[#04060a] text-[12.5px] font-semibold hover:bg-[var(--tt-brand-strong)] transition-colors disabled:opacity-50"
              >
                Keep it on
              </button>
              <button
                type="button"
                onClick={turnOff}
                disabled={busy}
                className="h-9 px-3.5 rounded-[var(--tt-radius)] border border-[var(--tt-border-strong)] text-[var(--tt-fg-muted)] text-[12.5px] font-medium hover:text-[var(--tt-fg)] hover:tt-tint-1 transition-colors disabled:opacity-50"
              >
                Turn off
              </button>
              <Link
                href="/settings#usage-privacy"
                onClick={dismiss}
                className="h-9 inline-flex items-center px-2 text-[12.5px] font-medium text-[var(--tt-fg-dim)] hover:text-[var(--tt-brand)] underline underline-offset-2 transition-colors"
              >
                See exactly what we collect
              </Link>
            </div>
          </div>
          <button
            type="button"
            onClick={dismiss}
            aria-label="Dismiss"
            className="shrink-0 h-7 w-7 grid place-items-center rounded-[var(--tt-radius)] text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)] hover:tt-tint-1 transition-colors"
          >
            <X size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}
