"use client";

import { useEffect, useSyncExternalStore } from "react";
import { Languages } from "lucide-react";
import { cn } from "@/lib/cn";
import { getLocale, setLocale, subscribe, type Locale } from "@/lib/i18n/locale";
import { PHRASES, CHINESE } from "@/lib/i18n/dict";

/**
 * Runtime-translation overlay + sidebar language switch.
 *
 * When the language is Chinese, the overlay walks rendered text nodes and swaps
 * known English phrases for their Chinese equivalents, then keeps translating as
 * the app mounts/updates via a MutationObserver. Switching to English restores
 * the originals it recorded. All of this happens in place — no reload — so the
 * collapsed sidebar never flashes open.
 *
 * Matching is exact (whole text-node === a dictionary key), so numbers, ids,
 * paths and proper nouns are never mangled. Interpolated strings and
 * title/placeholder/aria attributes are not matched and stay English.
 */

const SKIP_SELECTOR = "pre, code, textarea, script, style, noscript, option";

const serverSnapshot = (): Locale => "en";

export default function LocaleOverlay() {
  const locale = useSyncExternalStore(subscribe, getLocale, serverSnapshot);

  useEffect(() => {
    if (typeof document === "undefined") return;
    if (locale !== "zh") {
      document.documentElement.lang = "en";
      return;
    }
    document.documentElement.lang = "zh";

    // Remember the original (English) value of every node we translate so it can
    // be restored when the language is switched off.
    const originals = new Map<Text, string>();

    const translateNode = (node: Text) => {
      const raw = node.nodeValue || "";
      const text = raw.trim();
      if (!text || CHINESE.has(text) || !(text in PHRASES)) return;
      if (node.parentElement?.closest(SKIP_SELECTOR)) return;
      if (!originals.has(node)) originals.set(node, raw);
      const translated = PHRASES[text];
      if (node.nodeValue !== translated) node.nodeValue = translated;
    };

    const pass = () => {
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      for (let n = walker.nextNode(); n; n = walker.nextNode()) translateNode(n as Text);
    };

    // Coalesce bursts of mutations (polling, route swaps) into one pass.
    let applying = false;
    let frame = 0;
    const schedule = () => {
      if (applying) return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        applying = true;
        try {
          pass();
        } finally {
          applying = false;
        }
      });
    };

    pass();
    const observer = new MutationObserver(schedule);
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });

    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
      // Put back the untouched English for anything still showing our translation.
      originals.forEach((original, node) => {
        if (node.isConnected && node.nodeValue === PHRASES[original.trim()]) {
          node.nodeValue = original;
        }
      });
      originals.clear();
    };
  }, [locale]);

  return null;
}

/**
 * Sidebar language switch, styled to sit beside <ThemeToggle>. Mounted only in
 * Navigation (its one added line). Switching notifies the overlay above, which
 * translates or restores in place — so it is instant and reload-free.
 */
export function LanguageSwitch({ collapsed }: { collapsed?: boolean }) {
  const locale = useSyncExternalStore(subscribe, getLocale, serverSnapshot);
  const toggle = () => setLocale(locale === "zh" ? "en" : "zh");

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label="切换界面语言 / Switch interface language"
      title="切换界面语言 / Switch interface language"
      className={cn(
        "w-full flex items-center rounded-[var(--tt-radius)] border border-transparent transition-colors",
        "text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)] hover:border-[var(--tt-border)] hover:tt-tint-1",
        collapsed ? "justify-center h-9" : "justify-between gap-2 px-2 h-9",
      )}
    >
      {collapsed ? (
        <Languages size={15} />
      ) : (
        <span className="flex items-center gap-2 text-[10px] uppercase tracking-[0.18em]">
          <Languages size={13} />
          {locale === "zh" ? "中文" : "English"}
        </span>
      )}
    </button>
  );
}
