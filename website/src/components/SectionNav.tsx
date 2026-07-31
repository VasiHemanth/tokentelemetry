"use client";
/**
 * SectionNav — fixed left-edge rail (xl+ only) mirroring the numbered
 * section chrome. The active section's dot fills with --tt-brand and its
 * mono label slides in; clicks are plain hash anchors (smooth scrolling
 * comes from `html { scroll-behavior: smooth }` in globals.css, which
 * reduced motion turns off). Active state flips when a section crosses a
 * narrow band around the viewport midpoint (IntersectionObserver).
 */
import { useEffect, useState } from "react";
import { track } from "@/lib/track";

const SECTIONS = [
  { id: "observe", n: "00", label: "observe" },
  { id: "scan", n: "01", label: "scan" },
  { id: "burn", n: "02", label: "burn" },
  { id: "trace", n: "03", label: "trace" },
  { id: "setup", n: "04", label: "setup" },
  { id: "features", n: "05", label: "see" },
  { id: "agents", n: "06", label: "coverage" },
  { id: "hermes", n: "07", label: "hermes" },
  { id: "zero", n: "08", label: "zero" },
  { id: "faq", n: "09", label: "faq" },
] as const;

export default function SectionNav() {
  const [active, setActive] = useState<string>(SECTIONS[0].id);

  useEffect(() => {
    const els = SECTIONS.map((s) => document.getElementById(s.id)).filter(
      (el): el is HTMLElement => el !== null,
    );
    if (els.length === 0) return;
    // A 10%-tall band around the viewport midpoint: whichever section
    // enters it becomes active. Sections are all taller than the band, so
    // at most two can intersect during a transition.
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) setActive(e.target.id);
        }
      },
      { rootMargin: "-45% 0px -45% 0px", threshold: 0 },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);

  return (
    <nav
      aria-label="Page sections"
      className="hidden xl:block fixed left-4 top-1/2 -translate-y-1/2 z-40"
    >
      <ul className="flex flex-col gap-2.5">
        {SECTIONS.map((s) => {
          const on = active === s.id;
          return (
            <li key={s.id}>
              <a
                href={`#${s.id}`}
                aria-current={on ? "true" : undefined}
                onClick={() => track("click_nav", { to: s.id, location: "rail" })}
                className="group flex items-center gap-2.5 py-0.5"
              >
                <span
                  aria-hidden
                  className={`w-1.5 h-1.5 rounded-full border shrink-0 transition-colors duration-200 motion-reduce:transition-none ${
                    on
                      ? "bg-[var(--tt-brand)] border-[var(--tt-brand)]"
                      : "bg-transparent border-[var(--tt-fg-faint)] group-hover:border-[var(--tt-fg-dim)]"
                  }`}
                />
                <span
                  className={`font-mono text-[10.5px] tracking-[0.14em] uppercase whitespace-nowrap rounded px-1.5 py-0.5 bg-[color-mix(in_srgb,var(--tt-bg)_86%,transparent)] backdrop-blur-sm transition-[opacity,transform,color] duration-200 ease-[var(--tt-ease)] motion-reduce:transition-none motion-reduce:transform-none ${
                    on
                      ? "opacity-100 translate-x-0 text-[var(--tt-fg)]"
                      : "opacity-0 -translate-x-1.5 text-[var(--tt-fg-dim)] group-hover:opacity-80 group-hover:translate-x-0 group-focus-visible:opacity-80 group-focus-visible:translate-x-0"
                  }`}
                >
                  {s.n} {s.label}
                </span>
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
