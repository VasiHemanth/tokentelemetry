import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { FAQ_ITEMS } from "@/components/faq-items";
import SiteHeader from "@/components/SiteHeader";
import Analytics from "@/components/Analytics";
import PageViewTracker from "@/components/PageViewTracker";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

const SITE_URL = "https://tokentelemetry.com";
const TITLE = "Token Telemetry — Observability for coding & autonomous agents (Hermes, Claude Code, Codex …)";
const DESCRIPTION =
  "Token Telemetry is local, read-only observability for 11 coding agents (Claude Code, Codex, Gemini CLI, Cursor, Copilot, Qwen, OpenCode, Vibe, Antigravity, Grok Build, Pi) plus Hermes Agent (Nous Research) — with a dedicated dashboard for gateway health, cron jobs, skills, memory, and 38 source platforms. One command, 100% on your machine.";

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
    // Image is served by app/opengraph-image.tsx (dynamic, includes the
    // "NEW · Hermes Agent" chip and the AI-agents headline).
  },
  twitter: {
    card: "summary_large_image",
    title: TITLE,
    description: DESCRIPTION,
    creator: "@VasiHemanth",
    // Twitter image is served by app/twitter-image.tsx if present, else
    // falls back to the same opengraph-image.tsx.
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
      <body className="relative min-h-screen [overflow-x:clip]">
        {/* Single source of background atmosphere */}
        <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 tt-canvas-glow" />
        <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 tt-grid opacity-30" />
        <SiteHeader />
        {children}
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(JSON_LD) }} />
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(ORG_LD) }} />
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(FAQ_LD) }} />
        <Analytics />
        <PageViewTracker />
      </body>
    </html>
  );
}
