/* Project-scoped /loop derivation.
 *
 * The project tabs already hold this project's session rows (project-context),
 * and each row carries the full `loop` field the backend scan annotated
 * (lifecycle state + fire-turn footprint). So the per-project loop breakdown is
 * a pure client-side fold over those rows — no extra fetch, and it stays in
 * lockstep with the project filter for free.
 *
 * This deliberately mirrors backend/main.py's /analytics `loops`/`by_loop`
 * aggregation so the numbers match the global Analytics tab exactly:
 *   - footprint tokens/cost are the loop's OWN fire-response turns, never the
 *     whole session (a loop session does plenty of non-loop work too);
 *   - the per-loop map is keyed by job_id || session_id (last write wins, same
 *     as the backend dict), while the summary counters count every loop session.
 * Loop tokens/cost are an attribution VIEW — already part of session totals,
 * never re-summed into them.
 */
import type { SessionLoop, SessionRow } from "./project-context";

export interface LoopRow {
  key: string;
  sessionId: string;
  agent: string;
  label: string;
  state: LoopState;
  mode: string;
  cadence: string;
  cadenceSeconds?: number;
  recurring: boolean;
  iterations: number;
  tokens: number;         // footprint (loop fire turns only)
  cost: number;           // footprint
  sessionTokens: number;
  sessionCost: number;
  jobId?: string | null;
  sourceSignal?: string;
  createdAt?: string | null;
  lastFired?: string | null;
  expiresAt?: string | null;
  expiredReason?: string | null;
  cancelledAt?: string | null;
}

export interface LoopSummary {
  total: number;
  active: number;
  expired: number;
  cancelled: number;
  unknown: number;
  loopSessions: number;
  totalIterations: number;
  loopTokens: number;
  loopCost: number;
}

export type LoopState = "active" | "expired" | "cancelled" | "unknown";

function normState(s?: string): LoopState {
  return s === "active" || s === "expired" || s === "cancelled" ? s : "unknown";
}

export interface ProjectLoops {
  rows: LoopRow[];
  summary: LoopSummary;
}

export function deriveProjectLoops(sessions: SessionRow[]): ProjectLoops {
  const summary: LoopSummary = {
    total: 0, active: 0, expired: 0, cancelled: 0, unknown: 0,
    loopSessions: 0, totalIterations: 0, loopTokens: 0, loopCost: 0,
  };
  const byKey = new Map<string, LoopRow>();

  for (const s of sessions) {
    const lp: SessionLoop | undefined = s.loop;
    if (!lp || !lp.is_loop) continue;

    const state = normState(lp.state);
    summary.total += 1;
    summary.loopSessions += 1;
    if (state === "active") summary.active += 1;
    else if (state === "expired") summary.expired += 1;
    else if (state === "cancelled") summary.cancelled += 1;
    else summary.unknown += 1;

    const iterations = lp.iterations || 0;
    const tokens = lp.footprint_tokens || 0;
    const cost = lp.footprint_cost || 0;
    summary.totalIterations += iterations;
    summary.loopTokens += tokens;
    summary.loopCost += cost;

    const key = lp.job_id || s.id;
    byKey.set(key, {
      key,
      sessionId: s.id,
      agent: s.agent,
      label: lp.prompt_preview || "",
      state,
      mode: lp.mode || "",
      cadence: lp.cadence || "",
      cadenceSeconds: lp.cadence_seconds,
      recurring: lp.recurring !== false,
      iterations,
      tokens,
      cost,
      sessionTokens: s.tokens?.total || 0,
      sessionCost: s.cost || 0,
      jobId: lp.job_id,
      sourceSignal: lp.source_signal,
      createdAt: lp.created_at,
      lastFired: lp.last_fired,
      expiresAt: lp.expires_at,
      expiredReason: lp.expired_reason,
      cancelledAt: lp.cancelled_at,
    });
  }

  const rows = [...byKey.values()].sort((a, b) => b.iterations - a.iterations);
  summary.loopCost = Number(summary.loopCost.toFixed(6));
  return { rows, summary };
}

/* ── Presentation helpers (shared by config + insights tabs) ── */

export const LOOP_STATE: Record<LoopState, { dot: string; label: string; ring: string }> = {
  active:    { dot: "bg-emerald-400",                                          label: "text-emerald-300",       ring: "border-emerald-500/40" },
  expired:   { dot: "bg-[var(--tt-fg-dim)]",                                   label: "text-[var(--tt-fg-dim)]", ring: "border-[var(--tt-border)]" },
  cancelled: { dot: "bg-amber-400",                                           label: "text-amber-300",         ring: "border-amber-500/40" },
  unknown:   { dot: "bg-transparent border border-[var(--tt-border-strong)]", label: "text-[var(--tt-fg-muted)]", ring: "border-[var(--tt-border)]" },
};

export function loopStateTone(s: LoopState) {
  return LOOP_STATE[s] ?? LOOP_STATE.unknown;
}

/** Human interval from cadence_seconds + mode (matches the trace LoopCard).
    Only Claude's dynamic ScheduleWakeup loop is a self-pacing heartbeat; every
    other mode (Claude fixed_cron, Grok's "scheduler") is a fixed interval. */
export function loopInterval(row: Pick<LoopRow, "cadenceSeconds" | "mode">): string {
  const s = row.cadenceSeconds;
  if (row.mode === "dynamic") return s ? `~${s}s heartbeat` : "Self-paced";
  if (s && s % 86400 === 0) return `Every ${s / 86400}d`;
  if (s && s % 3600 === 0) return `Every ${s / 3600}h`;
  if (s && s % 60 === 0) return `Every ${s / 60}m`;
  if (s) return `Every ${s}s`;
  return row.mode === "fixed_cron" ? "Cron schedule" : "Self-paced";
}

export function loopReasonLabel(r?: string | null): string {
  return (
    {
      cron_expired_7d: "reached its 7-day auto-expiry",
      one_shot_completed: "ran once and finished",
      stale_session_ended: "session ended (no recent fire)",
      cancelled: "cancelled",
    } as Record<string, string>
  )[r || ""] || r || "";
}

export function loopRel(iso?: string | null): string {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (isNaN(t)) return "";
  const diff = Date.now() - t;
  const abs = Math.abs(diff);
  const unit =
    abs >= 86400000 ? `${Math.round(abs / 86400000)}d`
    : abs >= 3600000 ? `${Math.round(abs / 3600000)}h`
    : `${Math.round(abs / 60000)}m`;
  return diff >= 0 ? `${unit} ago` : `in ${unit}`;
}

export function loopFmtNum(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}
