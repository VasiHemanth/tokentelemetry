"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { format } from "date-fns";
import {
  Activity, Clock, TrendingUp, Folders, DollarSign, Cpu, ArrowUpRight, Radio, Terminal,
} from "lucide-react";

import { useResource } from "@/lib/api";
import { AGENTS, getAgent, type AgentKey } from "@/lib/agents";
import SourceBadge from "@/components/SourceBadge";
import { formatTokens, formatCost } from "@/lib/format";
import {
  PageHeader, StatTile, Section, Card, CardHeader, CardTitle, CardEyebrow,
  Table, THead, TBody, TR, TH, TD, AgentBadge, Badge, Button, EmptyState, Skeleton,
} from "@/components/ui";

interface Session {
  id: string;
  agent: string;
  project: string;
  timestamp: string;
  display?: string;
  text?: string;
  tokens?: { input: number; output: number; cached: number; total: number };
  cost?: number;
  /** Hermes-only: cli / telegram / cron / etc. */
  source_subtype?: string;
}

interface AnalyticsResponse {
  by_model?: Record<string, { total: number; session_count: number; agent: string }>;
  pricing_updated?: string;
  total?: { cache_hit_pct: number | null };
}

export default function Home() {
  const pathname = usePathname();
  const sessionsRes = useResource<Session[]>("/sessions", { pollMs: 15_000, initial: [] });
  const agentsRes   = useResource<string[]>("/agents", { pollMs: 30_000, initial: [] });
  const analyticsRes = useResource<AnalyticsResponse>("/analytics", { pollMs: 30_000 });

  const sessions = (sessionsRes.data ?? []).slice().sort((a, b) => {
    const ta = new Date(a.timestamp).getTime();
    const tb = new Date(b.timestamp).getTime();
    return (Number.isFinite(tb) ? tb : 0) - (Number.isFinite(ta) ? ta : 0);
  });
  const availableAgents = agentsRes.data ?? [];
  const byModel = analyticsRes.data?.by_model ?? {};
  const pricingUpdated = analyticsRes.data?.pricing_updated;

  const totalTokens = sessions.reduce((a, s) => a + (s.tokens?.total ?? 0), 0);
  const totalCost   = sessions.reduce((a, s) => a + (s.cost ?? 0), 0);
  const projectCount = new Set(sessions.map((s) => s.project)).size;

  const modelRows = Object.entries(byModel)
    .map(([name, s]) => ({ name, ...s }))
    .sort((a, b) => b.session_count - a.session_count);
  const totalModelSessions = modelRows.reduce((a, r) => a + r.session_count, 0) || 1;

  const loading = sessionsRes.loading;

  return (
    <div className="px-8 py-8 max-w-[1600px] mx-auto space-y-10 pb-20">
      <PageHeader
        eyebrow="Overview"
        title="Dashboard"
        description={
          loading
            ? "Loading telemetry…"
            : `Monitoring ${sessions.length.toLocaleString()} traces across ${availableAgents.length} detected ${availableAgents.length === 1 ? "agent" : "agents"}.`
        }
        icon={<Activity size={20} strokeWidth={2.25} />}
        actions={
          <>
            <Badge variant="success" size="sm" className="h-9 px-2.5">
              <span className="relative flex w-1.5 h-1.5">
                <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-400" />
              </span>
              Live
            </Badge>
            <Link href="/analytics">
              <Button variant="secondary" size="md">
                Analytics <ArrowUpRight size={14} />
              </Button>
            </Link>
          </>
        }
      />

      {/* KPI strip */}
      <Section title="Key metrics">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatTile
            label="Sessions"
            value={loading ? <Skeleton className="h-8 w-20" /> : sessions.length.toLocaleString()}
            icon={<Clock size={16} />}
            accent="var(--tt-brand)"
          />
          <StatTile
            label="Tokens"
            value={loading ? <Skeleton className="h-8 w-20" /> : formatTokens(totalTokens)}
            icon={<TrendingUp size={16} />}
            accent="var(--tt-success)"
          />
          <StatTile
            label="Active Projects"
            value={loading ? <Skeleton className="h-8 w-12" /> : projectCount}
            icon={<Folders size={16} />}
            accent="var(--tt-info)"
          />
          <StatTile
            label="Cost (est.)"
            value={loading ? <Skeleton className="h-8 w-20" /> : formatCost(totalCost)}
            hint={pricingUpdated ? `Rates updated ${pricingUpdated}` : undefined}
            icon={<DollarSign size={16} />}
            accent="var(--tt-warn)"
          />
        </div>
      </Section>

      {/* Connected agents — split into coding vs autonomous */}
      {availableAgents.length > 0 && (() => {
        const AUTONOMOUS = new Set(["hermes"]);
        const coding = availableAgents.filter((k) => !AUTONOMOUS.has(k));
        const autonomous = availableAgents.filter((k) => AUTONOMOUS.has(k));
        const renderCard = (k: string) => {
          const meta = AGENTS[k as AgentKey];
          if (!meta) return null;
          const count = sessions.filter((s) => s.agent === k).length;
          const Icon = meta.icon;
          const inner = (
            <>
              <div
                aria-hidden
                className="pointer-events-none absolute inset-x-0 -top-px h-px"
                style={{ background: `linear-gradient(90deg, transparent, ${meta.hex}66, transparent)` }}
              />
              <div className="flex items-center justify-between">
                <div
                  className="h-7 w-7 grid place-items-center rounded-md"
                  style={{ backgroundColor: `${meta.hex}14`, color: meta.hex }}
                >
                  <Icon size={14} />
                </div>
                <span className="tabular text-[13px] font-semibold text-[var(--tt-fg)]">{count}</span>
              </div>
              <div className="mt-2 text-[11px] uppercase tracking-[0.16em] text-[var(--tt-fg-muted)]">
                {meta.label}
              </div>
            </>
          );
          const className =
            "group relative overflow-hidden rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] p-3 transition-colors hover:border-[var(--tt-border-strong)]";
          // Hermes routes to its dedicated page; other agents stay non-interactive for now.
          if (k === "hermes") {
            return (
              <Link key={k} href="/hermes" className={`${className} cursor-pointer hover:bg-[var(--tt-sunken)]`}>
                {inner}
              </Link>
            );
          }
          return <div key={k} className={className}>{inner}</div>;
        };
        return (
          <>
            {coding.length > 0 && (
              <Section
                title="Connected coding agents"
                description="Detected from local agent runtimes — counts reflect sessions captured."
              >
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-7 gap-3">
                  {coding.map(renderCard)}
                </div>
              </Section>
            )}
            {autonomous.length > 0 && (
              <Section
                title="Connected autonomous agents"
                description="General-purpose agents that run across CLI, messaging, and scheduled jobs."
              >
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-7 gap-3">
                  {autonomous.map(renderCard)}
                </div>
              </Section>
            )}
          </>
        );
      })()}

      {/* Activity + sidebars */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 items-start">
        {/* Recent activity */}
        <Card padding="none" className="xl:col-span-2 overflow-hidden">
          <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-[var(--tt-border)]">
            <div className="flex items-center gap-2">
              <Activity size={14} className="text-[var(--tt-brand)]" />
              <CardTitle className="!text-[13px]">Recent activity</CardTitle>
            </div>
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.18em] text-[var(--tt-fg-dim)]">
              <Radio size={10} className="text-emerald-400" />
              auto-sync 15s
            </div>
          </div>

          {loading ? (
            <ActivityLoading />
          ) : sessions.length === 0 ? (
            <EmptyState
              icon={<Terminal size={20} />}
              title="No agent data yet"
              description="TokenTelemetry watches local agent runtimes for activity. Run Claude Code, Cursor, Copilot, or another supported agent to populate this feed."
            />
          ) : (
            <div className="max-h-[560px] overflow-y-auto">
              <Table>
                <THead>
                  <TR>
                    <TH className="pl-5">Agent</TH>
                    <TH>Project</TH>
                    <TH>Context</TH>
                    <TH className="text-right pr-5">Time</TH>
                  </TR>
                </THead>
                <TBody>
                  {sessions.slice(0, 50).map((s, i) => (
                    <TR key={`${s.agent}-${s.id}-${i}`} interactive>
                      <TD className="pl-5">
                        <Link href={`/sessions/${s.id}?agent=${s.agent}&from=${encodeURIComponent(pathname)}`} className="block">
                          <AgentBadge agent={s.agent} />
                        </Link>
                      </TD>
                      <TD className="font-mono text-[12px] text-[var(--tt-fg-muted)] max-w-[160px] truncate" title={s.agent === "hermes" ? `Hermes source: ${s.source_subtype || "unknown"}` : s.project}>
                        <Link href={`/sessions/${s.id}?agent=${s.agent}&from=${encodeURIComponent(pathname)}`} className="block truncate">
                          {s.agent === "hermes" ? (
                            <SourceBadge source={s.source_subtype} size="xs" />
                          ) : (
                            s.project.split("/").pop()
                          )}
                        </Link>
                      </TD>
                      <TD className="text-[var(--tt-fg)] max-w-[480px] truncate">
                        <Link href={`/sessions/${s.id}?agent=${s.agent}&from=${encodeURIComponent(pathname)}`} className="block truncate">
                          {s.display || s.text || (
                            <span className="italic text-[var(--tt-fg-faint)]">No message content</span>
                          )}
                        </Link>
                      </TD>
                      <TD className="text-right pr-5 tabular text-[11px] text-[var(--tt-fg-muted)] group-hover:text-[var(--tt-brand)] transition-colors">
                        <Link href={`/sessions/${s.id}?agent=${s.agent}&from=${encodeURIComponent(pathname)}`} className="block">
                          <div>{format(new Date(s.timestamp), "HH:mm:ss")}</div>
                          <div className="text-[10px] text-[var(--tt-fg-faint)] uppercase tracking-wider">
                            {format(new Date(s.timestamp), "MMM d")}
                          </div>
                        </Link>
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </div>
          )}
        </Card>

        {/* Right column */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>
                <Activity size={14} className="text-[var(--tt-brand)]" />
                Agent distribution
              </CardTitle>
              <CardEyebrow>{sessions.length} sessions</CardEyebrow>
            </CardHeader>
            {availableAgents.length === 0 ? (
              <div className="text-[12px] text-[var(--tt-fg-dim)] py-6 text-center">
                No agents detected.
              </div>
            ) : (
              <div className="space-y-4">
                {availableAgents
                  .map((k) => ({ k, count: sessions.filter((s) => s.agent === k).length }))
                  .filter((r) => r.count > 0)
                  .sort((a, b) => b.count - a.count)
                  .map(({ k, count }) => {
                    const meta = getAgent(k);
                    const pct = sessions.length ? (count / sessions.length) * 100 : 0;
                    return (
                      <div key={k} className="space-y-1.5">
                        <div className="flex items-center justify-between text-[11px]">
                          <span className="flex items-center gap-2 text-[var(--tt-fg-muted)]">
                            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: meta.hex }} />
                            {meta.label}
                          </span>
                          <span className="tabular text-[var(--tt-fg-dim)]">
                            {count} <span className="text-[var(--tt-fg-faint)]">·</span> {pct.toFixed(0)}%
                          </span>
                        </div>
                        <div className="h-1 rounded-full tt-tint-1 overflow-hidden">
                          <div className="h-full rounded-full transition-[width] duration-500" style={{ width: `${pct}%`, backgroundColor: meta.hex }} />
                        </div>
                      </div>
                    );
                  })}
              </div>
            )}
            <Link
              href="/analytics"
              className="mt-5 pt-4 border-t border-[var(--tt-border)] flex items-center justify-between text-[11px] text-[var(--tt-fg-muted)] hover:text-[var(--tt-brand)] transition-colors"
            >
              <span className="uppercase tracking-[0.18em]">View analytics</span>
              <ArrowUpRight size={12} />
            </Link>
          </Card>

          {modelRows.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>
                  <Cpu size={14} className="text-emerald-400" />
                  Model distribution
                </CardTitle>
                <CardEyebrow>{modelRows.length} models</CardEyebrow>
              </CardHeader>
              <div className="space-y-3.5 max-h-[420px] overflow-y-auto pr-1 -mr-1">
                {modelRows.map((m) => {
                  const meta = getAgent(m.agent);
                  const pct = (m.session_count / totalModelSessions) * 100;
                  return (
                    <div key={m.name} className="space-y-1">
                      <div className="flex items-center justify-between gap-2 text-[11px]">
                        <span className="font-mono text-[var(--tt-fg)] truncate" title={m.name}>{m.name}</span>
                        <span className="tabular text-[var(--tt-fg-dim)] whitespace-nowrap">{m.session_count}</span>
                      </div>
                      <div className="h-[3px] rounded-full tt-tint-1 overflow-hidden">
                        <div className="h-full transition-[width] duration-500" style={{ width: `${pct}%`, backgroundColor: meta.hex }} />
                      </div>
                      <div className="flex items-center justify-between text-[10px] text-[var(--tt-fg-faint)]">
                        <span className="uppercase tracking-[0.16em]" style={{ color: meta.hex }}>{m.agent}</span>
                        <span className="tabular">{(m.total / 1000).toFixed(0)}k tok</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function ActivityLoading() {
  return (
    <div className="p-5 space-y-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="grid grid-cols-[80px_140px_1fr_60px] gap-4 items-center">
          <Skeleton className="h-5 w-16" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-12" />
        </div>
      ))}
    </div>
  );
}

// formatters live in @/lib/format — imported at the top of this file.
