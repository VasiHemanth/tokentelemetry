"use client";

import { memo, useMemo, useState } from "react";
import { Brain, Maximize2 } from "lucide-react";
import { formatReasoningContent } from "@/lib/traceTree/content";
import ConversationMarkdown from "./ConversationMarkdown";
import ContentModal from "./ContentModal";

/** A cheap inline preview; the larger saved record is formatted only on demand. */
function RecordedReasoning({ value }: { value: unknown }) {
  const preview = useMemo(() => formatReasoningContent(value, 1200), [value]);
  const [expanded, setExpanded] = useState(false);
  if (preview.kind === "empty") return null;
  return <section aria-label="Recorded reasoning" className="my-3 min-w-0 rounded-lg border border-[var(--tt-violet-bd)] bg-[var(--tt-violet-bg)] p-3">
    <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
      <h3 title="Reasoning text or a summary saved by the harness" className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--tt-violet-fg)]"><Brain size={13} />Recorded reasoning <span className="font-normal text-[var(--tt-fg-muted)]">· preview</span></h3>
      <button type="button" aria-label="Expand recorded reasoning" onClick={() => setExpanded(true)} className="inline-flex shrink-0 items-center gap-1.5 rounded px-1.5 py-1 text-xs text-[var(--tt-violet-fg)] hover:bg-[var(--tt-raised)]"><Maximize2 size={13} />Expand</button>
    </div>
    <div className="line-clamp-4 break-words"><ConversationMarkdown text={preview.text} compact /></div>
    {expanded && <ContentModal label="Recorded reasoning" value={value} reasoning initialFormatted onClose={() => setExpanded(false)} />}
  </section>;
}

export default memo(RecordedReasoning);
