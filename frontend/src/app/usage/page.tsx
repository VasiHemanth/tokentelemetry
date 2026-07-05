"use client";

import { useMemo, useState } from "react";
import { Gauge, AlertTriangle } from "lucide-react";

import { useResource } from "@/lib/api";
import { getAgent, ALL_AGENT_KEYS } from "@/lib/agents";
import { formatTokens, formatCost } from "@/lib/format";
import { PLAN_LABEL, CHARGES_LABEL, type AgentRouteOverview } from "@/lib/billing";
import {
  PageHeader, Card, CardHeader, CardTitle, EmptyState, Skeleton,
} from "@/components/ui";

interface WindowStats {
  input: number; output: number; cached: number; total: number;
  cost: number; session_count: number; cache_hit_pct: number | null;
}

type WindowKey = "today" | "7d" | "30d" | "all";

interface UsageData {
  agents: Record<string, Record<WindowKey, WindowStats>>;
  billing: Record<string, AgentRouteOverview>;
  generated_at: string;
}

const WINDOWS: { key: WindowKey; label: string }[] = [
  { key: "today", label: "Today" },
  { key: "7d", label: "7 days" },
  { key: "30d", label: "30 days" },
  { key: "all", label: "All time" },
];

// What each agent's OWN in-session command shows today, from researching each
// agent's docs. TokenTelemetry sources every card below from local session
// files regardless of whether the agent ships a command at all — this is the
// one place all of them line up. See docs/design/ for the full writeup.
const NATIVE_COMMAND: Record<string, { command: string; confidence: "confirmed" | "partial" | "none" }> = {
  claude:      { command: "/usage, /cost, /context", confidence: "confirmed" },
  codex:       { command: "/usage, /status", confidence: "confirmed" },
  gemini:      { command: "/stats", confidence: "confirmed" },
  antigravity: { command: "/context, /credits (docs conflict)", confidence: "partial" },
  qwen:        { command: "/stats (alias /usage)", confidence: "confirmed" },
  vibe:        { command: "/status (fields undocumented)", confidence: "partial" },
  cursor:      { command: "Settings → Usage only, no CLI command", confidence: "none" },
  copilot:     { command: "/usage (CLI, session-scoped only)", confidence: "confirmed" },
  opencode:    { command: "opencode stats (shell, not in-TUI)", confidence: "partial" },
  hermes:      { command: "hermes insights (fields undocumented)", confidence: "partial" },
  grok:        { command: "not found in docs", confidence: "none" },
  cline:       { command: "task header, live — no slash command", confidence: "partial" },
  smallcode:   { command: "/stats, /tokens, /budget", confidence: "confirmed" },
  openai_compat: { command: "n/a — generic passthrough", confidence: "none" },
};

const CONFIDENCE_STYLE: Record<string, string> = {
  confirmed: "text-[var(--tt-success-fg)] bg-[var(--tt-success-fg)]/10",
  partial: "text-[var(--tt-warn-fg,#b45309)] bg-[var(--tt-warn-fg,#b45309)]/10",
  none: "text-[var(--tt-fg-dim)] bg-[var(--tt-fg-dim)]/10",
};

const CONFIDENCE_LABEL: Record<string, string> = {
  confirmed: "Has native cmd",
  partial: "Docs disagree",
  none: "No native cmd",
};

function poolText(overview?: AgentRouteOverview): string | null {
  const active = overview?.routes?.interactive?.active;
  if (!active) return null;
  if (active.pool_usd != null) return `$${active.pool_usd.toFixed(0)}/${active.pool_period ?? "month"}`;
  if (active.pool_requests != null) return `${active.pool_requests.toLocaleString()}/${active.pool_period ?? "day"}`;
  return null;
}

