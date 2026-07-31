"use client";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import {
  motion,
  useMotionValue,
  useMotionValueEvent,
  useReducedMotion,
  useScroll,
  useTransform,
  type MotionValue,
} from "motion/react";
import { FEATURES, type Feature } from "@/data/features";
import { webpSrcSet } from "@/lib/shots";
import { Check } from "lucide-react";
import BrowserFrame from "./BrowserFrame";
import { EASE } from "@/components/motion";
import SectionHead from "@/components/SectionHead";
import { track } from "@/lib/track";

const COUNT = FEATURES.length;
/** Each panel owns an equal slice of scroll progress. */
const SEG = 1 / COUNT;
/** Half-width of the crossfade band straddling each slice boundary. */
const BAND = SEG * 0.2;

/**
 * Natural pixel dimensions of each screenshot, so the fallback stack can
 * reserve image space (no CLS) and the pinned stage crops predictably.
 */
const SHOT_DIMS: Record<string, { w: number; h: number }> = {
  hermes: { w: 3200, h: 3000 },
  dashboard: { w: 3200, h: 3000 },
  traces: { w: 3200, h: 3000 },
  analytics: { w: 2912, h: 1662 },
  projects: { w: 3200, h: 2600 },
  artifacts: { w: 2880, h: 1840 },
};

const DESKTOP_QUERY = "(min-width: 768px)";

function subscribeDesktop(onChange: () => void): () => void {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return () => {};
  }
  const mql = window.matchMedia(DESKTOP_QUERY);
  mql.addEventListener("change", onChange);
  return () => mql.removeEventListener("change", onChange);
}

/** SSR renders the plain stack (false); desktop clients flip to the pinned stage after hydration. */
function useIsDesktop(): boolean {
  return useSyncExternalStore(
    subscribeDesktop,
    () =>
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia(DESKTOP_QUERY).matches,
    () => false,
  );
}

