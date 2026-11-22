import { Database, CheckCircle2, RefreshCw, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui";
import {
  RECALL_DOC_TYPES, formatEstimate, formatShortDate,
  type RecallDelta, type TypeCounts,
} from "@/lib/recall";
import { docTypeMeta } from "./docTypes";

function countParts(counts: TypeCounts | undefined, word: string): string[] {
  if (!counts) return [];
  const out: string[] = [];
  for (const t of RECALL_DOC_TYPES) {
    const n = counts[t];
    if (!n) continue;
    const m = docTypeMeta(t);
    const name = n === 1 ? m.label.toLowerCase() : m.plural;
    out.push(`${n.toLocaleString()}${word ? ` ${word}` : ""} ${name}`);
  }
  return out;
}

/** The sentence for a stale index, e.g. "142 new chunks, 3 new skills, 2 changed sessions since Nov 18." */
export function staleSummary(d: RecallDelta): string {
  const parts: string[] = [];
  if (d.new_chunks_estimate) parts.push(`${d.new_chunks_estimate.toLocaleString()} new chunks`);
  parts.push(...countParts(d.new, "new"), ...countParts(d.changed, "changed"), ...countParts(d.removed, "removed"));
  const since = formatShortDate(d.last_indexed_at);
  const body = parts.length ? parts.join(", ") : "Changes";
  return since ? `${body} since ${since}.` : `${body}.`;
}

export function DeltaBanner({ delta, loading, error, newModel, canIndex, blockedReason, busy, running, onIndex }: {
  delta: RecallDelta | null;
  loading: boolean;
  error: string | null;
  /** Name of the model that would be used now. */
  newModel: string;
  /** False until semantic search is set up and enabled. */
  canIndex: boolean;
  blockedReason?: string;
  busy: boolean;
  running: boolean;
  onIndex: (full: boolean) => void;
}) {
  if (loading && !delta) {
    return <div className="h-14 rounded-[var(--tt-radius)] tt-tint-1 animate-pulse" aria-busy />;
  }
  if (error && !delta) {
    return <p className="text-[12px] text-[var(--tt-danger-fg)]">Could not check this project&apos;s index: {error}</p>;
  }
  if (!delta) return null;

  const est = formatEstimate(delta.estimate_seconds);
  const disabled = busy || running || !canIndex;
  const reason = !canIndex ? blockedReason : undefined;

  const box = "flex flex-wrap items-center gap-x-4 gap-y-2 rounded-[var(--tt-radius)] border px-3.5 py-3 text-[12.5px]";
  const neutral = "border-[var(--tt-border)] bg-[var(--tt-panel)] text-[var(--tt-fg-muted)]";

  switch (delta.state) {
    case "up_to_date":
      return (
        <div className={`${box} ${neutral}`} role="status">
          <CheckCircle2 size={14} className="text-[var(--tt-success-fg)] shrink-0" />
          <span className="flex-1 min-w-0">
            Indexed {formatShortDate(delta.last_indexed_at)}
            {delta.lock?.model ? <> with <span className="font-mono">{delta.lock.model}</span></> : null}.
          </span>
        </div>
      );
    case "stale":
      return (
        <div className={`${box} ${neutral}`} role="status">
          <RefreshCw size={14} className="text-[var(--tt-brand)] shrink-0" />
          <span className="flex-1 min-w-[220px] tabular">{staleSummary(delta)}</span>
          <Button size="sm" variant="primary" disabled={disabled} title={reason} onClick={() => onIndex(false)}>
            Re-index{est ? ` (${est})` : ""}
          </Button>
        </div>
      );
    case "model_changed":
      return (
        <div className={`${box} border-[var(--tt-warn-bd)] bg-[var(--tt-warn-bg)] text-[var(--tt-warn-fg)]`} role="status">
          <AlertTriangle size={14} className="shrink-0" />
          <span className="flex-1 min-w-[220px]">
            This project was indexed with <span className="font-mono">{delta.lock?.model ?? "another model"}</span>.
            Semantic search is off for it until you re-index. Vectors from different models are never mixed.
          </span>
          <Button size="sm" variant="primary" disabled={disabled} title={reason} onClick={() => onIndex(true)}>
            Re-index everything with {newModel}
          </Button>
        </div>
      );
    case "never_indexed": {
      const what = countParts(delta.new, "");
      return (
        <div className={`${box} ${neutral}`} role="status">
          <Database size={14} className="text-[var(--tt-brand)] shrink-0" />
          <span className="flex-1 min-w-[220px] tabular">
            This project is not indexed.
            {what.length > 0 ? <> Will embed {what.join(", ")}.</> : null}
            {delta.new_chunks_estimate
              ? <> About {delta.new_chunks_estimate.toLocaleString()} chunks{est ? `, ${est}` : ""}.</>
              : null}
          </span>
          <Button size="sm" variant="primary" disabled={disabled} title={reason} onClick={() => onIndex(false)}>
            Index this project
          </Button>
        </div>
      );
    }
    default:
      return (
        <div className={`${box} ${neutral}`} role="status">
          <AlertTriangle size={14} className="shrink-0" />
          <span className="flex-1">Indexing is not available for this project right now.</span>
        </div>
      );
  }
}
