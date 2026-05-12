import type { Metadata } from "next";
import Script from "next/script";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { FAQ_ITEMS } from "@/components/FAQ";
import SiteHeader from "@/components/SiteHeader";

const GA_ID = process.env.NEXT_PUBLIC_GA_ID;

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

const SITE_URL = "https://tokentelemetry.com";
const TITLE = "Token Telemetry (TokenTelemetry) — See exactly what your coding agents cost, think, and do";
const DESCRIPTION =
  "Token Telemetry (TokenTelemetry) is local, read-only observability for Claude Code, Codex, Gemini CLI, Cursor, Copilot, and 4 more coding agents. Tokens, traces, cost — one command, no signup, 100% on your machine.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: TITLE,
  description: DESCRIPTION,
  applicationName: "TokenTelemetry",
  keywords: [
    "Token Telemetry",
    "TokenTelemetry",
    "tokentelemetry",
    "tokentelemetry.com",
    "token telementry",
    "tokentelementry",
    "token telemtry",
    "AI agent observability",
    "Claude Code dashboard",
    "Codex token tracking",
    "Gemini CLI cost",
    "local AI observability",
    "coding agent monitoring",
    "LLM token cost tracker",
    "Cursor logs",
    "open source agent telemetry",
  ],
  authors: [{ name: "Hemanth Vasi", url: "https://www.linkedin.com/in/vasi-hemanth/" }],
  creator: "Hemanth Vasi",
  alternates: { canonical: SITE_URL },
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "any" },
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/apple-icon.png", sizes: "180x180", type: "image/png" }],
    shortcut: ["/favicon.ico"],
  },
  manifest: "/manifest.webmanifest",
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    url: SITE_URL,
    siteName: "TokenTelemetry",
    type: "website",
    locale: "en_US",
    images: [{ url: "/og.png", width: 1200, height: 630, alt: "TokenTelemetry" }],
  },
  twitter: {
    card: "summary_large_image",
    title: TITLE,
    description: DESCRIPTION,
    creator: "@VasiHemanth",
    images: ["/og.png"],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true, "max-image-preview": "large", "max-snippet": -1 },
  },
  verification: {
    google: process.env.GOOGLE_VERIFICATION,
    other: process.env.BING_VERIFICATION
      ? { "msvalidate.01": process.env.BING_VERIFICATION }
      : undefined,
  },
};

const JSON_LD = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "Token Telemetry",
  alternateName: ["TokenTelemetry", "tokentelemetry", "Token-Telemetry"],
  url: SITE_URL,
  sameAs: [
    "https://github.com/VasiHemanth/tokentelemetry",
    "https://www.linkedin.com/in/vasi-hemanth/",
  ],
  description: DESCRIPTION,
  applicationCategory: "DeveloperApplication",
  operatingSystem: "macOS, Linux, Windows",
  offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
  license: "https://opensource.org/licenses/MIT",
  author: { "@type": "Person", name: "Hemanth Vasi", url: "https://www.linkedin.com/in/vasi-hemanth/" },
  codeRepository: "https://github.com/VasiHemanth/tokentelemetry",
};

const ORG_LD = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "Token Telemetry",
  alternateName: ["TokenTelemetry", "tokentelemetry"],
  url: SITE_URL,
  logo: `${SITE_URL}/og.png`,
  sameAs: [
    "https://github.com/VasiHemanth/tokentelemetry",
    "https://www.linkedin.com/in/vasi-hemanth/",
  ],
};

const FAQ_LD = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: FAQ_ITEMS.map(({ q, a }) => ({
    "@type": "Question",
    name: q,
    acceptedAnswer: { "@type": "Answer", text: a },
  })),
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} dark`} suppressHydrationWarning>
      <body className="relative min-h-screen overflow-x-hidden">
        {/* Single source of background atmosphere */}
        <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 tt-canvas-glow" />
        <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 tt-grid opacity-30" />
        <SiteHeader />
        {children}
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(JSON_LD) }} />
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(ORG_LD) }} />
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(FAQ_LD) }} />
        {GA_ID && (
          <>
            <Script
              id="ga4-loader"
              strategy="afterInteractive"
              src={`https://www.googletagmanager.com/gtag/js?id=${GA_ID}`}
            />
            <Script id="ga4-init" strategy="afterInteractive">
              {`
                const host = location.hostname;
                if (host !== 'localhost' && host !== '127.0.0.1' && host !== '0.0.0.0') {
                  window.dataLayer = window.dataLayer || [];
                  function gtag(){dataLayer.push(arguments);}
                  gtag('js', new Date());
                  gtag('config', '${GA_ID}', { anonymize_ip: true });
                }
              `}
            </Script>
          </>
        )}
      </body>
    </html>
  );
}
