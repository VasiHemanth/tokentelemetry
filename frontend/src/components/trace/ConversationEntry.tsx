"use client";

import { useMemo } from "react";
import { ArrowUpRight, Brain, Check, ChevronRight, CircleAlert, FileSearch, GitBranch, MessageSquare, Sparkles, Terminal, User, Wrench } from "lucide-react";
import type { TraceSpan } from "@/lib/traceTree/types";
import { formatContent } from "@/lib/traceTree/content";
import { fmtClock, fmtDur } from "@/lib/traceTree/timeScale";
import type { LoadState } from "./SpanTable";
import InlineEvidence from "./InlineEvidence";
import ConversationMarkdown from "./ConversationMarkdown";

export interface ConversationEntryProps {
  span: TraceSpan;
  depth: number;
  agentColor?: string;
  selected: boolean;
  real: boolean;
  evidenceOpen: boolean;
  onToggleEvidence: (id: string) => void;
  open: boolean;
  load?: LoadState;
  onInspect: (id: string) => void;
  onToggle: (id: string) => void;
  onRetry: (id: string) => void;
}

export default function ConversationEntry({ span, depth, agentColor, selected, real, evidenceOpen, onToggleEvidence, open, load, onInspect, onToggle, onRetry }: ConversationEntryProps) {
  const isRequest = span.kind === "turn", isReply = span.kind === "llm", isAgent = span.kind === "agent", isSkill = span.kind === "skill";
  const notification = isRequest && span.turnKind === "notification";
  const activity = !isRequest && !isReply;
  const value = isRequest ? span.content?.input : isReply ? span.content?.output : undefined;
  const text = useMemo(() => formatContent(value, 6000), [value]);
  const hasResponse = isReply && !!text.text;
  const hasResult = span.content?.output !== undefined;
  const canExpand = isAgent && (!!span.agent?.childId || span.children.length > 0);
  const label = isReply ? hasResponse ? "Assistant" : span.recordOnly ? "Assistant entry" : "Model call" : notification && !span.recordOnly ? "Agent report" : span.title;
  const Icon = isRequest ? notification ? MessageSquare : User : isReply ? Sparkles : isAgent ? GitBranch : isSkill ? Wrench : Terminal;
  const nodeTone = isRequest && !notification ? "border-[var(--tt-border-focus)] bg-[var(--tt-brand-glow)] text-[var(--tt-brand)]" : isAgent ? "border-[var(--tt-violet-bd)] bg-[var(--tt-violet-bg)] text-[var(--tt-violet-fg)]" : "border-[var(--tt-border)] bg-[var(--tt-panel)] text-[var(--tt-fg-muted)]";
  const surface = isRequest ? "border-[var(--tt-border)] bg-[var(--tt-raised)]" : isAgent ? "border-[var(--tt-violet-bd)] bg-[var(--tt-violet-bg)]" : activity ? "border-[var(--tt-border)] bg-[var(--tt-canvas)]" : "border-transparent";
  const branchStyle = isAgent && agentColor ? { color: agentColor, borderColor: `color-mix(in srgb, ${agentColor} 30%, transparent)`, backgroundColor: `color-mix(in srgb, ${agentColor} 7%, var(--tt-panel))` } : undefined;
  const action = "inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-colors hover:bg-[var(--tt-raised)] hover:text-[var(--tt-fg)]";
  return <div className="grid min-w-0 grid-cols-[28px_minmax(0,1fr)] gap-2 sm:gap-3" style={{ marginLeft: Math.min(depth, 3) * 12 }}>
    <div className="relative flex justify-center">
      <div aria-hidden="true" className="absolute bottom-[-20px] left-1/2 top-8 border-l border-[var(--tt-border)]" />
      <span aria-hidden="true" style={branchStyle} className={`relative mt-1 flex size-7 shrink-0 items-center justify-center rounded-full border ${span.error ? "border-[var(--tt-danger-bd)] bg-[var(--tt-danger-bg)] text-[var(--tt-danger-fg)]" : nodeTone}`}><Icon size={13} /></span>
    </div>
    <article style={isAgent ? { borderColor: branchStyle?.borderColor, backgroundColor: branchStyle?.backgroundColor } : undefined} data-entry-kind={span.kind} aria-label={`${label}${selected ? ", selected" : ""}`} className={`group min-w-0 rounded-lg border ${surface} ${selected ? "!border-[var(--tt-border-focus)] ring-1 ring-[var(--tt-border-focus)]" : ""} ${span.error ? "!border-[var(--tt-danger-bd)]" : ""}`}>
      <div className={`${activity || !hasResponse && isReply ? "px-3 py-2.5" : "px-4 py-4"}`}>
        <div className="flex min-w-0 items-start justify-between gap-2">
          <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
            <span className={`${activity ? "font-mono text-[13px]" : "text-sm"} font-semibold text-[var(--tt-fg)] [overflow-wrap:anywhere]`}>{label}</span>
            {isRequest && !notification && <span className="rounded border border-[var(--tt-border-focus)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--tt-brand)]">Request</span>}
            {isAgent && <span style={{ color: agentColor }} className="text-xs text-[var(--tt-violet-fg)]">{span.agent?.background ? "Background agent" : "Delegated agent"}</span>}
            {isSkill && <span className="text-xs text-[var(--tt-cyan-fg)]">Skill</span>}
            {depth > 0 && <span className="inline-flex items-center gap-1 text-[11px] text-[var(--tt-fg-muted)]"><GitBranch size={11} />Child trace</span>}
            {span.error ? <span className="inline-flex items-center gap-1 rounded bg-[var(--tt-danger-bg)] px-1.5 py-0.5 text-xs font-medium text-[var(--tt-danger-fg)]"><CircleAlert size={11} />Error</span> : activity && !isAgent && <span className="inline-flex items-center gap-1 text-[11px] text-[var(--tt-fg-muted)]">{hasResult && <Check size={11} />}{hasResult ? "Result recorded" : "Call recorded"}</span>}
            {selected && <span className="text-[10px] font-medium text-[var(--tt-brand)]">Selected</span>}
          </div>
          <button type="button" aria-label={`Inspect ${span.title}`} title="Open full evidence" onClick={() => onInspect(span.id)} className="mt-0.5 shrink-0 rounded-md p-1.5 text-[var(--tt-fg-dim)] transition-colors hover:bg-[var(--tt-raised)] hover:text-[var(--tt-brand)] focus-visible:outline focus-visible:outline-[var(--tt-border-focus)]"><FileSearch size={14} /></button>
        </div>
        {(isRequest || hasResponse) && text.text ? <div className={`${isRequest ? "mt-3" : "mt-2"} min-w-0 break-words`}>
          {hasResponse ? <ConversationMarkdown text={text.text} /> : <p className="whitespace-pre-wrap text-[15px] leading-7 text-[var(--tt-fg)]">{text.text}</p>}
          {text.truncated && <button type="button" onClick={() => onInspect(span.id)} className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-[var(--tt-brand)]">Read complete record <ArrowUpRight size={12} /></button>}
        </div> : activity ? <p className="mt-1 break-words text-[13px] leading-6 text-[var(--tt-fg-muted)]">{span.label || (isAgent ? "Delegated work recorded by the harness" : "Recorded tool activity")}</p> : <p className="mt-1 text-xs leading-6 text-[var(--tt-fg-muted)]">{isReply ? "No response text in this record." : "No readable request in this record."}</p>}
        <div className={`${hasResponse || isRequest ? "mt-3" : "mt-1.5"} flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-[var(--tt-fg-muted)]`}>
          {real && <time className="font-mono tabular-nums">{fmtClock(span.start)}{!isRequest ? ` · ${span.approxStart ? "≈ " : ""}${fmtDur(span.end - span.start)}` : ""}</time>}
          {isReply && <span className="max-w-full truncate rounded border border-[var(--tt-border)] bg-[var(--tt-canvas)] px-1.5 py-0.5 font-mono text-[10px]" title={span.title}>{span.title}</span>}
          {span.content?.reasoning != null && <button type="button" onClick={() => onInspect(span.id)} className={`${action} border border-[var(--tt-border)] text-[var(--tt-fg-muted)]`}><Brain size={12} />Recorded reasoning</button>}
          {activity && <button type="button" onClick={() => onToggleEvidence(span.id)} aria-expanded={evidenceOpen} className={`${action} ${evidenceOpen ? "bg-[var(--tt-brand-glow)] text-[var(--tt-brand)]" : "text-[var(--tt-brand)]"}`}><ChevronRight size={12} className={evidenceOpen ? "rotate-90" : ""} />Input & result</button>}
          {canExpand && <button type="button" onClick={() => onToggle(span.id)} style={{ color: agentColor }} aria-expanded={open} className={`${action} text-[var(--tt-violet-fg)]`}><GitBranch size={12} />{open ? "Hide child recording" : "Explore child recording"}</button>}
          {isAgent && open && span.agent?.loaded && span.children.length === 0 && <span>No readable child records returned.</span>}
          {load?.state === "pending" && <span role="status">Loading child recording…</span>}
          {load?.state === "error" && <button type="button" onClick={() => onRetry(span.id)} className="text-xs text-[var(--tt-danger-fg)]">Could not load · Retry</button>}
        </div>
        {evidenceOpen && <InlineEvidence span={span} />}
      </div>
    </article>
  </div>;
}
