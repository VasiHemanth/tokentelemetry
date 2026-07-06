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
// agent's docs. TokenTelemetry sources the tokens/cost above from local session
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

// Session-limit & reset model per agent, from researching each provider's docs
// (July 2026). Deliberately qualitative — the exact hourly/weekly numbers churn
// every few months, and TokenTelemetry can't see your *live remaining* quota
// (that lives on the provider's servers; the agent's own command queries it).
// What's durable is the SHAPE of the limit and when it resets, plus a one-line
// note on where the live figure comes from.
interface LimitInfo {
  model: string;   // limit shape, e.g. "5h session + weekly cap"
  reset: string;   // reset cadence, e.g. "5h after 1st prompt · weekly"
  note: string;    // the relevant comment: native cmd + local-vs-live caveat
}
const LIMIT_INFO: Record<string, LimitInfo> = {
  claude: {
    model: "5h session + weekly cap",
    reset: "5h after 1st prompt · weekly",
    note: "Live % via /usage; quota is shared with claude.ai. TT counts your local tokens.",
  },
  codex: {
    model: "5h window + weekly cap",
    reset: "rolling 5h · weekly",
    note: "Live limits via /status (counted in messages, not tokens). TT counts local tokens.",
  },
  gemini: {
    model: "Daily request cap",
    reset: "daily",
    note: "Free tier ~1k req/day, 60 rpm. /stats shows session tokens, not the daily quota.",
  },
  qwen: {
    model: "Daily request cap",
    reset: "daily",
    note: "Qwen OAuth free tier resets daily. /stats (alias /usage) shows session tokens.",
  },
  antigravity: {
    model: "Model credits",
    reset: "periodic (docs vary)",
    note: "/credits and /context; reset cadence isn't clearly documented.",
  },
  copilot: {
    model: "Monthly credits",
    reset: "1st of month, 00:00 UTC",
    note: "Premium-request / AI-credit allotment. The CLI /usage is session-scoped only.",
  },
  cursor: {
    model: "Monthly usage credits",
    reset: "your billing date",
    note: "No CLI command — Settings → Usage. The $-credit pool resets each cycle.",
  },
  vibe: {
    model: "API rate limits",
    reset: "n/a — bound to API key",
    note: "/status fields undocumented; limited by your provider key's rate limits.",
  },
  opencode: {
    model: "API rate limits",
    reset: "n/a — bound to API key",
    note: "`opencode stats` is a shell cmd, not in-TUI. Bounded by your API key.",
  },
  hermes: {
    model: "API rate limits",
    reset: "n/a — bound to API key",
    note: "`hermes insights` (shell). Bounded by the underlying API key's limits.",
  },
  grok: {
    model: "API rate limits",
    reset: "n/a — bound to API key",
    note: "No usage command found in docs. Bounded by your xAI key's rate limits.",
  },
  cline: {
    model: "API rate limits",
    reset: "no window — per API call",
    note: "Live token count sits in the task header; you pay per request, no reset.",
  },
  smallcode: {
    model: "Per-session token budget",
    reset: "per session",
    note: "/budget and /tokens show a session budget, not a provider reset window.",
  },
  openai_compat: {
    model: "API rate limits",
    reset: "n/a — your endpoint",
    note: "Generic passthrough — limits and reset are whatever your endpoint enforces.",
  },
};
const LIMIT_FALLBACK: LimitInfo = {
  model: "API rate limits",
  reset: "n/a — bound to API key",
  note: "Bounded by the underlying provider key's rate limits.",
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

/** One metric cell — fixed two-line body so every card's baselines line up. */
function Stat({ label, value, sub, title }: { label: string; value: string; sub?: string; title?: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--tt-fg-dim)] truncate" title={title}>{label}</div>
      <div className="tabular text-[16px] font-semibold leading-tight text-[var(--tt-fg)] truncate">{value}</div>
      <div className="text-[11px] leading-tight text-[var(--tt-fg-muted)] tabular truncate">{sub || " "}</div>
    </div>
  );
}

