"use client";

import { List } from "lucide-react";
import { Suspense } from "react";
import { PageHeader } from "@/components/ui";
import HermesIcon from "@/components/icons/HermesIcon";
import HermesSessionExplorer from "@/components/hermes/HermesSessionExplorer";

export default function HermesSessionsPage() {
  return (
    <div className="px-8 py-8 max-w-[1600px] mx-auto space-y-8 pb-20">
      <PageHeader
        backHref="/hermes"
        eyebrow="Hermes Agent"
        title="Session explorer"
        description="Search, filter, and inspect Hermes sessions without rendering the entire history at once."
        icon={<HermesIcon size={20} />}
        actions={<div className="flex items-center gap-2 text-[11px] text-[var(--tt-fg-dim)]"><List size={14} /> Newest first by default</div>}
      />
      <Suspense fallback={<div className="h-96 rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] animate-pulse" aria-label="Loading session explorer" />}>
        <HermesSessionExplorer />
      </Suspense>
    </div>
  );
}
