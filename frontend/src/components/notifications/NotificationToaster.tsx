"use client";

import Link from "next/link";
import { AlertTriangle, ArrowRight, X } from "lucide-react";

import { cn } from "@/lib/cn";
import { type AppNotification } from "@/lib/notifications";
import { useNotifications } from "./NotificationProvider";

/**
 * One-time active surface for new notifications. Per the chosen pattern
 * ("top banner once, then bell"), this renders the not-yet-surfaced rows as a
 * top banner; dismissing (or following) acknowledges them and they live on in
 * the bell. The provider guarantees each row appears here at most once.
 */
export default function NotificationToaster() {
  const { toToast, acknowledgeToasts } = useNotifications();
  if (toToast.length === 0) return null;

  // Show the most severe as the headline; collapse the rest into "+N more".
  const sorted = [...toToast].sort(severityRank);
  const top = sorted[0];
  const extra = sorted.length - 1;
  const over = top.severity === "over";

  return (
    <div
      role="status"
      aria-label="New notification"
      className={cn(
        "relative border-b",
        over
          ? "border-[color:var(--tt-danger)]/25 bg-gradient-to-r from-[color:var(--tt-danger)]/12 to-transparent"
          : "border-[color:var(--tt-warn)]/25 bg-gradient-to-r from-[color:var(--tt-warn)]/12 to-transparent",
      )}
    >
      <div className="flex items-center gap-3 px-4 py-2.5 max-w-[1600px] mx-auto">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <AlertTriangle
            size={15}
            className={cn("shrink-0", over ? "text-[var(--tt-danger)]" : "text-[var(--tt-warn)]")}
          />
          <span className="text-[13px] text-[var(--tt-fg)] font-medium truncate">{top.title}</span>
          {top.body && (
            <span className="text-[12px] text-[var(--tt-fg-dim)] truncate hidden sm:inline">
              — {top.body}{extra > 0 && ` · +${extra} more`}
            </span>
          )}
          {!top.body && extra > 0 && (
            <span className="text-[12px] text-[var(--tt-fg-dim)]">+{extra} more</span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {top.href && (
            <Link
              href={top.href}
              onClick={acknowledgeToasts}
              className="inline-flex items-center gap-1 h-7 px-2.5 rounded-[var(--tt-radius)] text-[12px] text-[var(--tt-fg)] hover:tt-tint-1 transition-colors"
            >
              View <ArrowRight size={13} />
            </Link>
          )}
          <button
            onClick={acknowledgeToasts}
            aria-label="Dismiss"
            className="grid place-items-center h-7 w-7 rounded-[var(--tt-radius)] text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)] hover:tt-tint-1 transition-colors"
          >
            <X size={15} />
          </button>
        </div>
      </div>
    </div>
  );
}

function severityRank(a: AppNotification, b: AppNotification): number {
  const rank = (s: string) => (s === "over" ? 2 : s === "warn" ? 1 : 0);
  return rank(b.severity) - rank(a.severity);
}
