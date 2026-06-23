"use client";

// Cost attribution tree for a session and its spawned subagents.
//
// When a parent agent delegates work to child sessions, the parent's own token
// cost only tells part of the story — the work it kicked off may cost far more.
// This card fetches GET /sessions/{id}/tree (backed by _rollup_delegation_costs
// in backend/main.py) and renders the subtree with per-node own/total costs so a
// user can see "this workflow cost $0.52 total" traced to the session that
// started it.

import React, { useState } from "react";
import Link from "next/link";
import { ChevronRight, ChevronDown, GitBranch, Layers } from "lucide-react";
import { AgentBadge } from "@/components/ui";
import { useResource } from "@/lib/api";
import { formatCost } from "@/lib/format";

interface TreeNode {
  session_id: string;
  agent?: string | null;
  project?: string | null;
  display?: string | null;
  cost_usd: number;
  total_cost_usd: number;
  children_cost_usd: number;
  child_count: number;
  depth: number;
  children: TreeNode[];
}

function shortId(id: string): string {
  if (id.length <= 12) return id;
  return `${id.slice(0, 8)}…${id.slice(-4)}`;
}

function TreeRow({ node }: { node: TreeNode }) {
  const hasChildren = node.children.length > 0 || node.child_count > 0;
  // Root (depth 0) defaults open so the user sees the breakdown immediately.
  const [open, setOpen] = useState(node.depth < 2);
  const hasSubtree = node.total_cost_usd > node.cost_usd + 1e-9;

  return (
    <div>
      <div
        className="flex items-center gap-2 py-1.5 pr-2 rounded-md hover:bg-[var(--tt-panel)]/60 transition-colors"
        style={{ paddingLeft: `${node.depth * 16 + 4}px` }}
      >
        {hasChildren ? (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-label={open ? "Collapse children" : "Expand children"}
            className="shrink-0 text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)] transition-colors"
          >
            {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
        ) : (
          <span className="shrink-0 w-[14px]" aria-hidden />
        )}

        {node.agent && <AgentBadge agent={node.agent} withLabel={false} />}

        <Link
          href={`/sessions/${node.session_id}?agent=${encodeURIComponent(node.agent || "")}`}
          className="font-mono text-[11px] text-[var(--tt-fg-muted)] hover:text-[var(--tt-brand)] hover:underline truncate"
          title={node.session_id}
        >
          {shortId(node.session_id)}
        </Link>

        <div className="ml-auto flex items-center gap-2 shrink-0">
          <span className="text-[11px] text-[var(--tt-fg)] tabular-nums" title="Own token cost">
            {formatCost(node.cost_usd)}
          </span>
          {hasSubtree && (
            <span
              className="inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-medium tabular-nums bg-[var(--tt-warn-bg)] text-[var(--tt-warn-fg)] border-[var(--tt-warn-bd)]"
              title={`Subtree total: own ${formatCost(node.cost_usd)} + children ${formatCost(node.children_cost_usd)}`}
            >
              <Layers size={10} />
              subtree {formatCost(node.total_cost_usd)}
            </span>
          )}
        </div>
      </div>

      {open && node.children.length > 0 && (
        <div>
          {node.children.map((child) => (
            <TreeRow key={child.session_id} node={child} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function DelegationTreeCard({ sessionId }: { sessionId: string }) {
  const { data, loading, error } = useResource<TreeNode>(
    sessionId ? `/sessions/${encodeURIComponent(sessionId)}/tree` : null,
  );

  if (loading) {
    return (
      <div className="rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)]/40 p-4">
        <div className="h-4 w-40 rounded bg-[var(--tt-border)]/40 animate-pulse" />
      </div>
    );
  }

  if (error || !data) {
    // Tree is supplementary; if it can't load, stay quiet rather than erroring.
    return null;
  }

  const noChildren = data.child_count === 0 && data.children.length === 0;

  return (
    <div className="rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)]/40 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-[10px] font-black text-[var(--tt-fg-dim)] uppercase tracking-[0.2em]">
          <GitBranch size={14} /> Cost Attribution Tree
        </h3>
        {!noChildren && (
          <span className="text-[10px] text-[var(--tt-fg-muted)] tabular-nums">
            {formatCost(data.cost_usd)} own + {formatCost(data.children_cost_usd)} children
            {" = "}
            <span className="text-[var(--tt-warn-fg)] font-semibold">
              {formatCost(data.total_cost_usd)} total
            </span>
          </span>
        )}
      </div>

      {noChildren ? (
        <div className="text-[11px] italic text-[var(--tt-fg-faint)]">
          No child sessions. This session didn&apos;t spawn any subagents.
        </div>
      ) : (
        <div className="text-[11px]">
          <TreeRow node={data} />
        </div>
      )}
    </div>
  );
}
