import type { Metadata } from "next";
import RedirectNotice from "./RedirectNotice";

/** Where the docs link actually sends people. Referral link, disclosed below. */
const TARGET = "https://www.orcarouter.ai/ref/ref_cdcd52dcf72dbbc6f881";

export const metadata: Metadata = {
  title: "Opening OrcaRouter",
  description: "Leaving the TokenTelemetry docs for OrcaRouter.",
  // A hop page has no content worth indexing, and letting it rank would put a
  // referral link in search results ahead of the documentation explaining it.
  robots: { index: false, follow: false },
};

/**
 * Counted hop to the OrcaRouter referral link.
 *
 * A plain 302 would be simpler but invisible to us: the Cloudflare Web Analytics
 * beacon is a client-side script, so a response that serves no HTML fires no
 * beacon and counts no pageview. Rendering a real page (which inherits the
 * beacon from the root layout) and then navigating from the client is what makes
 * the click countable at all.
 *
 * The count is a floor, not a total. Analytics here are consent-gated, so anyone
 * who declined the banner passes through uncounted. OrcaRouter's own partner
 * dashboard is the authoritative number; this only measures intent on our side.
 */
export default function OrcaRouterHop() {
  return <RedirectNotice target={TARGET} />;
}
