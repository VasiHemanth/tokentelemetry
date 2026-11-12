"use client";

import Link from "next/link";
import { Loader2 } from "lucide-react";
import { useResource } from "@/lib/api";
import type { WasteExplain, WasteOccurrence } from "@/lib/waste";
import ReadImage, { isImagePath } from "@/components/trace/ReadImage";

type Mark = { call: number | null; turn: number | null; hot: boolean };

/** One mark per call, placed by where it falls in the session's tool calls. */
function Track({ marks, total }: { marks: Mark[]; total: number }) {
  const span = Math.max(total, 1);
  return (
    <div className="relative h-4 w-full rounded border border-[var(--tt-border)] bg-[var(--tt-sunken)]">
      {marks.map((m, i) => m.call == null ? null : (
        <span
          key={i}
          title={`Call ${m.call} of ${total}${m.turn != null ? `, turn ${m.turn}` : ""}${m.hot ? ", repeat" : ", first read"}`}
          className="absolute top-0 h-full w-[3px] rounded-sm"
          style={{
            left: `calc(${Math.min(100, (100 * m.call) / span)}% - 1px)`,
            background: m.hot ? "var(--tt-warn)" : "var(--tt-fg-faint)",
          }}
        />
      ))}
    </div>
  );
}

function turnsText(occ: WasteOccurrence[]): string {
  const turns = Array.from(new Set(occ.filter(o => o.repeat && o.turn != null).map(o => o.turn as number))).sort((a, b) => a - b);
  if (!turns.length) return "";
  const shown = turns.slice(0, 8).join(", ");
  return `Repeated in turn${turns.length > 1 ? "s" : ""} ${shown}${turns.length > 8 ? ` and ${turns.length - 8} more` : ""}`;
}

export function WasteWhy({ id, agent, toolCalls, sessionHref }: { id: string; agent: string; toolCalls: number; sessionHref: string }) {
  const { data, loading, error } = useResource<WasteExplain>(`/waste/session/${encodeURIComponent(id)}?agent=${encodeURIComponent(agent)}`);

  if (loading && !data) {
    return (
      <div className="flex items-center gap-2 py-3 text-[12px] text-[var(--tt-fg-muted)]">
        <Loader2 size={13} className="animate-spin" /> Reading this session&apos;s trace
      </div>
    );
  }
  if (error || !data) {
    return <div className="py-3 text-[12px] text-[var(--tt-fg-muted)]">Could not read this session&apos;s trace.</div>;
  }
  const { rereads, retries, errors } = data;
  const nothing = !rereads.length && !retries.length && !errors.total;

  return (
    <div className="space-y-5 py-3 text-[12px]">
      {(rereads.length > 0 || retries.length > 0) && (
        <div className="flex items-center justify-between gap-4 text-[11px] text-[var(--tt-fg-faint)]">
          <span>Each bar is the whole session from start to end. Amber marks are repeats. Hover a mark for its position.</span>
          <span className="whitespace-nowrap">{toolCalls.toLocaleString()} tool calls</span>
        </div>
      )}

      {rereads.length > 0 && (
        <div>
          <div className="mb-2 font-medium text-[var(--tt-fg)]">Files read again ({rereads.length})</div>
          <div className="space-y-2">
            {rereads.slice(0, 12).map(r => (
              <div key={r.path} className="grid grid-cols-[minmax(140px,240px)_1fr] items-center gap-3">
                <div className="flex min-w-0 items-center gap-2">
                  {isImagePath(r.path) && <ReadImage path={r.path} sessionId={id} agent={agent} variant="thumb" />}
                  <div className="min-w-0">
                  <div className="truncate font-mono text-[var(--tt-fg)]" title={r.path}>{r.name}</div>
                  <div className="truncate text-[11px] text-[var(--tt-fg-muted)]">
                    read {r.reads} times, {r.repeats} repeat{r.repeats === 1 ? "" : "s"}{r.edits ? `, edited ${r.edits} times` : ", never edited"}
                  </div>
                  <Link href={`${sessionHref}&view=execution&q=${encodeURIComponent(r.name)}`} className="text-[11px] text-[var(--tt-accent)] hover:underline">
                    Show these reads in the trace
                  </Link>
                  </div>
                </div>
                <div className="min-w-0">
                  <Track total={toolCalls} marks={r.occurrences.map(o => ({ call: o.call, turn: o.turn, hot: o.repeat }))} />
                  <div className="mt-0.5 truncate text-[11px] text-[var(--tt-fg-faint)]">{turnsText(r.occurrences)}</div>
                </div>
              </div>
            ))}
            {rereads.length > 12 && <div className="text-[11px] text-[var(--tt-fg-faint)]">and {rereads.length - 12} more files</div>}
          </div>
        </div>
      )}

      {retries.length > 0 && (
        <div>
          <div className="mb-2 font-medium text-[var(--tt-fg)]">Identical calls in a row ({retries.length})</div>
          <div className="space-y-2">
            {retries.slice(0, 8).map((r, i) => (
              <div key={i} className="grid grid-cols-[minmax(140px,240px)_1fr] items-center gap-3">
                <div className="min-w-0">
                  <div className="truncate font-mono text-[var(--tt-fg)]">{r.tool || "tool"}</div>
                  <div className="truncate text-[11px] text-[var(--tt-fg-muted)]" title={r.path ?? undefined}>
                    {r.count} identical calls{r.turn != null ? `, turn ${r.turn}` : ""}
                  </div>
                </div>
                <Track total={toolCalls} marks={[{ call: r.call, turn: r.turn, hot: true }]} />
              </div>
            ))}
          </div>
        </div>
      )}

      {errors.total > 0 && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="font-medium text-[var(--tt-fg)]">Failed calls ({errors.total})</span>
          <span className="text-[var(--tt-fg-muted)]">{errors.by_tool.map(t => `${t.tool} ${t.count}`).join(", ")}</span>
          <Link href={`${sessionHref}&view=execution&tfilter=errors`} className="text-[11px] text-[var(--tt-accent)] hover:underline">
            Open trace with errors only
          </Link>
        </div>
      )}

      {nothing && (
        <div className="text-[var(--tt-fg-muted)]">
          No repeats or failed calls were found in this trace. The flag comes from session totals (cost, cache use or context growth).
        </div>
      )}
    </div>
  );
}
