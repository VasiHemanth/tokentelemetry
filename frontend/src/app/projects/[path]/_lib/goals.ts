/* Project-scoped `/goal` derivation.
 *
 * Mirrors _lib/loops.ts: a pure client-side fold over the session rows the
 * project context already holds, so it stays in lockstep with the project
 * filter and needs no extra fetch.
 *
 * Where this deliberately DIFFERS from loops, and why:
 *
 *  - **A session has many goals.** `loop` is one object per session; `goals` is
 *    a list, because a session can arm several in sequence. So the fold is over
 *    (session x goal) pairs, and the key has to include the goal.
 *
 *  - **There is no single "goal cost" to total.** Cost means three unrelated
 *    things (see cost_basis) and summing across them is meaningless:
 *      native            Codex counted the tokens itself; they are a SHARE OF a
 *                        session total we already report.
 *      attributed_turns  Claude's extra turns caused by a blocked stop; genuinely
 *                        incremental.
 *      session           Grok/Antigravity have no per-goal boundary at all.
 *    So the summary keeps them in SEPARATE buckets and the UI never adds them.
 *
 *  - **State is not uniformly trustworthy.** Only Codex reports real status;
 *    everything else is inferred from breadcrumbs, which `stateSource` carries
 *    so the UI can mute it.
 */
import type { SessionRow } from "./project-context";

export type GoalState =
  | "active" | "paused" | "complete" | "blocked" | "armed" | "unknown";

export type GoalCostBasis = "native" | "attributed_turns" | "session";

export interface GoalRow {
  key: string;
  sessionId: string;
  agent: string;
  source: string;
  objective: string;          // "" when the agent doesn't record one
  objectiveTruncated: boolean;
  latestMessage?: string | null;
  state: GoalState;
  stateSource: "reported" | "inferred";
  costBasis: GoalCostBasis;
  tokens: number | null;      // null unless the agent gives us a real number
  cost: number | null;
  durationSeconds?: number | null;
  tokenBudget?: number | null;
  createdAt?: string | null;
  updatedAt?: string | null;
  sessionTokens: number;
  sessionCost: number;
  blocks: number;             // Claude only
  bursts: number[];           // Claude only
  capHit: boolean;            // Claude only
  checkpoints: number;        // Grok only
  statusRaw?: string | null;  // Codex only
  goalId?: string | null;
}

export interface GoalSummary {
  total: number;
  goalSessions: number;
  /** Still-running or resumable work: reported states only. */
  live: number;
  complete: number;
  /** Goals whose outcome the agent never recorded. */
  outcomeUnknown: number;
  reported: number;
  inferred: number;
  /** Kept apart on purpose — never add these together. */
  nativeTokens: number;
  attributedTokens: number;
  attributedCost: number;
  sessionBasisSessions: number;
  totalBlocks: number;
}

const STATES: GoalState[] = ["active", "paused", "complete", "blocked", "armed", "unknown"];

function normState(s?: string): GoalState {
  return (STATES as string[]).includes(s || "") ? (s as GoalState) : "unknown";
}

export interface ProjectGoals {
  rows: GoalRow[];
  summary: GoalSummary;
}

