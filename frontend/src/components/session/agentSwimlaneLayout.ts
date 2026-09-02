export interface SubagentTimelineEntry {
  agent_id?: string | null;
  child_session_id?: string | null;
  agent_type?: string | null;
  agent_role?: string | null;
  description?: string | null;
  nickname?: string | null;
  model?: string | null;
  status?: string | null;
  started_at?: string | number | null;
  startedAt?: string | number | null;
  completed_at?: string | number | null;
  completedAt?: string | number | null;
  ended_at?: string | number | null;
  duration_ms?: number | null;
  durationMs?: number | null;
  [key: string]: unknown;
}

export type SwimlaneTiming = "absolute" | "relative" | "unknown";
export type SwimlaneLayoutMode = "absolute" | "relative" | "mixed" | "unknown";

export interface AgentSwimlaneLane {
  id: string;
  label: string;
  detail: string | null;
  status: string | null;
  startMs: number | null;
  durationMs: number | null;
  leftPct: number;
  widthPct: number;
  timing: SwimlaneTiming;
  entry: SubagentTimelineEntry;
}

export interface AgentSwimlaneLayout {
  lanes: AgentSwimlaneLane[];
  mode: SwimlaneLayoutMode;
  startMs: number | null;
  endMs: number | null;
  durationMs: number;
}

interface MeasuredLane {
  entry: SubagentTimelineEntry;
  id: string;
  label: string;
  detail: string | null;
  status: string | null;
  startMs: number | null;
  durationMs: number | null;
  timing: SwimlaneTiming;
}

function asText(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const text = value.trim();
  return text.length > 0 ? text : null;
}

function asDuration(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : null;
}

/** Parse ISO timestamps, epoch milliseconds, and epoch seconds. */
function asTimestamp(value: unknown): number | null {
  if (value == null || value === "") return null;

  const numeric = typeof value === "number"
    ? value
    : typeof value === "string" && /^\d+(?:\.\d+)?$/.test(value.trim())
      ? Number(value)
      : null;

  if (numeric != null) {
    if (!Number.isFinite(numeric) || numeric < 0) return null;
    // Current epoch milliseconds are 13 digits; timestamps below 1e11 are seconds.
    return numeric < 100_000_000_000 ? numeric * 1_000 : numeric;
  }

  if (typeof value !== "string") return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function laneIdentity(entry: SubagentTimelineEntry, index: number) {
  const agentId = asText(entry.agent_id);
  const childId = asText(entry.child_session_id);
  const description = asText(entry.description);
  const nickname = asText(entry.nickname);
  const role = asText(entry.agent_role) ?? asText(entry.agent_type);

  return {
    id: agentId ?? childId ?? `subagent-${index + 1}`,
    label: description ?? nickname ?? role ?? childId ?? agentId ?? `Subagent ${index + 1}`,
    detail: role && role !== description && role !== nickname ? role : null,
    status: asText(entry.status),
  };
}

function measureLane(entry: SubagentTimelineEntry, index: number): MeasuredLane {
  const identity = laneIdentity(entry, index);
  const start = asTimestamp(entry.started_at ?? entry.startedAt);
  const completed = asTimestamp(
    entry.completed_at ?? entry.completedAt ?? entry.ended_at,
  );
  const recordedDuration = asDuration(entry.duration_ms ?? entry.durationMs);

  if (start != null && completed != null && completed >= start) {
    return {
      ...identity,
      entry,
      startMs: start,
      durationMs: completed - start,
      timing: "absolute",
    };
  }

  if (start != null && recordedDuration != null) {
    return {
      ...identity,
      entry,
      startMs: start,
      durationMs: recordedDuration,
      timing: "absolute",
    };
  }

  if (completed != null && recordedDuration != null) {
    return {
      ...identity,
      entry,
      startMs: completed - recordedDuration,
      durationMs: recordedDuration,
      timing: "absolute",
    };
  }

  if (recordedDuration != null) {
    return {
      ...identity,
      entry,
      startMs: null,
      durationMs: recordedDuration,
      timing: "relative",
    };
  }

  return {
    ...identity,
    entry,
    startMs: null,
    durationMs: null,
    timing: "unknown",
  };
}

function percentage(value: number, domain: number): number {
  return Math.max(0, Math.min(100, (value / domain) * 100));
}

/**
 * Build visual lanes without inferring concurrency where timestamps are absent.
 * Duration-only entries intentionally begin at zero and remain marked `relative`.
 */
export function buildAgentSwimlaneLayout(
  entries: readonly SubagentTimelineEntry[],
): AgentSwimlaneLayout {
  const measured = entries.map(measureLane);
  const absolute = measured.filter(
    (lane): lane is MeasuredLane & { startMs: number; durationMs: number } =>
      lane.timing === "absolute" && lane.startMs != null && lane.durationMs != null,
  );
  const relative = measured.filter(
    (lane): lane is MeasuredLane & { durationMs: number } =>
      lane.timing === "relative" && lane.durationMs != null,
  );

  const startMs = absolute.length > 0
    ? Math.min(...absolute.map((lane) => lane.startMs))
    : null;
  const endMs = absolute.length > 0
    ? Math.max(...absolute.map((lane) => lane.startMs + lane.durationMs))
    : null;
  const absoluteDuration = startMs != null && endMs != null ? endMs - startMs : 0;
  const relativeDuration = relative.reduce(
    (maximum, lane) => Math.max(maximum, lane.durationMs),
    0,
  );
  const durationMs = Math.max(absoluteDuration, relativeDuration);
  const domain = Math.max(durationMs, 1);

  let mode: SwimlaneLayoutMode = "unknown";
  if (absolute.length > 0 && relative.length > 0) mode = "mixed";
  else if (absolute.length > 0) mode = "absolute";
  else if (relative.length > 0) mode = "relative";

  const lanes = measured.map<AgentSwimlaneLane>((lane) => {
    if (lane.timing === "absolute" && lane.startMs != null && lane.durationMs != null) {
      return {
        ...lane,
        leftPct: percentage(lane.startMs - (startMs ?? lane.startMs), domain),
        widthPct: percentage(lane.durationMs, domain),
      };
    }

    if (lane.timing === "relative" && lane.durationMs != null) {
      return {
        ...lane,
        leftPct: 0,
        widthPct: percentage(lane.durationMs, domain),
      };
    }

    return { ...lane, leftPct: 0, widthPct: 0 };
  });

  return { lanes, mode, startMs, endMs, durationMs };
}

export function formatSwimlaneDuration(durationMs: number): string {
  const seconds = Math.max(0, durationMs) / 1_000;
  if (seconds < 60) {
    const precision = seconds > 0 && seconds < 20 && !Number.isInteger(seconds) ? 1 : 0;
    const rounded = precision === 1 ? Math.round(seconds * 10) / 10 : Math.round(seconds);
    return `${rounded.toFixed(precision)}s`;
  }

  const wholeSeconds = Math.round(seconds);
  const hours = Math.floor(wholeSeconds / 3_600);
  const minutes = Math.floor((wholeSeconds % 3_600) / 60);
  const remainder = wholeSeconds % 60;

  if (hours > 0) {
    return `${hours}h${minutes > 0 ? ` ${minutes}m` : ""}${remainder > 0 ? ` ${remainder}s` : ""}`;
  }
  return `${minutes}m${remainder > 0 ? ` ${remainder}s` : ""}`;
}