export default function FeatureShowcase() {
  const reduced = useReducedMotion();
  const isDesktop = useIsDesktop();
  // Below 768px or under prefers-reduced-motion: no pinning, no scroll-scrub.
  const pinned = isDesktop && !reduced;

  return (
    <section id="features" className="scroll-mt-[82px] max-w-[1320px] mx-auto px-5 sm:px-8 py-16 sm:py-24">
      <SectionHead
        index="05"
        label="see"
        title={
          <>
            One dashboard.{" "}
            <span className="text-[var(--tt-brand)]">Every agent.</span>
          </>
        }
      />
      {pinned ? <ScrubStage /> : <StaticStack />}
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Pinned scroll-scrubbed narrative (desktop, motion OK)               */
/* ------------------------------------------------------------------ */

function ScrubStage() {
  const wrapRef = useRef<HTMLDivElement>(null);
  const pillRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const rectsRef = useRef<{ x: number; w: number }[]>([]);
  const [activeIdx, setActiveIdx] = useState(0);

  const { scrollYProgress } = useScroll({
    target: wrapRef,
    offset: ["start start", "end end"],
  });

  // Underline position/width are set imperatively so a resize re-measure
  // takes effect immediately (not only on the next scroll event).
  const underlineX = useMotionValue(0);
  const underlineW = useMotionValue(0);

  const sync = useCallback(() => {
    const rects = rectsRef.current;
    if (rects.length !== COUNT) return;
    const v = scrollYProgress.get();
    // Continuous pill index: underline sits on pill i at slice center,
    // slides between neighbors as the boundary approaches.
    const t = Math.min(Math.max(v * COUNT - 0.5, 0), COUNT - 1);
    const i = Math.floor(t);
    const j = Math.min(i + 1, COUNT - 1);
    const f = t - i;
    // Inset 12px each side to match the original inset-x-3 underline.
    const ax = rects[i].x + 12;
    const bx = rects[j].x + 12;
    const aw = Math.max(rects[i].w - 24, 0);
    const bw = Math.max(rects[j].w - 24, 0);
    underlineX.set(ax + (bx - ax) * f);
    underlineW.set(aw + (bw - aw) * f);
    const idx = Math.min(Math.floor(v * COUNT), COUNT - 1);
    setActiveIdx((prev) => (prev === idx ? prev : idx));
  }, [scrollYProgress, underlineX, underlineW]);

  const measure = useCallback(() => {
    rectsRef.current = pillRefs.current.map((el) =>
      el ? { x: el.offsetLeft, w: el.offsetWidth } : { x: 0, w: 0 },
    );
    sync();
  }, [sync]);

  useEffect(() => {
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [measure]);

  useMotionValueEvent(scrollYProgress, "change", sync);

  // Scroll position stays the single source of truth: a pill click just
  // scrolls the window to the middle of that panel's slice.
  const scrollToPanel = useCallback((i: number) => {
    const el = wrapRef.current;
    if (!el) return;
    const top = el.getBoundingClientRect().top + window.scrollY;
    const scrollable = el.offsetHeight - window.innerHeight;
    window.scrollTo({
      top: top + ((i + 0.5) / COUNT) * scrollable,
      behavior: "smooth",
    });
    track("feature_tab", { id: FEATURES[i].id });
  }, []);

  const onKeyDown = (e: React.KeyboardEvent) => {
    let next: number | null = null;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") next = (activeIdx + 1) % COUNT;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") next = (activeIdx - 1 + COUNT) % COUNT;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = COUNT - 1;
    if (next !== null) {
      e.preventDefault();
      pillRefs.current[next]?.focus();
      scrollToPanel(next);
    }
  };

  return (
    // Tall scroll track: ~85vh of scroll per panel (~510vh total for 6).
    <div ref={wrapRef} style={{ height: `${COUNT * 85}vh` }}>
      <div className="sticky top-0 flex h-screen flex-col pt-20 pb-6">
        {/* Progress rail */}
        <div className="mb-5 shrink-0">
          <div
            role="tablist"
            aria-label="Product surfaces"
            onKeyDown={onKeyDown}
            className="relative mx-auto flex w-fit items-center gap-1 rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] px-1 py-1"
          >
            {FEATURES.map((f, i) => (
              <button
                key={f.id}
                ref={(el) => {
                  pillRefs.current[i] = el;
                }}
                role="tab"
                id={`feature-tab-${f.id}`}
                aria-controls={`feature-panel-${f.id}`}
                aria-selected={activeIdx === i}
                tabIndex={activeIdx === i ? 0 : -1}
                onClick={() => scrollToPanel(i)}
                className={`h-9 px-4 rounded-[var(--tt-radius)] text-[12.5px] font-medium tracking-tight whitespace-nowrap transition-colors ${
                  activeIdx === i
                    ? "text-[var(--tt-fg)]"
                    : "text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)]"
                }`}
              >
                {f.label}
              </button>
            ))}
            {/* Underline follows scroll progress, not click state */}
            <motion.span
              aria-hidden
              style={{ x: underlineX, width: underlineW }}
              className="absolute bottom-0 left-0 h-px bg-[var(--tt-brand)]"
            />
          </div>
          {/* Thin progress line under the rail */}
          <div className="relative mx-auto mt-3 h-px w-full max-w-[560px] overflow-hidden bg-[var(--tt-border)]">
            <motion.div
              aria-hidden
              style={{ scaleX: scrollYProgress }}
              className="absolute inset-0 origin-left bg-[var(--tt-brand)]"
            />
          </div>
        </div>

        {/* Fixed-height stage; every panel is absolutely positioned in the
            same cell, so nothing ever reflows. */}
        <div className="relative min-h-0 flex-1">
          {FEATURES.map((f, i) => (
            <ScrubPanel
              key={f.id}
              feature={f}
              index={i}
              progress={scrollYProgress}
              active={activeIdx === i}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function ScrubPanel({
  feature,
  index,
  progress,
  active,
}: {
  feature: Feature;
  index: number;
  progress: MotionValue<number>;
  active: boolean;
}) {
  const start = index * SEG;
  const end = start + SEG;
  // Incoming fades in just before its slice starts; outgoing fades out just
  // after its slice ends — neighbors overlap, so there is never a blank frame.
  // Scroll-timeline offsets must be strictly increasing within [0, 1], so the
  // edge panels clamp their outer keys and pin the clamped side to the
  // visible state: panel 0 starts visible, the last panel stays visible.
  const first = index === 0;
  const last = start + SEG >= 1 - BAND / 2;
  const keys = [
    first ? 0 : start - BAND,
    first ? BAND : start,
    last ? 1 - BAND : end,
    last ? 1 : end + BAND,
  ];
  const opacity = useTransform(progress, keys, [first ? 1 : 0, 1, 1, last ? 1 : 0]);
  const y = useTransform(progress, keys, [first ? 0 : 12, 0, 0, last ? 0 : -12]);
  const scale = useTransform(progress, keys, [first ? 1 : 1.03, 1, 1, last ? 1 : 0.97]);

  const words = feature.headline.split(" ");
  const dims = SHOT_DIMS[feature.id] ?? { w: 3200, h: 2000 };

  return (
    <motion.div
      role="tabpanel"
      id={`feature-panel-${feature.id}`}
      aria-labelledby={`feature-tab-${feature.id}`}
      aria-hidden={!active}
      style={{ opacity, y, scale, pointerEvents: active ? "auto" : "none" }}
      // No resident will-change: six promoted layers of full-bleed screenshots
      // cost real memory; the scroll-linked transform composites fine without.
      className="absolute inset-0 grid grid-cols-[minmax(280px,2fr)_3fr] gap-6 lg:gap-10"
    >
      {/* Caption column */}
      <div className="flex min-h-0 flex-col justify-center gap-5">
        <h3
          aria-label={feature.headline}
          className="text-[clamp(19px,2.3vw,29px)] leading-[1.18] tracking-[-0.02em] font-semibold text-[var(--tt-fg)]"
        >
          <span aria-hidden>
            {words.map((w, j) => (
              <motion.span
                key={j}
                className="inline-block"
                initial={false}
                animate={active ? { opacity: 1, y: 0 } : { opacity: 0, y: 8 }}
                transition={{ duration: 0.3, ease: EASE, delay: active ? 0.04 * j : 0 }}
              >
                {w}
                {j < words.length - 1 ? " " : ""}
              </motion.span>
            ))}{" "}
          </span>
        </h3>
        <ul className="flex min-h-0 flex-col gap-2.5 overflow-y-auto pr-1">
          {feature.bullets.map((b, j) => (
            <motion.li
              key={j}
              initial={false}
              animate={active ? { opacity: 1, y: 0 } : { opacity: 0, y: 10 }}
              transition={{
                duration: 0.25,
                ease: EASE,
                delay: active ? 0.16 + 0.05 * j : 0,
              }}
              className="flex gap-2.5 text-[12.5px] leading-relaxed text-[var(--tt-fg-muted)]"
            >
              <span className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded border border-[color:var(--tt-brand)]/25 bg-[color:var(--tt-brand-glow)]">
                <Check size={9} className="text-[var(--tt-brand)]" strokeWidth={3} />
              </span>
              <span>{b}</span>
            </motion.li>
          ))}
        </ul>
      </div>

      {/* Screenshot column — fixed crop window, identical for every panel */}
      <div className="relative min-h-0">
        <div
          aria-hidden
          className="pointer-events-none absolute -inset-6 bg-gradient-to-tr from-[color:var(--tt-brand-glow)] via-transparent to-emerald-500/5 blur-3xl"
        />
        <BrowserFrame
          label={`tokentelemetry · ${feature.label.toLowerCase()}`}
          className="h-full flex flex-col"
        >
          <div className="relative min-h-0 flex-1">
            {/* All panels lazy: the stage is far below the fold, and the
                browser fetches every panel once the section nears the
                viewport anyway (the stacked frames all occupy layout). */}
            <picture>
              <source
                type="image/webp"
                srcSet={webpSrcSet(feature.screenshot)}
                sizes="(min-width: 768px) 56vw, calc(100vw - 40px)"
              />
              <img
                src={feature.screenshot}
                alt={feature.label}
                width={dims.w}
                height={dims.h}
                className="absolute inset-0 h-full w-full object-cover object-top"
                loading="lazy"
                decoding="async"
              />
            </picture>
          </div>
        </BrowserFrame>
      </div>
    </motion.div>
  );
}

/* ------------------------------------------------------------------ */
/* Fallback: plain vertical stack (mobile / prefers-reduced-motion)    */
/* ------------------------------------------------------------------ */

function StaticStack() {
  return (
    <div className="flex flex-col gap-14 sm:gap-20">
      {FEATURES.map((f) => {
        const dims = SHOT_DIMS[f.id] ?? { w: 3200, h: 2000 };
        return (
          <div key={f.id}>
            <p className="mb-3 font-mono text-[11px] uppercase tracking-[0.16em] text-[var(--tt-fg-dim)]">
              {f.label}
            </p>
            <h3 className="mb-5 max-w-3xl text-[20px] sm:text-[26px] leading-[1.2] tracking-[-0.02em] font-semibold text-[var(--tt-fg)]">
              {f.headline}
            </h3>
            <BrowserFrame label={`tokentelemetry · ${f.label.toLowerCase()}`} className="mb-5">
              <picture>
                <source
                  type="image/webp"
                  srcSet={webpSrcSet(f.screenshot)}
                  sizes="(min-width: 1384px) 1256px, calc(100vw - 40px)"
                />
                <img
                  src={f.screenshot}
                  alt={f.label}
                  width={dims.w}
                  height={dims.h}
                  className="block h-auto w-full"
                  loading="lazy"
                  decoding="async"
                />
              </picture>
            </BrowserFrame>
            <div className="grid gap-3 md:grid-cols-3">
              {f.bullets.map((b, i) => (
                <div
                  key={i}
                  className="flex gap-3 rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] p-4"
                >
                  <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-md border border-[color:var(--tt-brand)]/25 bg-[color:var(--tt-brand-glow)]">
                    <Check size={11} className="text-[var(--tt-brand)]" strokeWidth={3} />
                  </span>
                  <p className="text-[13.5px] leading-relaxed text-[var(--tt-fg-muted)]">{b}</p>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