function AgentUsageCard({
  agent, stats, overview,
}: { agent: string; stats: WindowStats; overview?: AgentRouteOverview }) {
  const meta = getAgent(agent);
  const Icon = meta.icon;
  const native = NATIVE_COMMAND[agent];
  const active = overview?.routes?.interactive?.active;
  const pool = poolText(overview);

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <span
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md"
            style={{ background: `${meta.hex}1a`, color: meta.hex }}
          >
            <Icon size={15} />
          </span>
          {meta.label}
        </CardTitle>
        {native && (
          <span
            title={native.command}
            className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium whitespace-nowrap ${CONFIDENCE_STYLE[native.confidence]}`}
          >
            {CONFIDENCE_LABEL[native.confidence]}
          </span>
        )}
      </CardHeader>

      {stats.session_count === 0 ? (
        <p className="text-[12px] text-[var(--tt-fg-dim)]">No sessions in this window.</p>
      ) : (
        <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-[12px]">
          <div>
            <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--tt-fg-dim)]">Tokens</div>
            <div className="tabular text-[16px] font-semibold text-[var(--tt-fg)]">{formatTokens(stats.total)}</div>
            <div className="text-[11px] text-[var(--tt-fg-muted)] tabular">
              {formatTokens(stats.input)} in · {formatTokens(stats.output)} out
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--tt-fg-dim)]">Cost (API equiv.)</div>
            <div className="tabular text-[16px] font-semibold text-[var(--tt-fg)]">{formatCost(stats.cost)}</div>
            <div className="text-[11px] text-[var(--tt-fg-muted)] tabular">{stats.session_count} sessions</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--tt-fg-dim)]">Cache hit</div>
            <div className="tabular text-[16px] font-semibold text-[var(--tt-fg)]">
              {stats.cache_hit_pct == null ? "—" : `${stats.cache_hit_pct}%`}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--tt-fg-dim)]">Plan</div>
            <div className="text-[13px] font-medium text-[var(--tt-fg)]">
              {overview ? (PLAN_LABEL[overview.plan] ?? overview.plan) : "—"}
            </div>
            {active && (
              <div className="flex flex-wrap items-center gap-1 mt-0.5">
                <span className={`rounded px-1.5 py-px text-[10px] font-medium ${CONFIDENCE_STYLE[active.charges === "included" ? "confirmed" : active.charges === "electricity" ? "none" : "partial"]}`}>
                  {CHARGES_LABEL[active.charges]}
                </span>
                {pool && (
                  <span className="rounded px-1.5 py-px text-[10px] font-medium text-[var(--tt-fg-muted)] bg-[var(--tt-bg-elev)]">
                    {pool} pool
                  </span>
                )}
                {active.no_spillover && (
                  <span className="flex items-center gap-0.5 text-[10px] text-[var(--tt-danger-fg)]">
                    <AlertTriangle size={10} /> no fallback
                  </span>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}

export default function UsagePage() {
  const [activeWindow, setActiveWindow] = useState<WindowKey>("today");
  const { data, loading } = useResource<UsageData>("/usage", { pollMs: 30_000 });

  const agentIds = useMemo(() => {
    if (!data) return [];
    // Known agents first in TT's canonical order, then anything the backend
    // detected that isn't in the static AGENTS map yet (e.g. a harness added
    // server-side before its frontend metadata lands) — never silently dropped.
    const detected = Object.keys(data.agents);
    const known = ALL_AGENT_KEYS.filter((a) => detected.includes(a));
    const unknown = detected.filter((a) => !(ALL_AGENT_KEYS as string[]).includes(a)).sort();
    return [...known, ...unknown];
  }, [data]);

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<Gauge size={18} />}
        eyebrow="Cross-agent"
        title="Usage"
        description="What every agent's own /usage, /stats, or /status command would show — Claude Code, Codex, Gemini CLI, and the rest — read from the same local session data TokenTelemetry already scans, in one place instead of switching tools."
      />

      <div className="flex items-center gap-1">
        {WINDOWS.map((w) => (
          <button
            key={w.key}
            type="button"
            onClick={() => setActiveWindow(w.key)}
            className={`rounded-md px-3 py-1.5 text-[12px] font-medium transition-colors cursor-pointer ${
              activeWindow === w.key
                ? "bg-[var(--tt-brand)] text-white"
                : "text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] border border-[var(--tt-border)]"
            }`}
          >
            {w.label}
          </button>
        ))}
      </div>

      {loading && !data ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-40 w-full" />)}
        </div>
      ) : agentIds.length === 0 ? (
        <EmptyState
          icon={<Gauge size={22} />}
          title="No agents detected yet"
          description="Run a coding agent TokenTelemetry supports and its usage will show up here."
        />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {agentIds.map((agent) => (
            <AgentUsageCard
              key={agent}
              agent={agent}
              stats={data!.agents[agent][activeWindow]}
              overview={data!.billing[agent]}
            />
          ))}
        </div>
      )}
    </div>
  );
}
