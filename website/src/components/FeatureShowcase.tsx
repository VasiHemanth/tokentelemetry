"use client";
import { useRef, useState } from "react";
import { motion, AnimatePresence, useInView, useReducedMotion } from "motion/react";
import { FEATURES } from "@/data/features";
import { Check } from "lucide-react";
import BrowserFrame from "./BrowserFrame";
import { Reveal, EASE, SPRING } from "@/components/motion";

export default function FeatureShowcase() {
  const [active, setActive] = useState(FEATURES[0].id);
  const feature = FEATURES.find((f) => f.id === active)!;
  const reduced = useReducedMotion();

  // One-time section reveal: the panel (screenshot frame + glow) rises once on
  // first in-view; tab swaps after that are handled by AnimatePresence alone.
  const panelRef = useRef<HTMLDivElement>(null);
  const panelInView = useInView(panelRef, { once: true, amount: 0.2 });

  // Bullet cards stagger 80ms per tab change (the keyed panel remounts them).
  const bulletList = {
    hidden: {},
    show: { transition: { staggerChildren: reduced ? 0 : 0.08 } },
  };
  const bulletItem = reduced
    ? {
        hidden: { opacity: 0 },
        show: { opacity: 1, transition: { duration: 0.15 } },
      }
    : {
        hidden: { opacity: 0, y: 12 },
        show: { opacity: 1, y: 0, transition: { duration: 0.25, ease: EASE } },
      };

  return (
    <section id="features" className="max-w-[1320px] mx-auto px-5 sm:px-8 py-16 sm:py-24">
      <Reveal y={16} className="text-center mb-8 sm:mb-10">
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--tt-fg-dim)] mb-3">
          What you&apos;ll see
        </p>
        <h2 className="text-[28px] sm:text-[44px] leading-[1.1] tracking-[-0.02em] font-semibold text-[var(--tt-fg)] max-w-2xl mx-auto">
          One dashboard. <span className="text-[var(--tt-brand)]">Every agent.</span>
        </h2>
      </Reveal>

      {/* Tabs — horizontally scrollable on mobile, wraps on larger screens */}
      <div className="-mx-5 sm:mx-auto mb-8 sm:mb-10 sm:w-fit overflow-x-auto sm:overflow-visible">
        <div className="flex sm:flex-wrap items-center sm:justify-center gap-1 px-5 sm:px-1 py-1 mx-auto sm:rounded-[var(--tt-radius-lg)] sm:border sm:border-[var(--tt-border)] sm:bg-[var(--tt-panel)] w-max sm:w-auto">
        {FEATURES.map((f) => (
          <button
            key={f.id}
            onClick={() => setActive(f.id)}
            className={`relative h-9 px-4 rounded-[var(--tt-radius)] text-[12.5px] font-medium tracking-tight transition-colors whitespace-nowrap ${
              active === f.id
                ? "tt-tint-2 text-[var(--tt-fg)]"
                : "text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)]"
            }`}
          >
            {f.label}
            {active === f.id &&
              (reduced ? (
                <span aria-hidden className="absolute inset-x-3 -bottom-px h-px bg-[var(--tt-brand)]" />
              ) : (
                <motion.span
                  aria-hidden
                  layoutId="feature-tab"
                  transition={SPRING.tab}
                  className="absolute inset-x-3 -bottom-px h-px bg-[var(--tt-brand)]"
                />
              ))}
          </button>
        ))}
        </div>
      </div>

      <motion.div
        ref={panelRef}
        initial={false}
        animate={
          panelInView
            ? { opacity: 1, y: 0 }
            : { opacity: 0, y: reduced ? 0 : 24 }
        }
        transition={reduced ? { duration: 0.15 } : SPRING.reveal}
      >
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={feature.id}
            initial={reduced ? { opacity: 0 } : { opacity: 0, y: 12, scale: 0.995 }}
            animate={
              reduced
                ? { opacity: 1, transition: { duration: 0.15 } }
                : { opacity: 1, y: 0, scale: 1, transition: { duration: 0.3, ease: EASE } }
            }
            exit={
              reduced
                ? { opacity: 0, transition: { duration: 0.15 } }
                : { opacity: 0, y: -8, transition: { duration: 0.18, ease: EASE } }
            }
          >
            <h3 className="text-center text-[20px] sm:text-[32px] leading-[1.2] tracking-[-0.02em] font-semibold text-[var(--tt-fg)] max-w-3xl mx-auto mb-8 sm:mb-10">
              {feature.headline}
            </h3>

            {/* Screenshot */}
            <div className="relative mb-8 sm:mb-10">
              {/* Glow fades in over 650ms on first in-view only; instant on tab remounts */}
              <motion.div
                aria-hidden
                initial={false}
                animate={{ opacity: panelInView ? 1 : 0 }}
                transition={{ duration: reduced ? 0.15 : 0.65, ease: EASE }}
                className="absolute -inset-x-6 -inset-y-6 pointer-events-none bg-gradient-to-tr from-[color:var(--tt-brand-glow)] via-transparent to-emerald-500/5 blur-3xl"
              />
              <BrowserFrame label={`tokentelemetry · ${feature.label.toLowerCase()}`}>
                <img
                  src={feature.screenshot}
                  alt={feature.label}
                  className="block w-full h-auto"
                  loading="lazy"
                  decoding="async"
                />
              </BrowserFrame>
            </div>

            {/* Bullets */}
            <motion.div
              variants={bulletList}
              initial="hidden"
              animate="show"
              className="grid md:grid-cols-3 gap-3"
            >
              {feature.bullets.map((b, i) => (
                <motion.div
                  key={i}
                  variants={bulletItem}
                  className="flex gap-3 p-4 rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] hover:border-[var(--tt-border-strong)] transition-colors"
                >
                  <span className="mt-0.5 h-5 w-5 rounded-md bg-[color:var(--tt-brand-glow)] border border-[color:var(--tt-brand)]/25 grid place-items-center shrink-0">
                    <Check size={11} className="text-[var(--tt-brand)]" strokeWidth={3} />
                  </span>
                  <p className="text-[13.5px] text-[var(--tt-fg-muted)] leading-relaxed">{b}</p>
                </motion.div>
              ))}
            </motion.div>
          </motion.div>
        </AnimatePresence>
      </motion.div>
    </section>
  );
}
