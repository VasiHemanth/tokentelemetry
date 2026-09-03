"use client";

import Navigation from "./Navigation";
import FeedbackFloatingButton from "./feedback/FeedbackFloatingButton";
import WhatsNewBanner from "./WhatsNewBanner";
import { NotificationProvider } from "./notifications/NotificationProvider";
import { QuotaProvider } from "./QuotaProvider";
import NotificationToaster from "./notifications/NotificationToaster";
import TokenGate from "./TokenGate";
import TelemetryNotice from "./TelemetryNotice";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";

/**
 * Routes rendered without any app chrome.
 *
 * The tray panel is a popover a few hundred pixels wide: a sidebar, banner and
 * ambient canvas have no room there and nowhere to navigate to. It keeps
 * QuotaProvider (its whole content comes from it) and drops the rest, including
 * the notification poller, which would be pure background cost in a panel that
 * never shows a notification.
 */
const BARE_ROUTES = ["/menubar"];

export default function LayoutWrapper({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [isCollapsed, setIsCollapsed] = useState(false);

  useEffect(() => {
    // URL override (e.g. ?sidebar=collapsed) wins over localStorage — useful for
    // screenshots and embedded views.
    const params = new URLSearchParams(window.location.search);
    const fromUrl = params.get("sidebar");
    if (fromUrl === "collapsed" || fromUrl === "expanded") {
      // Preserve hydration, then apply the browser-only URL preference.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setIsCollapsed(fromUrl === "collapsed");
      return;
    }
    const saved = localStorage.getItem("sidebar-collapsed");
    if (saved) setIsCollapsed(saved === "true");
  }, []);

  const toggle = (collapsed: boolean) => {
    setIsCollapsed(collapsed);
    localStorage.setItem("sidebar-collapsed", String(collapsed));
  };

  if (BARE_ROUTES.some((route) => pathname?.startsWith(route))) {
    return (
      <QuotaProvider>
        <body className="min-h-full overflow-hidden bg-[var(--tt-panel)]">{children}</body>
      </QuotaProvider>
    );
  }

  return (
    <NotificationProvider>
      <QuotaProvider>
      <body className="min-h-full flex bg-[var(--tt-canvas)] overflow-hidden">
        <Navigation isCollapsed={isCollapsed} setIsCollapsed={toggle} />
        <main className="flex-1 h-screen overflow-y-auto relative">
          {/* Ambient canvas — single source of background atmosphere */}
          <div aria-hidden className="pointer-events-none absolute inset-0 tt-canvas-glow" />
          <div aria-hidden className="pointer-events-none absolute inset-0 tt-grid opacity-40" />
          <div className="relative z-10">
            <WhatsNewBanner />
            <NotificationToaster />
            {children}
          </div>
        </main>
        <FeedbackFloatingButton />
        <TokenGate />
        <TelemetryNotice />
      </body>
      </QuotaProvider>
    </NotificationProvider>
  );
}
