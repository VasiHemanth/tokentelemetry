import BrowserFrame from "./BrowserFrame";
import { webpSrcSet } from "@/lib/shots";

/**
 * The product, shown above the fold. The CRO audit found the hero carried no
 * real product pixel on mobile (~74% of traffic) — the old animated terminal
 * was `hidden lg:block`. This puts the actual dashboard screenshot in front of
 * every visitor, immediately.
 *
 * The image is cropped from the top (object-top) inside a fixed aspect ratio so
 * it (a) shows the high-signal metrics row rather than empty chrome, and (b)
 * reserves its own height — no layout shift as it loads (helps the poor CLS the
 * audit flagged). To upgrade to a short looping clip later, drop a
 * `<video poster="/screenshots/dashboard.png" muted playsInline …>` in place of
 * the <img>; the frame and aspect box already fit it.
 */
export default function HeroShot() {
  return (
    <div className="relative">
      <div
        aria-hidden
        className="absolute -inset-x-6 -top-8 -bottom-8 pointer-events-none bg-gradient-to-tr from-[color:var(--tt-brand-glow)] via-transparent to-transparent blur-3xl"
      />
      <BrowserFrame label="tokentelemetry · dashboard" className="relative">
        <div className="aspect-[16/11] sm:aspect-[16/12] overflow-hidden bg-[var(--tt-sunken)]">
          <picture>
            <source
              type="image/webp"
              srcSet={webpSrcSet("/screenshots/dashboard.png")}
              sizes="(min-width: 1060px) 1000px, calc(100vw - 40px)"
            />
            <img
              src="/screenshots/dashboard.png"
              alt="TokenTelemetry dashboard — live traces, token burn, and cost across every agent"
              width={3200}
              height={3000}
              className="block w-full h-auto object-cover object-top"
              // First meaningful visual; load it eagerly so it wins LCP.
              loading="eager"
              decoding="async"
              fetchPriority="high"
            />
          </picture>
        </div>
      </BrowserFrame>
    </div>
  );
}
