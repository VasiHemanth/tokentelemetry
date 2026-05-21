"use client";

import Navigation from "./Navigation";
import FeedbackFloatingButton from "./feedback/FeedbackFloatingButton";
import { useEffect, useState } from "react";

export default function LayoutWrapper({ children }: { children: React.ReactNode }) {
  const [isCollapsed, setIsCollapsed] = useState(false);

  useEffect(() => {
    // URL override (e.g. ?sidebar=collapsed) wins over localStorage — useful for
    // screenshots and embedded views.
    const params = new URLSearchParams(window.location.search);
    const fromUrl = params.get("sidebar");
    if (fromUrl === "collapsed" || fromUrl === "expanded") {
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

  return (
    <body className="min-h-full flex bg-[var(--tt-canvas)] overflow-hidden">
      <Navigation isCollapsed={isCollapsed} setIsCollapsed={toggle} />
      <main className="flex-1 h-screen overflow-y-auto relative">
        {/* Ambient canvas — single source of background atmosphere */}
        <div aria-hidden className="pointer-events-none absolute inset-0 tt-canvas-glow" />
        <div aria-hidden className="pointer-events-none absolute inset-0 tt-grid opacity-40" />
        <div className="relative z-10">{children}</div>
      </main>
      <FeedbackFloatingButton />
    </body>
  );
}
