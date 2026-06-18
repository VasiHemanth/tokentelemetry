"use client";
import Link from "next/link";
import { useState } from "react";
import { Star, Activity, Menu, X } from "lucide-react";
import { track } from "@/lib/track";
import { useGithubStats } from "@/lib/useGithubStats";

const GITHUB_URL = "https://github.com/VasiHemanth/tokentelemetry";

export default function SiteHeader() {
  const { stars } = useGithubStats();
  const [menuOpen, setMenuOpen] = useState(false);
  const closeMenu = () => setMenuOpen(false);

  return (
    <header className="sticky top-0 z-50 border-b border-[var(--tt-border)] backdrop-blur-[14px]"
      style={{ background: "color-mix(in srgb, var(--tt-canvas) 82%, transparent)" }}>
      <div className="max-w-[1180px] mx-auto px-5 h-[58px] flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2.5 min-w-0" onClick={closeMenu}>
          <span className="h-7 w-7 grid place-items-center rounded-lg bg-gradient-to-br from-[var(--tt-brand-strong)] to-[var(--tt-brand-deep)] shadow-[0_6px_18px_-8px_var(--tt-brand-glow)]">
            <Activity size={16} strokeWidth={2.4} className="text-white" />
          </span>
          <span className="text-[15px] font-semibold tracking-[-0.01em] text-[var(--tt-fg)]">
            Token<span className="text-[var(--tt-fg-muted)] font-medium">Telemetry</span>
          </span>
        </Link>

        <div className="flex items-center gap-2">
          <Link
            href="/docs"
            onClick={() => track("click_nav", { to: "docs", location: "header" })}
            className="hidden sm:inline-flex items-center h-[34px] px-3 rounded-[var(--tt-radius)] text-[12.5px] font-medium text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] transition-colors"
          >
            Docs
          </Link>
          <Link
            href="/resources"
            onClick={() => track("click_nav", { to: "resources", location: "header" })}
            className="hidden sm:inline-flex items-center h-[34px] px-3 rounded-[var(--tt-radius)] text-[12.5px] font-medium text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] transition-colors"
          >
            Resources
          </Link>
          <a
            href={GITHUB_URL}
            target="_blank" rel="noopener noreferrer"
            onClick={() => track("click_github", { location: "header" })}
            className="inline-flex items-center gap-1.5 h-[34px] px-3 rounded-[var(--tt-radius)] border border-[var(--tt-border-strong)] bg-[var(--tt-panel)] text-[12.5px] font-medium text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] hover:border-[var(--tt-border-strong)] transition-colors"
          >
            <Star size={14} className="text-[var(--tt-warn)]" fill="currentColor" />
            <span className="text-[var(--tt-fg)] font-semibold">{stars}</span> stars
          </a>
          <a
            href="#install"
            onClick={() => track("click_install", { location: "header" })}
            className="hidden sm:inline-flex items-center h-[34px] px-3.5 rounded-[var(--tt-radius)] bg-[var(--tt-brand-strong)] hover:bg-[var(--tt-brand)] text-white text-[12.5px] font-semibold shadow-[0_8px_22px_-12px_var(--tt-brand-glow)] transition-colors"
          >
            Install
          </a>

          {/* Mobile menu toggle — the Docs/Resources/Install links above are
              hidden < sm, so on phones this hamburger is the only way to reach them. */}
          <button
            type="button"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((o) => !o)}
            className="sm:hidden inline-flex items-center justify-center h-[34px] w-[34px] rounded-[var(--tt-radius)] border border-[var(--tt-border-strong)] bg-[var(--tt-panel)] text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] transition-colors"
          >
            {menuOpen ? <X size={16} /> : <Menu size={16} />}
          </button>
        </div>
      </div>

      {/* Mobile dropdown */}
      {menuOpen && (
        <div className="sm:hidden border-t border-[var(--tt-border)] bg-[var(--tt-panel)]">
          <nav className="max-w-[1180px] mx-auto px-5 py-3 flex flex-col gap-1">
            <Link
              href="/docs"
              onClick={() => { track("click_nav", { to: "docs", location: "mobile_menu" }); closeMenu(); }}
              className="inline-flex items-center h-[40px] px-3 rounded-[var(--tt-radius)] text-[14px] font-medium text-[var(--tt-fg)] hover:bg-[var(--tt-raised)] transition-colors"
            >
              Docs
            </Link>
            <Link
              href="/resources"
              onClick={() => { track("click_nav", { to: "resources", location: "mobile_menu" }); closeMenu(); }}
              className="inline-flex items-center h-[40px] px-3 rounded-[var(--tt-radius)] text-[14px] font-medium text-[var(--tt-fg)] hover:bg-[var(--tt-raised)] transition-colors"
            >
              Resources
            </Link>
            <a
              href="#install"
              onClick={() => { track("click_install", { location: "mobile_menu" }); closeMenu(); }}
              className="inline-flex items-center justify-center h-[40px] px-3 mt-1 rounded-[var(--tt-radius)] bg-[var(--tt-brand-strong)] hover:bg-[var(--tt-brand)] text-white text-[14px] font-semibold transition-colors"
            >
              Install
            </a>
          </nav>
        </div>
      )}
    </header>
  );
}