function AgentUsageCard({
  agent, stats, overview,
}: { agent: string; stats: WindowStats; overview?: AgentRouteOverview }) {
  const meta = getAgent(agent);
  const Icon = meta.icon;
  const native = NATIVE_COMMAND[agent];
  const limit = LIMIT_INFO[agent] ?? LIMIT_FALLBACK;
  const active = overview?.routes?.interactive?.active;
  const pool = poolText(overview);

  return (
    <Card className="flex flex-col h-full">
      <CardHeader className="mb-3">
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

      {/* Body: metrics (or empty note), grows to fill so the footer pins bottom. */}
      <div className="flex-1">
        {stats.session_count === 0 ? (
          <div className="grid h-full min-h-[52px] place-items-center">
            <p className="text-[12px] text-[var(--tt-fg-dim)]">No sessions in this window.</p>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-3">
              <Stat label="Tokens" value={formatTokens(stats.total)}
                    sub={`${formatTokens(stats.input)} in · ${formatTokens(stats.output)} out`} />
              <Stat label="Cost" title="API list-price equivalent" value={formatCost(stats.cost)}
                    sub={`${stats.session_count} session${stats.session_count === 1 ? "" : "s"}`} />
              <Stat label="Cache" value={stats.cache_hit_pct == null ? "—" : `${stats.cache_hit_pct}%`}
                    sub="hit rate" />
            </div>
            {overview && (
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <span className="text-[10px] uppercase tracking-[0.14em] text-[var(--tt-fg-dim)]">Plan</span>
                <div className="flex flex-wrap items-center justify-end gap-1">
                  <span className="text-[12px] font-medium text-[var(--tt-fg)]">
                    {PLAN_LABEL[overview.plan] ?? overview.plan}
                  </span>
                  {active && (
                    <span className={`rounded px-1.5 py-px text-[10px] font-medium ${CONFIDENCE_STYLE[active.charges === "included" ? "confirmed" : active.charges === "electricity" ? "none" : "partial"]}`}>
                      {CHARGES_LABEL[active.charges]}
                    </span>
                  )}
                  {pool && (
                    <span className="rounded px-1.5 py-px text-[10px] font-medium text-[var(--tt-fg-muted)] bg-[var(--tt-bg-elev)]">
                      {pool} pool
                    </span>
                  )}
                  {active?.no_spillover && (
                    <span className="flex items-center gap-0.5 text-[10px] text-[var(--tt-danger-fg)]">
                      <AlertTriangle size={10} /> no fallback
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Limits & reset — reference metadata, shown for every agent. */}
      <div className="mt-4 pt-3 border-t border-[var(--tt-border)] space-y-1.5">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-[10px] uppercase tracking-[0.14em] text-[var(--tt-fg-dim)] shrink-0">Limits</span>
          <span className="text-[12px] text-[var(--tt-fg-muted)] text-right">{limit.model}</span>
        </div>
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-[10px] uppercase tracking-[0.14em] text-[var(--tt-fg-dim)] shrink-0">Resets</span>
          <span className="text-[12px] text-[var(--tt-fg-muted)] text-right">{limit.reset}</span>
        </div>
        <p className="text-[10.5px] leading-snug text-[var(--tt-fg-dim)]">{limit.note}</p>
      </div>
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
    <div className="px-8 py-8 max-w-[1600px] mx-auto space-y-6 pb-20">
      <PageHeader
        icon={<Gauge size={18} />}
        eyebrow="Cross-agent"
        title="Usage"
        description="What every agent's own /usage, /stats, or /status command would show — Claude Code, Codex, Gemini CLI, and the rest — read from the same local session data TokenTelemetry already scans, in one place instead of switching tools."
      />

      <div className="inline-flex gap-0.5 bg-[var(--tt-sunken)] border border-[var(--tt-border)] rounded-[var(--tt-radius)] p-0.5">
        {WINDOWS.map((w) => (
          <button
            key={w.key}
            type="button"
            onClick={() => setActiveWindow(w.key)}
            className={`px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] rounded-[calc(var(--tt-radius)-2px)] transition-colors cursor-pointer ${
              activeWindow === w.key
                ? "bg-[var(--tt-panel)] text-[var(--tt-fg)] shadow-sm"
                : "text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)]"
            }`}
          >
            {w.label}
          </button>
        ))}
      </div>

      {loading && !data ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-56 w-full" />)}
        </div>
      ) : agentIds.length === 0 ? (
        <EmptyState
          icon={<Gauge size={22} />}
          title="No agents detected yet"
          description="Run a coding agent TokenTelemetry supports and its usage will show up here."
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 auto-rows-fr">
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

      <p className="text-[11px] leading-relaxed text-[var(--tt-fg-dim)] max-w-3xl">
        <span className="font-medium text-[var(--tt-fg-muted)]">On limits &amp; resets:</span>{" "}
        the tokens and cost above are re-counted from your local session files, so they&apos;re always available.
        Your <em>live remaining quota</em> and exact reset countdown live on each provider&apos;s servers — only that
        agent&apos;s own command (Claude&apos;s <code>/usage</code>, Codex&apos;s <code>/status</code>, …) can read them.
        The &ldquo;Limits&rdquo; and &ldquo;Resets&rdquo; lines describe each agent&apos;s reset <em>model</em>, verified
        against provider docs in July 2026; numbers can change, so treat them as the shape of the limit, not a live meter.
      </p>
    </div>
  );
}