export function deriveProjectGoals(sessions: SessionRow[]): ProjectGoals {
  const summary: GoalSummary = {
    total: 0, goalSessions: 0, live: 0, complete: 0, outcomeUnknown: 0,
    reported: 0, inferred: 0, nativeTokens: 0, attributedTokens: 0,
    attributedCost: 0, sessionBasisSessions: 0, totalBlocks: 0,
  };
  const rows: GoalRow[] = [];

  for (const s of sessions) {
    const goals = s.goals;
    if (!Array.isArray(goals) || goals.length === 0) continue;
    summary.goalSessions += 1;
    let countedSessionBasis = false;

    goals.forEach((g, i) => {
      const state = normState(g.state);
      const basis = (g.cost_basis || "session") as GoalCostBasis;
      const ev = g.evidence || {};
      summary.total += 1;

      if (state === "active" || state === "paused") summary.live += 1;
      else if (state === "complete") summary.complete += 1;
      // "armed"/"blocked"/"unknown" all mean the agent never recorded an
      // outcome — that is the honest bucket, not a failure bucket.
      else summary.outcomeUnknown += 1;

      if (g.state_source === "reported") summary.reported += 1;
      else summary.inferred += 1;

      const tokens = typeof g.tokens === "number" ? g.tokens : null;
      if (basis === "native" && tokens) summary.nativeTokens += tokens;
      if (basis === "attributed_turns") {
        if (tokens) summary.attributedTokens += tokens;
        if (typeof g.cost === "number") summary.attributedCost += g.cost;
      }
      if (basis === "session" && !countedSessionBasis) {
        summary.sessionBasisSessions += 1;
        countedSessionBasis = true;
      }
      summary.totalBlocks += Number(ev.blocks || 0);

      rows.push({
        key: `${s.id}:${g.goal_id || i}`,
        sessionId: s.id,
        agent: s.agent,
        source: g.source || s.agent,
        objective: g.objective || "",
        objectiveTruncated: Boolean(g.objective_truncated),
        latestMessage: ev.latest_message ?? null,
        state,
        stateSource: g.state_source === "reported" ? "reported" : "inferred",
        costBasis: basis,
        tokens,
        cost: typeof g.cost === "number" ? g.cost : null,
        durationSeconds: g.duration_seconds ?? null,
        tokenBudget: g.token_budget ?? null,
        createdAt: g.created_at,
        updatedAt: g.updated_at,
        sessionTokens: s.tokens?.total || 0,
        sessionCost: s.cost || 0,
        blocks: Number(ev.blocks || 0),
        bursts: Array.isArray(ev.block_bursts) ? ev.block_bursts : [],
        capHit: Boolean(ev.cap_hit),
        checkpoints: Number(ev.checkpoints || 0),
        statusRaw: ev.status_raw ?? null,
        goalId: g.goal_id ?? null,
      });
    });
  }

  // Live work first (it's the only actionable kind), then by how much the goal
  // actually cost, then newest.
  const liveRank = (r: GoalRow) => (r.state === "active" || r.state === "paused" ? 0 : 1);
  rows.sort((a, b) =>
    liveRank(a) - liveRank(b) ||
    (b.tokens || 0) - (a.tokens || 0) ||
    String(b.createdAt || "").localeCompare(String(a.createdAt || "")));

  summary.attributedCost = Number(summary.attributedCost.toFixed(6));
  return { rows, summary };
}

/* ── Presentation helpers (shared by config + insights tabs) ── */

export const GOAL_STATE: Record<GoalState, { dot: string; label: string; ring: string }> = {
  active:   { dot: "bg-emerald-400", label: "text-emerald-300", ring: "border-emerald-500/40" },
  paused:   { dot: "bg-amber-400",   label: "text-amber-300",   ring: "border-amber-500/40" },
  complete: { dot: "bg-sky-400",     label: "text-sky-300",     ring: "border-sky-500/40" },
  blocked:  { dot: "bg-rose-400",    label: "text-rose-300",    ring: "border-rose-500/40" },
  armed:    { dot: "bg-[var(--tt-brand)]", label: "text-[var(--tt-brand)]", ring: "border-[var(--tt-brand)]/30" },
  unknown:  { dot: "bg-transparent border border-[var(--tt-border-strong)]", label: "text-[var(--tt-fg-muted)]", ring: "border-[var(--tt-border)]" },
};

export function goalStateTone(s: GoalState) {
  return GOAL_STATE[s] ?? GOAL_STATE.unknown;
}

/** What this agent's cost number actually means. Shown next to every figure so
 *  a native count is never read as extra spend. */
export function goalCostLabel(basis: GoalCostBasis): string {
  return {
    native: "counted by the agent, part of the session total",
    attributed_turns: "extra turns caused by a blocked stop",
    session: "no per-goal boundary — the session is the goal",
  }[basis];
}

export function goalStateLabel(r: Pick<GoalRow, "state" | "source">): string {
  if (r.state === "armed") return "armed, outcome unknown";
  if (r.state === "blocked") return "blocked from stopping";
  if (r.state === "unknown") return "outcome not recorded";
  return r.state;
}

export function goalDuration(s?: number | null): string {
  if (s == null) return "";
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`;
  return `${Math.floor(s / 3600)}h ${Math.round((s % 3600) / 60)}m`;
}
