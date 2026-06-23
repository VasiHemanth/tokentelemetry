"use client";

import Link from "next/link";
import { Wallet, ArrowRight, AlertTriangle } from "lucide-react";

import { useResource } from "@/lib/api";
import { cn } from "@/lib/cn";
import { getAgent } from "@/lib/agents";
import { formatCost, formatTokens } from "@/lib/format";
import { Card, CardHeader, CardTitle } from "@/components/ui";
import {
  type BudgetStatus, type BudgetLimitType, budgetTone,
} from "@/lib/budgets";

/** Format a USD-or-token amount per the budget's limit type. */
function fmtAmount(v: number, type: BudgetLimitType): string {
  return type === "usd" ? formatCost(v) : `${formatTokens(v)} tok`;
}

const TONE_BAR: Record<string, string> = {
  ok: "bg-[var(--tt-brand)]",
  warn: "bg-[var(--tt-warn)]",
  over: "bg-[var(--tt-danger)]",
};
const TONE_TEXT: Record<string, string> = {
  ok: "text-[var(--tt-fg)]",
  warn: "text-[var(--tt-warn)]",
  over: "text-[var(--tt-danger)]",
};

function periodLabel(b: BudgetStatus): string {
  if (b.period === "rolling_30d") return "last 30 days";
  if (b.period === "weekly") return "this week";
  return "this month";
}

function ProgressRow({
  label, labelColor, b,
}: { label: string; labelColor?: string; b: BudgetStatus }) {
  const tone = budgetTone(b.fraction);
  const pct = Math.min(100, Math.round(b.fraction * 100));
  return (
    <div className="grid grid-cols-[120px_1fr_auto] items-center gap-3">
      <span
        className="text-[11px] font-semibold uppercase tracking-[0.14em] truncate"
        style={labelColor ? { color: labelColor } : undefined}
      >
        {label}
      </span>
      <div className="h-2 rounded-full tt-tint-1 overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-[width] duration-500", TONE_BAR[tone])}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={cn("tabular text-[11px] whitespace-nowrap", TONE_TEXT[tone])}>
        {fmtAmount(b.used, b.limit_type)} / {fmtAmount(b.limit_value, b.limit_type)}
        <span className="text-[var(--tt-fg-dim)]"> · {pct}%</span>
      </span>
    </div>
  );
}

/** A tracked agent that has no sub-budget — show spend, no bar. */
function TrackedRow({
  label, labelColor, used, limitType,
}: { label: string; labelColor?: string; used: number; limitType: BudgetLimitType }) {
  return (
    <div className="grid grid-cols-[120px_1fr_auto] items-center gap-3">
      <span
        className="text-[11px] font-semibold uppercase tracking-[0.14em] truncate"
        style={labelColor ? { color: labelColor } : undefined}
      >
        {label}
      </span>
      <div className="h-2 rounded-full tt-tint-1 overflow-hidden opacity-40" />
      <span className="tabular text-[11px] text-[var(--tt-fg-dim)] whitespace-nowrap">
        {fmtAmount(used, limitType)}
        <span className="opacity-60"> · no limit</span>
      </span>
    </div>
  );
}

export default function BudgetCard({
  projectPath, configHref,
}: { projectPath: string; configHref: string }) {
  const { data, loading } = useResource<{ budgets: BudgetStatus[] }>(
    "/budgets",
    { pollMs: 60_000, initial: undefined },
  );

  if (loading || !data) return null;
  const budgets = data.budgets ?? [];

  // Project-scoped budgets only (project total + per-agent on this project).
  const projTotal = budgets.find(
    (b) => b.filters.project === projectPath && !b.filters.agent && !b.filters.model,
  );
  const agentBudgets = budgets.filter(
    (b) => b.filters.project === projectPath && !!b.filters.agent && !b.filters.model,
  );

  // Nothing set for this project → discoverable prompt.
  if (!projTotal && agentBudgets.length === 0) {
    return (
      <Card padding="lg" className="border-dashed">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <div className="h-9 w-9 grid place-items-center rounded-[var(--tt-radius)] tt-tint-1 text-[var(--tt-fg-dim)] shrink-0">
              <Wallet size={16} />
            </div>
            <div className="min-w-0">
              <div className="text-[13px] font-medium text-[var(--tt-fg)]">No budget set for this project</div>
              <div className="text-[12px] text-[var(--tt-fg-dim)] mt-0.5">
                Track spend against a monthly limit — overall or per agent.
              </div>
            </div>
          </div>
          <Link
            href={configHref}
            className="inline-flex items-center gap-1 h-8 px-3 rounded-[var(--tt-radius)] text-[12px] font-medium text-[var(--tt-brand)] hover:tt-tint-1 transition-colors shrink-0"
          >
            Set a budget <ArrowRight size={13} />
          </Link>
        </div>
      </Card>
    );
  }

  // Reference limit type for tracked-agent formatting (prefer the project total).
  const refType: BudgetLimitType = projTotal?.limit_type ?? agentBudgets[0]?.limit_type ?? "usd";

  // Agents that already have a sub-budget — don't double-render them as "tracked".
  const budgetedAgents = new Set(agentBudgets.map((b) => b.filters.agent!));

  // Tracked-only agents: present in the project-total breakdown but with no sub-budget.
  const tracked = projTotal
    ? Object.entries(projTotal.breakdown_by_agent)
        .filter(([a]) => !budgetedAgents.has(a))
        .map(([a, v]) => ({ agent: a, used: refType === "usd" ? v.cost : v.tokens }))
        .filter((x) => x.used > 0)
    : [];

  const headerAlert = projTotal && projTotal.alert_level != null;

  return (
    <Card padding="lg">
      <CardHeader>
        <div>
          <CardTitle>
            <Wallet size={14} className="text-[var(--tt-brand)]" /> Budget
            {headerAlert && (
              <AlertTriangle size={13} className="text-[var(--tt-warn)] ml-1" />
            )}
          </CardTitle>
          <p className="text-[11px] text-[var(--tt-fg-dim)] mt-0.5">
            Spend {projTotal ? periodLabel(projTotal) : periodLabel(agentBudgets[0])} vs limit. Observational — alerts only, no caps.
          </p>
        </div>
        <Link
          href={configHref}
          className="text-[11px] text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] transition-colors"
        >
          Edit
        </Link>
      </CardHeader>

      <div className="space-y-2.5">
        {projTotal && <ProgressRow label="Project" b={projTotal} />}

        {(agentBudgets.length > 0 || tracked.length > 0) && (
          <div className="pt-3 mt-1 border-t border-[var(--tt-border)] space-y-2.5">
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--tt-fg-dim)]">
              Per agent
            </div>
            {agentBudgets.map((b) => {
              const meta = getAgent(b.filters.agent!);
              return <ProgressRow key={b.id} label={meta.label} labelColor={meta.hex} b={b} />;
            })}
            {tracked.map((t) => {
              const meta = getAgent(t.agent);
              return (
                <TrackedRow
                  key={t.agent}
                  label={meta.label}
                  labelColor={meta.hex}
                  used={t.used}
                  limitType={refType}
                />
              );
            })}
          </div>
        )}
      </div>
    </Card>
  );
}
