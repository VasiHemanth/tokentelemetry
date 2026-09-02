"use client";

import { AlertTriangle, ChevronRight, Clock, Cpu, GitBranch, Layers } from "lucide-react";
import type { ReactNode } from "react";
import { formatCost, formatTokens } from "@/lib/format";
import {
  buildDelegationTopology,
  type DelegationNode,
  type DelegationTokens,
} from "@/lib/delegationTopology";

export interface DelegationTopologyEntry<TEntry = unknown> extends Omit<DelegationNode, "entry"> {
  /** Original delegation record returned by the trace API. */
  entry: TEntry;
}

export interface DelegationParent {
  label: string;
  model?: string;
  tokens?: DelegationTokens;
  cost?: number;
  durationMs?: number;
}

export interface DelegationTopologyCardProps<TEntry = unknown> {
  parent: DelegationParent;
  entries: readonly DelegationTopologyEntry<TEntry>[];
  /** Opens the existing child-trace experience for a direct child. */
  onOpen: (entry: TEntry) => void;
  /** Eight is deliberately dense enough for a session card, not a graph canvas. */
  maxVisible?: number;
  className?: string;
}

function isFailure(status: string | undefined): boolean {
  return /^(failed|error|cancelled|canceled|interrupted|timed_out|timeout)$/i.test(status ?? "");
}

function displayModel(model: string | undefined): string | undefined {
  return model?.replace(/-\d{8}$/, "");
}

function displayStatus(status: string | undefined): string | undefined {
  return status?.replaceAll("_", " ");
}

function Metric({ children, title }: { children: ReactNode; title?: string }) {
  return (
    <span title={title} className="font-mono text-[10px] tabular-nums text-[var(--tt-fg-dim)] whitespace-nowrap">
      {children}
    </span>
  );
}

function NodeMetrics({ node }: { node: Pick<DelegationNode, "model" | "tokens" | "cost" | "durationMs"> }) {
  const tokenTotal = node.tokens?.total;
  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 min-h-3">
      {node.model && <Metric title="Model"><Cpu size={10} className="inline -mt-px mr-1" />{displayModel(node.model)}</Metric>}
      {tokenTotal != null && <Metric title="Tokens used">{formatTokens(tokenTotal)} tok</Metric>}
      {node.cost != null && <Metric title="Attributed cost">{formatCost(node.cost)}</Metric>}
      {node.durationMs != null && <Metric title="Duration"><Clock size={10} className="inline -mt-px mr-1" />{(node.durationMs / 1000).toFixed(1)}s</Metric>}
    </div>
  );
}

function ChildNode<TEntry>({ entry, onOpen, compact = false }: { entry: DelegationTopologyEntry<TEntry>; onOpen: (entry: TEntry) => void; compact?: boolean }) {
  const failed = isFailure(entry.status);
  return (
    <button
      type="button"
      onClick={() => onOpen(entry.entry)}
      className={[
        "group relative min-w-0 text-left rounded-[var(--tt-radius)] border bg-[var(--tt-sunken)] transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--tt-border-focus)]",
        failed
          ? "border-[var(--tt-danger-bd)] hover:border-[var(--tt-danger-fg)]/70"
          : "border-[var(--tt-border)] hover:border-[var(--tt-brand)]/60 hover:bg-[var(--tt-panel)]",
        compact ? "w-full px-2.5 py-2" : "w-[min(15rem,78vw)] shrink-0 px-3 py-2.5",
      ].join(" ")}
      aria-label={`Open ${entry.label} subagent trace`}
      title="Open this direct subagent trace"
    >
      <span className="flex items-start gap-2">
        <span className={[
          "mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-sm border",
          failed ? "border-[var(--tt-danger-bd)] bg-[var(--tt-danger-bg)] text-[var(--tt-danger-fg)]" : "border-[var(--tt-brand)]/30 bg-[var(--tt-brand)]/10 text-[var(--tt-brand)]",
        ].join(" ")}>
          {failed ? <AlertTriangle size={10} aria-hidden="true" /> : <GitBranch size={10} aria-hidden="true" />}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1.5">
            <span className="truncate text-[11px] font-semibold text-[var(--tt-fg)]">{entry.label}</span>
            {entry.status && <span className={failed ? "text-[9px] font-semibold uppercase tracking-[0.12em] text-[var(--tt-danger-fg)]" : "text-[9px] font-semibold uppercase tracking-[0.12em] text-[var(--tt-fg-faint)]"}>{displayStatus(entry.status)}</span>}
          </span>
          {entry.description && <span className="mt-0.5 block truncate text-[10px] text-[var(--tt-fg-muted)]">{entry.description}</span>}
          <NodeMetrics node={entry} />
        </span>
        <ChevronRight size={13} aria-hidden="true" className="mt-0.5 shrink-0 text-[var(--tt-fg-faint)] group-hover:text-[var(--tt-brand)]" />
      </span>
    </button>
  );
}

