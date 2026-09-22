"use client";

import { useEffect, useSyncExternalStore } from "react";
import { getLocale, type Locale, subscribe } from "@/lib/i18n/locale";
import {
  BASE_LOCALE,
  applyDocumentLocale,
  isSourceLanguage,
  loadDictionary,
  peekDictionary,
  type LocaleDictionary,
} from "@/lib/i18n/registry";

/**
 * Runtime-translation overlay. The language control itself is <LanguageSetting>
 * on the Settings page — this component only reacts to whatever the store says.
 *
 * When a language other than the source is active, the overlay walks rendered
 * text nodes and swaps known English phrases for that language's equivalents,
 * then keeps translating as the app mounts/updates via a MutationObserver.
 * Switching back to the source language restores the originals it recorded.
 * All of this happens in place — no reload — so the collapsed sidebar never
 * flashes open.
 *
 * Languages come from `registry.ts`; this component knows nothing about any
 * specific one. Dictionaries are code-split, so switching pays for one lazy
 * chunk the first time and is instant afterwards.
 *
 * Matching is exact (whole text-node === a dictionary key), so numbers, ids,
 * paths and proper nouns are never mangled. Interpolated strings and
 * title/placeholder/aria attributes are not matched and stay English.
 */

const SKIP_SELECTOR = "pre, code, textarea, script, style, noscript, option";

const serverSnapshot = (): Locale => BASE_LOCALE;

/** One active translation pass over the DOM, with its own undo record. */
function attachOverlay(dictionary: LocaleDictionary) {
  // Remember the original (English) value of every node we translate so it can
  // be restored when the language is switched off.
  const originals = new Map<Text, string>();
  const { phrases, translated } = dictionary;

  const translateNode = (node: Text) => {
    const raw = node.nodeValue || "";
    const text = raw.trim();
    if (!text || translated.has(text) || !(text in phrases)) return;
    if (node.parentElement?.closest(SKIP_SELECTOR)) return;
    if (!originals.has(node)) originals.set(node, raw);
    const next = phrases[text];
    if (node.nodeValue !== next) node.nodeValue = next;
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
      if (node.isConnected && node.nodeValue === phrases[original.trim()]) {
        node.nodeValue = original;
      }
    });
    originals.clear();
  };
}

export default function LocaleOverlay() {
  const locale = useSyncExternalStore(subscribe, getLocale, serverSnapshot);

  useEffect(() => {
    if (typeof document === "undefined") return;
    applyDocumentLocale(locale);
    if (isSourceLanguage(locale)) return;

    let stop: (() => void) | null = null;
    let cancelled = false;

    const start = (dictionary: LocaleDictionary) => {
      // The language may have moved on while the chunk was in flight, and an
      // empty dictionary (a chunk that failed to load) has nothing to attach.
      if (cancelled || Object.keys(dictionary.phrases).length === 0) return;
      stop = attachOverlay(dictionary);
    };

    const ready = peekDictionary(locale);
    if (ready) start(ready);
    else loadDictionary(locale).then(start);

    return () => {
      cancelled = true;
      stop?.();
    };
  }, [locale]);

  return null;
}
