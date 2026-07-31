"use client";

import { useState } from "react";
import { Play } from "lucide-react";
import BrowserFrame from "./BrowserFrame";
import { track } from "@/lib/track";

const VIDEO_ID = "AXGdSFFNS_w";
const VIDEO_TITLE = "TokenTelemetry demo";

/**
 * Landing-page demo video. Click-to-load facade: the poster image is plain
 * markup until the visitor clicks play, then the (autoplaying) iframe swaps in.
 * That keeps the YouTube player — several hundred KB of JS — off every page
 * load, and gives us a real play event to track, which a cross-origin iframe
 * would never surface.
 *
 * The docs site has its own embed (`components/docs/VideoEmbed.tsx`) with the
 * same facade approach but MDX-prose styling and a `doc_video_play` event. This
 * one uses the landing page's BrowserFrame chrome and fires `landing_video_play`
 * so the two surfaces stay separable in GA.
 */
export default function DemoVideo() {
  const [playing, setPlaying] = useState(false);

  return (
    <section id="demo" className="relative max-w-[1180px] mx-auto px-5 py-12 sm:py-[72px]">
      <div className="text-center max-w-[680px] mx-auto mb-8 sm:mb-10">
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--tt-fg-dim)] mb-3">
          A look at the product
        </p>
        <h2 className="text-[clamp(26px,3.6vw,42px)] leading-[1.08] tracking-[-0.025em] font-semibold text-[var(--tt-fg)]">
          TokenTelemetry, <span className="text-[var(--tt-brand)]">on video.</span>
        </h2>
      </div>

      <div className="relative max-w-[900px] mx-auto">
        <div
          aria-hidden
          className="absolute -inset-x-6 -inset-y-6 pointer-events-none bg-gradient-to-tr from-[color:var(--tt-brand-glow)] via-transparent to-transparent blur-3xl"
        />
        <BrowserFrame label="tokentelemetry · demo" className="relative">
          {/* Fixed 16:9 box reserves the height in both states, so swapping the
              poster for the iframe costs no layout shift. */}
          <div className="relative aspect-video bg-black">
            {playing ? (
              <iframe
                src={`https://www.youtube-nocookie.com/embed/${VIDEO_ID}?autoplay=1`}
                title={VIDEO_TITLE}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
                className="absolute inset-0 w-full h-full border-0"
              />
            ) : (
              <button
                type="button"
                aria-label={`Play: ${VIDEO_TITLE}`}
                onClick={() => {
                  track("landing_video_play", { id: VIDEO_ID, location: "landing" });
                  setPlaying(true);
                }}
                className="group absolute inset-0 w-full h-full cursor-pointer"
              >
                <img
                  src={`https://i.ytimg.com/vi/${VIDEO_ID}/maxresdefault.jpg`}
                  alt=""
                  width={1280}
                  height={720}
                  loading="lazy"
                  decoding="async"
                  className="block w-full h-full object-cover"
                />
                <span
                  aria-hidden
                  className="absolute inset-0 grid place-items-center bg-black/25 group-hover:bg-black/15 transition-colors"
                >
                  <span className="grid place-items-center w-[58px] h-[58px] rounded-full bg-[var(--tt-brand)] text-black shadow-[0_10px_40px_-8px_rgba(0,0,0,0.7)] group-hover:scale-105 transition-transform">
                    <Play size={22} fill="currentColor" className="translate-x-[2px]" />
                  </span>
                </span>
              </button>
            )}
          </div>
        </BrowserFrame>
      </div>
    </section>
  );
}
