"use client";

import { Brain, Loader2, RefreshCw, TriangleAlert, Unplug } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { apiFetch, useResource } from "@/lib/api";
import { Badge, Card, EmptyState, Skeleton } from "@/components/ui";

import { useProject } from "../_lib/project-context";
import BrainGraph from "./_components/BrainGraph";
import Onboarding from "./_components/Onboarding";
import PageDrawer from "./_components/PageDrawer";
import type { BrainGraphData } from "./_components/types";

const KIND_LABEL: Record<string, string> = {
  plugin_wiki: "plugin wiki",
  okf_ish: "OKF wiki",
  obsidian_vault: "Obsidian vault",
  markdown_wiki: "markdown wiki",
};

function useDarkTheme() {
  const [dark, setDark] = useState(true);
  useEffect(() => {
    const el = document.documentElement;
    const read = () => setDark(el.getAttribute("data-theme") !== "light");
    read();
    const obs = new MutationObserver(read);
    obs.observe(el, { attributes: true, attributeFilter: ["data-theme"] });
    return () => obs.disconnect();
  }, []);
  return dark;
}

export default function BrainTab() {
  const { decodedPath } = useProject();
  const dark = useDarkTheme();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [drawerId, setDrawerId] = useState<string | null>(null);

  const q = `project=${encodeURIComponent(decodedPath)}`;
  const { data, loading, refetch } = useResource<BrainGraphData>(
    decodedPath ? `/brain/graph?${q}` : null,
    { initial: undefined },
  );

  const onSelect = useCallback((id: string | null) => {
    setSelectedId(id);
    setDrawerId(id);
  }, []);

  const onNavigate = useCallback((id: string) => {
    setSelectedId(id);
    setDrawerId(id);
  }, []);

  const unregister = useCallback(async () => {
    await apiFetch("/brain/unregister", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project: decodedPath }),
    }).catch(() => null);
    refetch();
  }, [decodedPath, refetch]);

  if (loading && !data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-[560px] w-full" />
      </div>
    );
  }

  const summary = data?.summary;
  if (!summary || !summary.exists) {
    if (summary && summary.project_valid === false) {
      return (
        <Card>
          <EmptyState
            icon={<TriangleAlert size={20} />}
            title="Project folder not reachable"
            description="This project path no longer exists on disk (or sits outside the allowed roots), so its wiki cannot be read."
          />
        </Card>
      );
    }
    return <Onboarding project={decodedPath} onImported={refetch} />;
  }

  const compiling = summary.status === "compiling";
  const types = data ? Object.keys(data.types) : [];

  return (
    <div className="space-y-3">
      {/* status strip */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-2 text-[13px] font-semibold text-[var(--tt-fg)]">
          <Brain size={15} className="text-[var(--tt-brand)]" />
          Second brain
        </div>
        <Badge variant="outline" size="xs">{KIND_LABEL[summary.kind ?? ""] ?? summary.kind}</Badge>
        {summary.profile && <Badge variant="info" size="xs">{summary.profile}</Badge>}
        {summary.status === "complete" && <Badge variant="success" size="xs">complete</Badge>}
        {compiling && (
          <Badge variant="warn" size="xs">
            compiling {summary.batches_done ?? 0}/{summary.batches_total ?? "?"}
          </Badge>
        )}
        {summary.compiled_from_sha && (
          <span className="font-mono text-[10px] text-[var(--tt-fg-faint)]" title="Commit the wiki was compiled from">
            @{summary.compiled_from_sha.slice(0, 7)}
          </span>
        )}
        <span className="flex-1" />
        {summary.source === "registered" && (
          <button
            onClick={unregister}
            className="flex items-center gap-1.5 h-7 px-2.5 rounded-[var(--tt-radius-sm)] border border-[var(--tt-border)] text-[11px] text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)] hover:border-[var(--tt-border-strong)] transition-colors"
            title={`Imported from ${summary.wiki_path}. Click to un-import (removes the pointer only).`}
          >
            <Unplug size={12} />
            imported · un-import
          </button>
        )}
        <button
          onClick={refetch}
          className="flex items-center gap-1.5 h-7 px-2.5 rounded-[var(--tt-radius-sm)] border border-[var(--tt-border)] text-[11px] text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)] hover:border-[var(--tt-border-strong)] transition-colors"
          title="Re-read the wiki from disk"
        >
          {loading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
          Refresh
        </button>
      </div>

      {/* honest-status banners */}
      {compiling && (
        <div className="flex items-start gap-2 px-3.5 py-2.5 rounded-[var(--tt-radius)] border border-[var(--tt-warn-bd)] bg-[var(--tt-warn-bg)] text-[12px] text-[var(--tt-warn-fg)]">
          <TriangleAlert size={14} className="shrink-0 mt-0.5" />
          <span>
            This wiki is partially compiled ({summary.batches_done ?? 0} of {summary.batches_total ?? "?"} batches).
            The graph shows what exists so far; rerun <code className="font-mono">/brain-compile</code> in the project to finish.
          </span>
        </div>
      )}
      {(summary.kind === "obsidian_vault" || summary.kind === "markdown_wiki") && (
        <div className="flex items-start gap-2 px-3.5 py-2.5 rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-panel)] text-[12px] text-[var(--tt-fg-dim)]">
          <Brain size={14} className="shrink-0 mt-0.5 text-[var(--tt-brand)]" />
          <span>
            Rendered from a {KIND_LABEL[summary.kind]}: pages are untyped, so nodes are
            uncolored and staleness is unavailable. Run <code className="font-mono">/brain adopt</code> to
            formalize it into an OKF bundle.
          </span>
        </div>
      )}

      {/* the graph */}
      {data && data.nodes.length > 0 ? (
        <BrainGraph
          nodes={data.nodes}
          edges={data.edges}
          clusters={data.clusters}
          selectedId={selectedId}
          onSelect={onSelect}
          height={Math.max(560, typeof window !== "undefined" ? window.innerHeight - 420 : 640)}
        />
      ) : (
        <Card>
          <EmptyState
            icon={<Brain size={20} />}
            title="Wiki detected, but no concept pages yet"
            description="The bundle exists but holds no pages to graph. Run /brain-compile in the project to build the first batch."
          />
        </Card>
      )}

      <p className="text-[10.5px] text-[var(--tt-fg-faint)]">
        Hover a node to light up its neighborhood; click to open the page; drag nodes,
        scroll to zoom, drag the canvas to pan. Clusters group pages by wiki section
        (or by link communities for flat vaults).
      </p>

      <PageDrawer
        project={decodedPath}
        pageId={drawerId}
        types={types}
        dark={dark}
        onClose={() => setDrawerId(null)}
        onNavigate={onNavigate}
      />
    </div>
  );
}
