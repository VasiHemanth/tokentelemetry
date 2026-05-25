"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Script from "next/script";

const GA_ID = process.env.NEXT_PUBLIC_GA_ID;
const CLARITY_ID = process.env.NEXT_PUBLIC_CLARITY_ID;

const STORAGE_KEY = "tt-consent";
type Consent = "granted" | "denied";

function isLocalHost() {
  if (typeof window === "undefined") return false;
  const h = window.location.hostname;
  return h === "localhost" || h === "127.0.0.1" || h === "0.0.0.0";
}

/**
 * Cookie consent banner + consent-gated analytics.
 *
 * GA4 and Microsoft Clarity are non-essential, cookie-using analytics, so we
 * never load them until the visitor explicitly accepts. The choice is stored
 * in localStorage so the banner only shows once. Analytics are also skipped on
 * localhost so local dev sessions don't pollute the data.
 */
export default function Analytics() {
  // null = not yet read / no choice made (banner hidden until we know, to
  // avoid an SSR/client flash). Set after mount from localStorage.
  const [consent, setConsent] = useState<Consent | null>(null);
  const [decided, setDecided] = useState(true); // true until we learn otherwise
  const [local, setLocal] = useState(false);

  useEffect(() => {
    setLocal(isLocalHost());
    const stored = window.localStorage.getItem(STORAGE_KEY) as Consent | null;
    if (stored === "granted" || stored === "denied") {
      setConsent(stored);
    } else {
      setDecided(false); // show the banner
    }
  }, []);

  function choose(value: Consent) {
    window.localStorage.setItem(STORAGE_KEY, value);
    setConsent(value);
    setDecided(true);
  }

  // Banner reflects consent everywhere (so it's previewable in dev), but the
  // real analytics scripts never fire on localhost regardless of the choice.
  const analyticsEnabled = consent === "granted" && !local;

  return (
    <>
      {analyticsEnabled && GA_ID && (
        <>
          <Script
            id="ga4-loader"
            strategy="afterInteractive"
            src={`https://www.googletagmanager.com/gtag/js?id=${GA_ID}`}
          />
          <Script id="ga4-init" strategy="afterInteractive">
            {`
              window.dataLayer = window.dataLayer || [];
              function gtag(){dataLayer.push(arguments);}
              gtag('js', new Date());
              gtag('config', '${GA_ID}', { anonymize_ip: true });
            `}
          </Script>
        </>
      )}

      {analyticsEnabled && CLARITY_ID && (
        <Script id="ms-clarity" strategy="afterInteractive">
          {`
            (function(c,l,a,r,i,t,y){
              c[a]=c[a]||function(){(c[a].q=c[a].q||[]).push(arguments)};
              t=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;
              y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y);
            })(window, document, "clarity", "script", "${CLARITY_ID}");
          `}
        </Script>
      )}

      {!decided && (
        <div
          role="dialog"
          aria-live="polite"
          aria-label="Cookie consent"
          className="fixed inset-x-0 bottom-0 z-50 px-4 pb-4 sm:px-6 sm:pb-6"
        >
          <div className="mx-auto max-w-[640px] rounded-[var(--tt-radius-lg)] border border-[var(--tt-border-strong)] bg-[var(--tt-panel)] shadow-[0_20px_60px_-20px_rgba(0,0,0,0.8)] backdrop-blur p-4 sm:p-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between sm:gap-5">
              <p className="text-[13px] leading-relaxed text-[var(--tt-fg-muted)]">
                We use cookies for anonymous analytics (Google Analytics &amp;
                Microsoft Clarity) to understand how the site is used. No
                accounts, no ads.{" "}
                <Link
                  href="/privacy"
                  className="text-[var(--tt-fg)] underline underline-offset-2 hover:text-[var(--tt-brand)] transition-colors"
                >
                  Privacy policy
                </Link>
                .
              </p>
              <div className="flex shrink-0 items-center gap-2">
                <button
                  type="button"
                  onClick={() => choose("denied")}
                  className="h-9 px-3.5 rounded-[var(--tt-radius)] border border-[var(--tt-border-strong)] text-[var(--tt-fg-muted)] text-[12.5px] font-medium hover:text-[var(--tt-fg)] hover:tt-tint-1 transition-colors"
                >
                  Decline
                </button>
                <button
                  type="button"
                  onClick={() => choose("granted")}
                  className="h-9 px-4 rounded-[var(--tt-radius)] bg-[var(--tt-brand)] text-[#04060a] text-[12.5px] font-semibold hover:bg-[var(--tt-brand-strong)] transition-colors"
                >
                  Accept
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
