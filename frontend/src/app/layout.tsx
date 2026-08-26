import type { Metadata } from "next";
import Script from "next/script";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import LayoutWrapper from "../components/LayoutWrapper";
import { ThemeProvider, NO_FLASH_SCRIPT } from "../components/ThemeProvider";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "TokenTelemetry",
  description: "Local token + cost monitoring for Claude Code, Codex, Gemini CLI, and other coding agents.",
};

// This must be dynamic: TT_SINGLE_PORT_PROXY is a launch-time server setting,
// not a NEXT_PUBLIC_* build setting.
export const dynamic = "force-dynamic";

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        {/* Sets data-theme before paint to avoid FOUC. beforeInteractive runs in <head>. */}
        <Script id="tt-theme-init" strategy="beforeInteractive">
          {NO_FLASH_SCRIPT}
        </Script>
        <Script id="tt-runtime-config" strategy="beforeInteractive">
          {`window.__TT_SINGLE_PORT_PROXY__ = ${process.env.TT_SINGLE_PORT_PROXY === "1"};`}
        </Script>
      </head>
      <ThemeProvider>
        <LayoutWrapper>{children}</LayoutWrapper>
      </ThemeProvider>
    </html>
  );
}
