"use client";

import { ChevronDown, ChevronUp, GitBranch } from "lucide-react";
import { useId, useMemo, useState } from "react";

import { cn } from "@/lib/cn";

import {
  buildAgentSwimlaneLayout,
  formatSwimlaneDuration,
  type AgentSwimlaneLane,
  type SubagentTimelineEntry,
  type SwimlaneLayoutMode,
} from "./agentSwimlaneLayout";

export interface AgentSwimlaneDelegation {
  subagents?: SubagentTimelineEntry[] | null;
  child_session_ids?: string[] | null;
}

export interface AgentSwimlaneTimelineProps {
  delegation: AgentSwimlaneDelegation;
  onOpen: (entry: SubagentTimelineEntry) => void;
  /** Number of lanes shown before the disclosure. Defaults to 8. */
  initialVisibleLanes?: number;
  className?: string;
}

const STATUS_TONES: Record<string, string> = {
  completed: "text-[var(--tt-success-fg)]",
  complete: "text-[var(--tt-success-fg)]",
  running: "text-[var(--tt-info-fg)]",
  active: "text-[var(--tt-info-fg)]",
  failed: "text-[var(--tt-danger-fg)]",
  error: "text-[var(--tt-danger-fg)]",
  interrupted: "text-[var(--tt-warn-fg)]",
};

function timelineDescription(mode: SwimlaneLayoutMode): string {
  if (mode === "absolute") {
    return "Bars align to timestamps recorded in the trace.";
  }
  if (mode === "relative") {
    return "Start times were not recorded; bars compare duration only.";
  }
  if (mode === "mixed") {
    return "Timestamped bars align; dashed bars compare duration only.";
  }
  return "The trace identifies these agents but does not record their timing.";
}

function timingLabel(lane: AgentSwimlaneLane): string {
  if (lane.timing === "unknown" || lane.durationMs == null) return "timing unavailable";
  const duration = formatSwimlaneDuration(lane.durationMs);
  return lane.timing === "relative" ? `${duration}, relative duration` : duration;
}

function Axis({ mode, durationMs }: { mode: SwimlaneLayoutMode; durationMs: number }) {
  if (mode === "unknown") return null;

  return (
    <div
      className="grid min-w-[36rem] grid-cols-[minmax(9rem,12rem)_minmax(18rem,1fr)_4.5rem] items-end gap-3 px-3 pb-1"
      aria-hidden="true"
    >
      <span />
      <div className="grid grid-cols-3 text-[9px] font-medium uppercase tracking-[0.12em] text-[var(--tt-fg-faint)]">
        <span>{mode === "relative" ? "Relative start" : "First start"}</span>
        <span className="text-center">+{formatSwimlaneDuration(durationMs / 2)}</span>
        <span className="text-right">+{formatSwimlaneDuration(durationMs)}</span>
      </div>
      <span />
    </div>
  );
}

function TimelineBar({ lane }: { lane: AgentSwimlaneLane }) {
  if (lane.timing === "unknown") {
    return (
      <span className="absolute inset-x-2 top-1/2 -translate-y-1/2 text-center text-[9px] uppercase tracking-[0.12em] text-[var(--tt-fg-faint)]">
        Timing unavailable
      </span>
    );
  }

  const isRelative = lane.timing === "relative";
  return (
    <span
      className={cn(
        "absolute inset-y-1 rounded-[var(--tt-radius-sm)] border transition-[filter] group-hover/lane:brightness-125",
        isRelative
          ? "border-dashed border-[var(--tt-info-bd)] bg-[var(--tt-info-bg)]"
          : "border-[var(--tt-border-focus)] bg-[var(--tt-brand-glow)]",
      )}
      style={{
        left: `${lane.leftPct}%`,
        width: `${lane.widthPct}%`,
        minWidth: lane.durationMs === 0 ? "4px" : "8px",
      }}
    >
      <span
        className={cn(
          "absolute inset-y-0 left-0 w-0.5 rounded-full",
          isRelative ? "bg-[var(--tt-info)]" : "bg-[var(--tt-brand)]",
        )}
      />
    </span>
  );
}

