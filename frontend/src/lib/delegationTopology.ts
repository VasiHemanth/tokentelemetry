/**
 * Data-only helpers for the delegated-work topology. The compact view is
 * intentionally a parent-to-child representation: it describes spawn
 * relationships and never infers communication between child agents.
 */
export interface DelegationTokens {
  input?: number;
  output?: number;
  cached?: number;
  total?: number;
}

export interface DelegationNode {
  id: string;
  label: string;
  description?: string;
  model?: string;
  status?: string;
  durationMs?: number;
  cost?: number;
  tokens?: DelegationTokens;
  entry?: unknown;
}

export interface DelegationTopology {
  total: number;
  visible: DelegationNode[];
  hiddenCount: number;
  hasOverflow: boolean;
}

export interface DelegationTopologyOptions {
  /** The number of direct children rendered before using the overflow cluster. */
  maxVisible?: number;
}

function isFailure(status: string | undefined): boolean {
  return /^(failed|error|cancelled|canceled|interrupted|timed_out|timeout)$/i.test(status ?? "");
}

function relevance(entry: DelegationNode): number {
  if (isFailure(entry.status)) return 3;
  if ((entry.cost ?? 0) > 0 || (entry.tokens?.total ?? 0) > 0) return 2;
  if ((entry.durationMs ?? 0) > 0) return 1;
  return 0;
}

/**
 * Select direct child nodes for a legible graph. It never mutates source data
 * and preserves source order within each relevance tier, which keeps equally
 * relevant nodes stable during trace playback.
 */
export function getVisibleDelegationNodes(entries: readonly DelegationNode[], maxVisible: number): DelegationNode[] {
  if (!Number.isFinite(maxVisible) || maxVisible <= 0) return [];
  if (entries.length <= maxVisible) return [...entries];

  return entries
    .map((entry, index) => ({ entry, index, relevance: relevance(entry) }))
    .sort((a, b) => b.relevance - a.relevance || a.index - b.index)
    .slice(0, Math.floor(maxVisible))
    .map(({ entry }) => entry);
}

export function buildDelegationTopology(
  entries: readonly DelegationNode[],
  { maxVisible = 8 }: DelegationTopologyOptions = {},
): DelegationTopology {
  const visible = getVisibleDelegationNodes(entries, maxVisible);
  const hiddenCount = Math.max(0, entries.length - visible.length);
  return {
    total: entries.length,
    visible,
    hiddenCount,
    hasOverflow: hiddenCount > 0,
  };
}
