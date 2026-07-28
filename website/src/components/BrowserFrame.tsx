import { Activity } from "lucide-react";
import type { ReactNode } from "react";

/**
 * Shared "browser/app window" chrome — three traffic-light dots + a mono label.
 * Used by the hero boot sequence and the feature showcase so the product
 * surface always reads as a real screen. Children render directly under the
 * title bar (an <img>, a <video>, or animated content), so a static screenshot
 * today can be swapped for a short looping clip later without touching callers.
 *
 * `tab` replaces the default label span when provided (e.g. the hero swaps the
 * scan label for its localhost lock pill after the boot resolves).
 */
export default function BrowserFrame({
  label,
  tab,
  children,
  className = "",
}: {
  label: string;
  tab?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`relative rounded-[var(--tt-radius-lg)] sm:rounded-[var(--tt-radius-xl)] overflow-hidden border border-[var(--tt-border-strong)] bg-[var(--tt-panel)] shadow-[0_30px_120px_-30px_rgba(96,165,250,0.30)] ${className}`}
    >
      <div className="flex items-center gap-1.5 px-3 sm:px-4 h-9 bg-[var(--tt-raised)] border-b border-[var(--tt-border)]">
        <span className="w-2.5 h-2.5 rounded-full bg-rose-400/50" />
        <span className="w-2.5 h-2.5 rounded-full bg-amber-400/50" />
        <span className="w-2.5 h-2.5 rounded-full bg-emerald-400/50" />
        {tab ?? (
          <span className="ml-3 inline-flex items-center gap-1.5 text-[11px] font-mono text-[var(--tt-fg-dim)] truncate">
            <Activity size={11} className="text-[var(--tt-brand)]" />
            {label}
          </span>
        )}
      </div>
      {children}
    </div>
  );
}