function LaneRow({ lane, onOpen }: { lane: AgentSwimlaneLane; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={`Open subagent trace for ${lane.label}; ${timingLabel(lane)}`}
      className="group/lane grid min-w-[36rem] w-full grid-cols-[minmax(9rem,12rem)_minmax(18rem,1fr)_4.5rem] items-center gap-3 rounded-[var(--tt-radius)] px-3 py-1.5 text-left transition-colors hover:bg-[var(--tt-raised)]"
    >
      <span className="min-w-0">
        <span className="block truncate text-[11px] font-semibold text-[var(--tt-fg)]">
          {lane.label}
        </span>
        <span className="mt-0.5 flex min-w-0 items-center gap-1.5 text-[9px] uppercase tracking-[0.12em] text-[var(--tt-fg-dim)]">
          {lane.detail && <span className="truncate">{lane.detail}</span>}
          {lane.status && (
            <span className={cn("shrink-0", STATUS_TONES[lane.status.toLowerCase()])}>
              {lane.status}
            </span>
          )}
        </span>
      </span>

      <span className="relative h-7 overflow-hidden rounded-[var(--tt-radius-sm)] border border-[var(--tt-border)] bg-[var(--tt-sunken)]">
        <span className="absolute inset-0 grid grid-cols-4" aria-hidden="true">
          <span className="border-r border-[var(--tt-border)]" />
          <span className="border-r border-[var(--tt-border)]" />
          <span className="border-r border-[var(--tt-border)]" />
          <span />
        </span>
        <TimelineBar lane={lane} />
      </span>

      <span className="tabular text-right text-[10px] text-[var(--tt-fg-dim)]">
        {lane.durationMs == null ? "—" : formatSwimlaneDuration(lane.durationMs)}
      </span>
    </button>
  );
}

/**
 * A timing view of delegated work. It visualizes only recorded execution
 * windows and durations; it does not draw or infer agent communication edges.
 */
export function AgentSwimlaneTimeline({
  delegation,
  onOpen,
  initialVisibleLanes = 8,
  className,
}: AgentSwimlaneTimelineProps) {
  const titleId = useId();
  const laneListId = useId();
  const [expanded, setExpanded] = useState(false);

  const entries = useMemo<SubagentTimelineEntry[]>(() => {
    if (delegation.subagents?.length) return delegation.subagents;
    return (delegation.child_session_ids ?? []).map((childSessionId) => ({
      child_session_id: childSessionId,
    }));
  }, [delegation.child_session_ids, delegation.subagents]);

  const layout = useMemo(() => buildAgentSwimlaneLayout(entries), [entries]);
  if (layout.lanes.length === 0) return null;

  const visibleLimit = Number.isFinite(initialVisibleLanes)
    ? Math.max(1, Math.floor(initialVisibleLanes))
    : 8;
  const hasDisclosure = layout.lanes.length > visibleLimit;
  const visibleLanes = expanded ? layout.lanes : layout.lanes.slice(0, visibleLimit);
  const hiddenCount = layout.lanes.length - visibleLimit;

  return (
    <section
      aria-labelledby={titleId}
      className={cn(
        "overflow-hidden rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)]",
        className,
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--tt-border)] px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <GitBranch size={13} className="shrink-0 text-[var(--tt-brand)]" aria-hidden="true" />
            <h3
              id={titleId}
              className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--tt-fg)]"
            >
              Agent execution
            </h3>
            <span className="tabular rounded-full border border-[var(--tt-border)] bg-[var(--tt-sunken)] px-1.5 py-0.5 text-[9px] text-[var(--tt-fg-muted)]">
              {layout.lanes.length}
            </span>
          </div>
          <p className="mt-1 text-[10px] text-[var(--tt-fg-dim)]">
            {timelineDescription(layout.mode)}
          </p>
        </div>
        {layout.mode === "mixed" && (
          <div className="flex items-center gap-3 text-[9px] text-[var(--tt-fg-dim)]" aria-hidden="true">
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-4 rounded-full bg-[var(--tt-brand)]" /> timestamped
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-4 rounded-full border border-dashed border-[var(--tt-info-bd)] bg-[var(--tt-info-bg)]" /> relative
            </span>
          </div>
        )}
      </div>

      <div className="overflow-x-auto py-2">
        <Axis mode={layout.mode} durationMs={layout.durationMs} />
        <ol
          id={laneListId}
          className={cn(
            "space-y-0.5 px-1",
            expanded && hasDisclosure && "max-h-[28rem] overflow-y-auto overscroll-contain",
          )}
          aria-label={`${layout.lanes.length} delegated agent execution lanes`}
          tabIndex={expanded && hasDisclosure ? 0 : undefined}
        >
          {visibleLanes.map((lane, index) => (
            <li key={`${lane.id}-${index}`}>
              <LaneRow lane={lane} onOpen={() => onOpen(lane.entry)} />
            </li>
          ))}
        </ol>
      </div>

      {hasDisclosure && (
        <div className="border-t border-[var(--tt-border)] px-3 py-2">
          <button
            type="button"
            onClick={() => setExpanded((current) => !current)}
            aria-expanded={expanded}
            aria-controls={laneListId}
            className="flex w-full items-center justify-center gap-1.5 rounded-[var(--tt-radius-sm)] px-3 py-1.5 text-[10px] font-semibold text-[var(--tt-brand)] transition-colors hover:bg-[var(--tt-brand-glow)]"
          >
            {expanded ? (
              <>
                <ChevronUp size={12} aria-hidden="true" /> Show first {visibleLimit}
              </>
            ) : (
              <>
                <ChevronDown size={12} aria-hidden="true" /> Show {hiddenCount} more agents
              </>
            )}
          </button>
        </div>
      )}
    </section>
  );
}
