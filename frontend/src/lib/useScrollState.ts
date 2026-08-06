"use client";

import { useCallback, useEffect, useRef } from "react";
import { registerStateKey } from "@/lib/pageState";

type ScrollTarget = HTMLElement | Window | null;

function getPageContainer(): ScrollTarget {
  if (typeof document === "undefined") return null;
  return document.querySelector("main") ?? window;
}

function getScrollTop(target: ScrollTarget): number {
  if (!target) return 0;
  return "scrollTop" in target ? target.scrollTop : target.scrollY;
}

function scrollToY(target: ScrollTarget, y: number): void {
  if (!target) return;
  if ("scrollTop" in target) {
    target.scrollTop = y;
  } else {
    target.scrollTo({ top: y, behavior: "instant" });
  }
}

/**
 * Persists and restores scroll position for a page or scrollable element.
 *
 * - Targets the page <main> container by default, or an element bound via the returned `ref` + `onScroll`. 
 * - Positions are stored in sessionStorage under `scroll_<key>` and restored once `isReady` becomes true.
 */
export function useScrollState(key: string, isReady: boolean = true) {
  const nodeRef = useRef<HTMLElement | null>(null);
  const isRestoringRef = useRef(false);
  const restoredRef = useRef(false);

  useEffect(() => {
    registerStateKey(`scroll_${key}`);
  }, [key]);

  const saveScrollPosition = useCallback((top: number) => {
    if (isRestoringRef.current) return;      
    sessionStorage.setItem(`scroll_${key}`, String(top));
  },[key]);

  const ref = useCallback((node: HTMLElement | null) => {
    nodeRef.current = node;
  }, []);

  const onScroll = useCallback((e: React.UIEvent<HTMLElement>) => {
    saveScrollPosition(e.currentTarget.scrollTop);
  },[saveScrollPosition]);

  useEffect(() => {
    const target = nodeRef.current ?? getPageContainer();
    if (!target) return;

    if ("scrollRestoration" in window.history) {
      window.history.scrollRestoration = "manual";
    }

    // Restore the saved position once, when the page is ready to paint.
    if (isReady && !restoredRef.current) {
      const savedStr = sessionStorage.getItem(`scroll_${key}`);
      const savedY = savedStr ? parseInt(savedStr, 10) : 0;

      if (!isNaN(savedY) && savedY > 0) {
        isRestoringRef.current = true;
        requestAnimationFrame(() => {
          scrollToY(target, savedY);
          isRestoringRef.current = false;
          restoredRef.current = true;
        });
      } else {
        restoredRef.current = true;
      }
    }

    // Persist the position, debounced, while the user scrolls.
    let timer: ReturnType<typeof setTimeout> | null = null;

    const handleScrollPosition = () => {
      if (isRestoringRef.current) return;
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => saveScrollPosition(getScrollTop(target)), 50);
    };

    target.addEventListener("scroll", handleScrollPosition, { passive: true });

    return () => {
      if (timer) clearTimeout(timer);
      target.removeEventListener("scroll", handleScrollPosition);
    };
  }, [key, isReady, saveScrollPosition]);

  return { ref, onScroll };
}
