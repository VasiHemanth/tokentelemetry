import { RootProvider } from "fumadocs-ui/provider/next";
import { DocsLayout } from "fumadocs-ui/layouts/docs";
import type { ReactNode } from "react";
import { source } from "@/lib/source";

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <RootProvider
      // The marketing site is dark-only (`<html class="dark">` is hardcoded and
      // only dark `--tt-*` tokens exist). Disable Fumadocs' next-themes
      // integration so it never strips `.dark` or renders a light-mode toggle
      // that would land on an unstyled (broken) light theme.
      theme={{ enabled: false }}
      search={{
        // Static search: reads /api/search (generated at build time).
        // type:'static' is deprecated upstream but functional — it wires
        // the default dialog to oramaStaticClient, which loads an Orama
        // snapshot from the URL below. No server route needed.
        // options are spread into DefaultSearchDialog props
        options: { type: "static" as const, api: "/api/search" },
      }}
    >
      <DocsLayout
        tree={source.pageTree}
        nav={{
          title: "TokenTelemetry Docs",
          url: "/docs",
        }}
        // Dark-only site: hide the light/dark toggle in the sidebar footer.
        themeSwitch={{ enabled: false }}
        // Keep the sidebar always open. The collapse trigger lives *inside* the
        // sidebar; once collapsed, the only reopen control ("Open Sidebar") is
        // in the desktop-hidden mobile navbar, so users get stuck with no menu.
        // Disabling collapse removes that dead-end entirely.
        sidebar={{ collapsible: false }}
      >
        {children}
      </DocsLayout>
    </RootProvider>
  );
}
