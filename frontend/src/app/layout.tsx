import type { Metadata } from "next";
import Script from "next/script";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import LayoutWrapper from "../components/LayoutWrapper";
import { ThemeProvider, NO_FLASH_SCRIPT } from "../components/ThemeProvider";
import { KeyboardShortcutsProvider } from "../components/settings/KeyboardShortcutsProvider";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "TokenTelemetry",
  description: "Local token + cost monitoring for Claude Code, Codex, Gemini CLI, and other coding agents.",
};

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
      </head>
      <ThemeProvider>
        <KeyboardShortcutsProvider />
        <LayoutWrapper>{children}</LayoutWrapper>
      </ThemeProvider>
    </html>
  );
}
