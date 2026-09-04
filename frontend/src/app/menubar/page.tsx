"use client";

/**
 * The tray panel: what opens when the TokenTelemetry icon in the system tray or
 * menu bar is clicked.
 *
 * Rendered as HTML rather than drawn natively, which is what lets it reuse the
 * dashboard's own plan-limits design (PlanLimitsList) and its real agent logos
 * instead of reimplementing both against a native drawing API per platform.
 *
 * Chrome-free by route: LayoutWrapper renders this path without the sidebar,
 * banner or ambient canvas, because a popover sized for a menu has no room for
 * navigation and nowhere to navigate to.
 *
 * Links are deliberately absent. Following one would replace the panel with a
 * full dashboard page inside a window sized for a menu; anything that wants the
 * dashboard asks the shell to open the real window instead.
 */

import { useState } from "react";
import { ExternalLink, Loader2, RefreshCw } from "lucide-react";

import { useQuotas } from "@/components/QuotaProvider";
import { PlanLimitsList, UnavailableFooter } from "@/components/quota/PlanLimitsList";

/** Ask the desktop shell to surface the main window, when one is hosting us. */
function openDashboard(path: string) {
  const shell = (window as unknown as {
    tokentelemetry?: { openDashboard?: (path: string) => void };
  }).tokentelemetry;
  if (shell?.openDashboard) {
    shell.openDashboard(path);
    return;
  }
  // Opened in a plain browser tab (dev, or someone visiting /menubar directly):
  // navigating in place is the only thing available and is not harmful there.
  window.location.href = path;
}

export default function MenubarPanel() {
  const { data, refresh } = useQuotas();
  const [refreshing, setRefreshing] = useState(false);

  const providers = Object.entries(data?.providers ?? {});
  const unavailable = Object.values(data?.capabilities ?? {}).filter((c) => c.state !== "available");

  const doRefresh = async () => {
    setRefreshing(true);
    try {
      await refresh();
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="flex h-screen w-full flex-col bg-[var(--tt-panel)] text-[var(--tt-fg)]">
      <header className="flex shrink-0 items-center justify-between gap-2 border-b border-[var(--tt-border)] px-3.5 py-2.5">
        <span className="text-[12px] font-semibold">Plan limits</span>
        <span className="flex items-center gap-1">
          <button
            type="button"
            onClick={doRefresh}
            disabled={refreshing}
            aria-label="Refresh plan limits"
            title="Refresh plan limits"
            className="inline-flex h-6 w-6 items-center justify-center rounded-md text-[var(--tt-fg-muted)] transition-colors hover:bg-[var(--tt-sunken)] hover:text-[var(--tt-fg)] disabled:opacity-50"
          >
            {refreshing ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
          </button>
          <button
            type="button"
            onClick={() => openDashboard("/")}
            aria-label="Open dashboard"
            title="Open dashboard"
            className="inline-flex h-6 w-6 items-center justify-center rounded-md text-[var(--tt-fg-muted)] transition-colors hover:bg-[var(--tt-sunken)] hover:text-[var(--tt-fg)]"
          >
            <ExternalLink size={13} />
          </button>
        </span>
      </header>

      <div className="min-h-0 flex-1 divide-y divide-[var(--tt-border)] overflow-y-auto">
        <PlanLimitsList providers={providers} />
      </div>

      <div className="shrink-0">
        <UnavailableFooter unavailable={unavailable} onNavigate={() => openDashboard("/agents")} />
      </div>
    </div>
  );
}