/**
 * A compact parent-to-child topology for delegated work. Solid visual links
 * indicate only the recorded spawn relationship; it deliberately does not
 * imply that child agents communicated with one another.
 */
export function DelegationTopologyCard<TEntry>({
  parent,
  entries,
  onOpen,
  maxVisible = 8,
  className = "",
}: DelegationTopologyCardProps<TEntry>) {
  const topology = buildDelegationTopology(entries, { maxVisible });
  const visibleEntries = new Set(topology.visible);
  const hidden = entries.filter((entry) => !visibleEntries.has(entry));

  if (entries.length === 0) return null;

  return (
    <section className={`rounded-[var(--tt-radius-lg)] border border-[var(--tt-brand)]/25 bg-[var(--tt-panel)]/60 p-4 sm:p-5 ${className}`} aria-labelledby="delegation-topology-heading">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 id="delegation-topology-heading" className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-[var(--tt-brand)]">
            <Layers size={13} strokeWidth={2.5} aria-hidden="true" /> Delegation topology
          </h2>
          <p className="mt-1 text-[11px] text-[var(--tt-fg-dim)]">Recorded parent-to-child trace relationships</p>
        </div>
        <span className="rounded-full border border-[var(--tt-border)] bg-[var(--tt-sunken)] px-2 py-1 font-mono text-[10px] tabular-nums text-[var(--tt-fg-muted)]">
          {topology.total} direct subagent{topology.total === 1 ? "" : "s"}
        </span>
      </div>

      <div className="grid gap-3 lg:grid-cols-[minmax(12rem,0.72fr)_1.5rem_minmax(0,1.7fr)] lg:items-center">
        <div className="rounded-[var(--tt-radius)] border border-[var(--tt-brand)]/35 bg-[var(--tt-brand)]/[0.07] px-3 py-3">
          <div className="flex items-start gap-2">
            <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md border border-[var(--tt-brand)]/35 bg-[var(--tt-brand)]/10 text-[var(--tt-brand)]"><GitBranch size={13} aria-hidden="true" /></span>
            <div className="min-w-0">
              <p className="text-[9px] font-bold uppercase tracking-[0.16em] text-[var(--tt-brand)]">Parent session</p>
              <p className="truncate text-[12px] font-semibold text-[var(--tt-fg)]">{parent.label}</p>
              <NodeMetrics node={parent} />
            </div>
          </div>
        </div>

        <div aria-hidden="true" className="hidden h-full min-h-8 lg:flex items-center justify-center">
          <span className="h-px w-full bg-[linear-gradient(90deg,var(--tt-brand),var(--tt-border-strong))]" />
        </div>

        <div className="min-w-0">
          <p className="mb-2 text-[9px] font-bold uppercase tracking-[0.16em] text-[var(--tt-fg-faint)]">Direct subagents</p>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2" role="list" aria-label="Direct subagent traces">
            {topology.visible.map((entry) => (
              <div key={entry.id} role="listitem">
                <ChildNode entry={entry as DelegationTopologyEntry<TEntry>} onOpen={onOpen} />
              </div>
            ))}
          </div>
        </div>
      </div>

      {topology.hasOverflow && (
        <details className="mt-3 border-t border-[var(--tt-border)] pt-3">
          <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 rounded-[var(--tt-radius)] px-1 text-[11px] font-medium text-[var(--tt-fg-muted)] hover:text-[var(--tt-brand)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--tt-border-focus)]">
            <ChevronRight size={13} aria-hidden="true" className="transition-transform [[open]_&]:rotate-90" />
            Show {topology.hiddenCount} more direct subagent{topology.hiddenCount === 1 ? "" : "s"}
          </summary>
          <div className="mt-2 grid max-h-56 grid-cols-1 gap-2 overflow-y-auto pb-1 pr-1 sm:grid-cols-2" role="list" aria-label="Additional direct subagent traces">
            {hidden.map((entry) => (
              <div key={entry.id} role="listitem">
                <ChildNode entry={entry} onOpen={onOpen} compact />
              </div>
            ))}
          </div>
        </details>
      )}
    </section>
  );
}

export default DelegationTopologyCard;
