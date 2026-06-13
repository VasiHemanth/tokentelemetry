"use client";

import { AlertTriangle } from "lucide-react";
import {
  PLAN_LABEL, TASK_TYPE_LABEL, CHARGES_LABEL,
  type AgentRouteOverview, type RouteBucket, type TaskType, type BucketCharges,
} from "@/lib/billing";

// Stage 1: structure only. Renders the per-task-type drain ORDER (which bucket
// pays first), charge badges, pool sizes and the no-fallback warning. Live pool
// *fill* meters need per-session task-type attribution and come in stage 2.

const CHARGE_STYLE: Record<BucketCharges, string> = {
  included: "text-[var(--tt-success-fg)] bg-[var(--tt-success-fg)]/10",
  api_rate: "text-[var(--tt-warning-fg,#b45309)] bg-[var(--tt-warning-fg,#b45309)]/10",
  electricity: "text-[var(--tt-fg-dim)] bg-[var(--tt-fg-dim)]/10",
};

function poolText(b: RouteBucket): string | null {
  if (b.pool_usd != null) return `$${b.pool_usd.toFixed(0)}/${b.pool_period ?? "month"} pool`;
  if (b.pool_requests != null)
    return `${b.pool_requests.toLocaleString()} requests/${b.pool_period ?? "day"}`;
  return null;
}

function BucketRow({ bucket, index }: { bucket: RouteBucket; index: number }) {
  const pool = poolText(bucket);
  return (
    <div className="flex items-start gap-2 py-1.5">
      <span className="mt-0.5 flex h-4.5 w-4.5 shrink-0 items-center justify-center rounded-full bg-[var(--tt-bg-elev)] text-[10px] font-semibold text-[var(--tt-fg-muted)]">
        {index + 1}
      </span>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[12px] font-medium text-[var(--tt-fg)]">{bucket.label}</span>
          <span className={`rounded px-1.5 py-px text-[10px] font-medium ${CHARGE_STYLE[bucket.charges]}`}>
            {CHARGES_LABEL[bucket.charges]}
          </span>
          {pool && (
            <span className="rounded px-1.5 py-px text-[10px] font-medium text-[var(--tt-fg-muted)] bg-[var(--tt-bg-elev)]">
              {pool}
            </span>
          )}
          {bucket.no_spillover && (
            <span className="flex items-center gap-0.5 text-[10px] text-[var(--tt-danger-fg)]">
              <AlertTriangle size={10} /> no fallback
            </span>
          )}
        </div>
        {bucket.note && (
          <p className="mt-0.5 text-[11px] leading-snug text-[var(--tt-fg-muted)]">{bucket.note}</p>
        )}
      </div>
    </div>
  );
}

export function DrainOrder({
  overview,
  asOf,
  saving,
  onPlanChange,
}: {
  overview: AgentRouteOverview;
  asOf: string;
  saving: boolean;
  onPlanChange: (plan: string | null) => void;
}) {
  const taskTypes = Object.keys(overview.routes) as TaskType[];

  // When both task types resolve through an identical bucket sequence (Codex,
  // Gemini, all paygo agents), collapse to a single list — the split is only
  // worth screen space where it changes the answer (Claude post-June-15).
  const sameRoute =
    taskTypes.length === 2 &&
    JSON.stringify(overview.routes[taskTypes[0]].buckets.map((b) => b.id)) ===
      JSON.stringify(overview.routes[taskTypes[1]].buckets.map((b) => b.id));

  return (
    <div className="mt-1 mb-2 rounded-md border border-[var(--tt-border)] bg-[var(--tt-bg)]/50 px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-[var(--tt-fg-muted)]">
          Drain order
        </span>
        {overview.plans.length > 0 && (
          <select
            value={overview.plans.includes(overview.plan) ? overview.plan : "default"}
            disabled={saving}
            onChange={(e) => onPlanChange(e.target.value === "default" ? null : e.target.value)}
            className="rounded-md border border-[var(--tt-border)] bg-[var(--tt-bg-elev)] px-2 py-1 text-[11px] text-[var(--tt-fg)] outline-none focus:border-[var(--tt-brand)] cursor-pointer"
          >
            <option value="default">Plan: default</option>
            {overview.plans.map((p) => (
              <option key={p} value={p}>Plan: {PLAN_LABEL[p] ?? p}</option>
            ))}
          </select>
        )}
      </div>

      {sameRoute ? (
        <div className="mt-1">
          {overview.routes[taskTypes[0]].buckets.map((b, i) => (
            <BucketRow key={b.id} bucket={b} index={i} />
          ))}
        </div>
      ) : (
        taskTypes.map((tt) => (
          <div key={tt} className="mt-1.5">
            <div className="text-[11px] font-medium text-[var(--tt-fg-dim)]">
              {TASK_TYPE_LABEL[tt]}
            </div>
            {overview.routes[tt].buckets.map((b, i) => (
              <BucketRow key={`${tt}-${b.id}`} bucket={b} index={i} />
            ))}
          </div>
        ))
      )}

      <p className="mt-1.5 text-[10px] text-[var(--tt-fg-muted)]">
        Provider billing rules verified {asOf}. Plans change often — treat pools as approximate.
      </p>
    </div>
  );
}
