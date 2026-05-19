"use client";

import Link from "next/link";
import { format, formatDistanceToNow } from "date-fns";
import { useMemo } from "react";
import {
  Activity, DollarSign, Cpu, Power, AlertTriangle, Clock, CheckCircle2,
  BookOpen, Brain, ArrowRight,
} from "lucide-react";
import { useResource } from "@/lib/api";
import {
  PageHeader, Card, CardHeader, CardTitle, StatTile, EmptyState,
  Table, THead, TBody, TR, TH, TD, Badge,
} from "@/components/ui";
import SourceBadge from "@/components/SourceBadge";
import HermesIcon from "@/components/icons/HermesIcon";
import { formatTokens, formatCost } from "@/lib/format";

interface GatewayState {
  state: string | null;
  pid: number | null;
  pid_alive: boolean;
  active_agents: number;
  platforms: { name: string; state: string | null; error_code: string | null }[];
  updated_at: string | null;
}

interface CronJob {
  id: string;
  name: string;
  schedule: { kind?: string; value?: string; expr?: string };
  last_run_at: string | null;
  next_run_at: string | null;
  last_status: string | null;
  last_error: string | null;
  at_risk: boolean;
}

interface Overview {
  installed: boolean;
  gateway?: GatewayState;
  cron_jobs?: CronJob[];
}

interface Session {
  id: string;
  agent: string;
  project: string;
  timestamp: string;
  display?: string;
  text?: string;
  tokens?: { input: number; output: number; cached: number; reasoning?: number; total: number };
  cost?: number;
  model?: string;
  source_subtype?: string;
  project_inferred?: boolean;
  cost_anomaly?: boolean;
}

interface Group {
  /** display label */
  label: string;
  /** "project" or "source" — drives the icon/badge shown next to the label */
  kind: "project" | "source";
  /** group key for stable sort */
  key: string;
  sessions: Session[];
  totalCost: number;
}

export default function HermesPage() {
  const sessionsRes = useResource<Session[]>("/sessions", { pollMs: 15_000, initial: [] });
  const overviewRes = useResource<Overview>("/hermes/overview", { pollMs: 30_000 });
  const gateway = overviewRes.data?.gateway;
  const cronJobs = overviewRes.data?.cron_jobs ?? [];
  const hermesSessions = useMemo(
    () => (sessionsRes.data ?? []).filter((s) => s.agent === "hermes"),
    [sessionsRes.data]
  );

  const totalCost = useMemo(
    () => hermesSessions.reduce((acc, s) => acc + (s.cost || 0), 0),
    [hermesSessions]
  );

  const models = useMemo(() => {
    const m = new Map<string, { count: number; cost: number }>();
    for (const s of hermesSessions) {
      const key = s.model || "—";
      const cur = m.get(key) ?? { count: 0, cost: 0 };
      cur.count += 1;
      cur.cost += s.cost || 0;
      m.set(key, cur);
    }
    return [...m.entries()].sort((a, b) => b[1].cost - a[1].cost || b[1].count - a[1].count);
  }, [hermesSessions]);

  const sources = useMemo(() => {
    const m = new Map<string, number>();
    for (const s of hermesSessions) {
      const k = s.source_subtype || "unknown";
      m.set(k, (m.get(k) ?? 0) + 1);
    }
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [hermesSessions]);

  const groups = useMemo<Group[]>(() => {
    const byKey = new Map<string, Group>();
    for (const s of hermesSessions) {
      const hasProject = s.project && s.project !== "unknown";
      const key = hasProject ? `p:${s.project}` : `s:${s.source_subtype || "unknown"}`;
      const label = hasProject ? s.project : (s.source_subtype || "unknown");
      const kind: "project" | "source" = hasProject ? "project" : "source";
      let g = byKey.get(key);
      if (!g) {
        g = { label, kind, key, sessions: [], totalCost: 0 };
        byKey.set(key, g);
      }
      g.sessions.push(s);
      g.totalCost += s.cost || 0;
    }
    // sort: projects first (alphabetical), then sources (by session count desc)
    return [...byKey.values()].sort((a, b) => {
      if (a.kind !== b.kind) return a.kind === "project" ? -1 : 1;
      if (a.kind === "project") return a.label.localeCompare(b.label);
      return b.sessions.length - a.sessions.length;
    });
  }, [hermesSessions]);

  const loading = !sessionsRes.data;

  return (
    <div className="px-8 py-8 max-w-[1600px] mx-auto space-y-10 pb-20">
      <PageHeader
        icon={
          <div className="h-10 w-10 grid place-items-center rounded-[var(--tt-radius)] bg-[#eab308]/10 border border-[#eab308]/30">
            <HermesIcon size={20} className="text-[#eab308]" />
          </div>
        }
        eyebrow="Nous Research"
        title="Hermes Agent"
        description="Autonomous agent observability — sessions, sources, costs across every platform"
        actions={gateway && <GatewayPill g={gateway} />}
      />

      {/* Summary tiles */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile
          icon={<Activity size={14} />}
          label="Sessions"
          value={loading ? "—" : String(hermesSessions.length)}
        />
        <StatTile
          icon={<DollarSign size={14} />}
          label="Total cost"
          value={loading ? "—" : formatCost(totalCost)}
        />
        <StatTile
          icon={<Cpu size={14} />}
          label="Models"
          value={loading ? "—" : String(models.length)}
        />
        <StatTile
          icon={<Activity size={14} />}
          label="Sources"
          value={loading ? "—" : String(sources.length)}
        />
      </div>

      {/* Sub-page navigation tiles */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Link
          href="/hermes/skills"
          className="group flex items-center gap-3 bg-[var(--tt-panel)] border border-[var(--tt-border)] rounded-[var(--tt-radius-lg)] p-4 hover:border-[var(--tt-border-strong)] hover:bg-[var(--tt-sunken)] transition-colors"
        >
          <div className="h-9 w-9 grid place-items-center rounded-md bg-[#eab308]/10 text-[#eab308]">
            <BookOpen size={16} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[13px] font-semibold text-[var(--tt-fg)]">Skills</div>
            <div className="text-[11px] text-[var(--tt-fg-muted)]">Browse loaded skills + categories</div>
          </div>
          <ArrowRight size={14} className="text-[var(--tt-fg-dim)] group-hover:text-[var(--tt-fg)] transition-colors" />
        </Link>
        <Link
          href="/hermes/memory"
          className="group flex items-center gap-3 bg-[var(--tt-panel)] border border-[var(--tt-border)] rounded-[var(--tt-radius-lg)] p-4 hover:border-[var(--tt-border-strong)] hover:bg-[var(--tt-sunken)] transition-colors"
        >
          <div className="h-9 w-9 grid place-items-center rounded-md bg-cyan-500/10 text-cyan-300">
            <Brain size={16} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[13px] font-semibold text-[var(--tt-fg)]">Memory</div>
            <div className="text-[11px] text-[var(--tt-fg-muted)]">Agent facts (MEMORY.md) and user profile (USER.md)</div>
          </div>
          <ArrowRight size={14} className="text-[var(--tt-fg-dim)] group-hover:text-[var(--tt-fg)] transition-colors" />
        </Link>
      </div>

      {/* Empty state */}
      {!loading && hermesSessions.length === 0 && (
        <EmptyState
          title="No Hermes sessions yet"
          description="Run Hermes Agent locally (state.db lives under $HERMES_HOME, or ~/.hermes by default) to see sessions appear here. TokenTelemetry scans every refresh."
        />
      )}

      {/* Sources + models side by side */}
      {!loading && hermesSessions.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Sources</CardTitle>
            </CardHeader>
            <div className="px-5 pb-5 flex flex-wrap gap-2">
              {sources.map(([src, count]) => (
                <div key={src} className="flex items-center gap-2">
                  <SourceBadge source={src} size="sm" />
                  <span className="text-[12px] tabular text-[var(--tt-fg-muted)]">
                    {count}
                  </span>
                </div>
              ))}
            </div>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Models</CardTitle>
            </CardHeader>
            <div className="px-5 pb-5 space-y-2">
              {models.slice(0, 8).map(([m, info]) => (
                <div key={m} className="flex items-center justify-between text-[12px]">
                  <span className="font-mono text-[var(--tt-fg)] truncate max-w-[60%]" title={m}>
                    {m}
                  </span>
                  <span className="tabular text-[var(--tt-fg-muted)]">
                    {info.count} · {formatCost(info.cost)}
                  </span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {/* Cron jobs */}
      {cronJobs.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>
              <span className="flex items-center gap-2">
                <Clock size={14} /> Scheduled jobs
              </span>
            </CardTitle>
            <div className="ml-auto text-[11px] tabular text-[var(--tt-fg-muted)]">
              {cronJobs.filter((j) => j.at_risk).length > 0
                ? `${cronJobs.filter((j) => j.at_risk).length} at risk · ${cronJobs.length} total`
                : `${cronJobs.length} job${cronJobs.length === 1 ? "" : "s"}`}
            </div>
          </CardHeader>
          <Table>
            <THead>
              <TR>
                <TH className="pl-5">Job</TH>
                <TH>Schedule</TH>
                <TH>Last run</TH>
                <TH>Next run</TH>
                <TH className="pr-5">Status</TH>
              </TR>
            </THead>
            <TBody>
              {cronJobs.map((j) => (
                <TR key={j.id}>
                  <TD className="pl-5">
                    <div className="font-mono text-[12px] text-[var(--tt-fg)]">{j.name || j.id}</div>
                    {j.last_error && (
                      <div className="text-[10px] text-[var(--tt-danger-fg)] truncate max-w-[320px]" title={j.last_error}>
                        {j.last_error}
                      </div>
                    )}
                  </TD>
                  <TD className="font-mono text-[11px] text-[var(--tt-fg-muted)]">
                    {j.schedule.expr || j.schedule.value || j.schedule.kind || "—"}
                  </TD>
                  <TD className="text-[11px] text-[var(--tt-fg-muted)] tabular">
                    {j.last_run_at ? formatDistanceToNow(new Date(j.last_run_at), { addSuffix: true }) : "never"}
                  </TD>
                  <TD className="text-[11px] tabular">
                    {j.next_run_at ? (
                      <span className={j.at_risk ? "text-[var(--tt-warn-fg)]" : "text-[var(--tt-fg-muted)]"}>
                        {formatDistanceToNow(new Date(j.next_run_at), { addSuffix: true })}
                      </span>
                    ) : "—"}
                  </TD>
                  <TD className="pr-5">
                    {j.at_risk ? (
                      <Badge variant="warn" size="xs"><AlertTriangle size={9} /> at risk</Badge>
                    ) : j.last_status === "ok" ? (
                      <Badge variant="success" size="xs"><CheckCircle2 size={9} /> ok</Badge>
                    ) : j.last_status === "error" ? (
                      <Badge variant="danger" size="xs"><AlertTriangle size={9} /> error</Badge>
                    ) : (
                      <Badge variant="neutral" size="xs">{j.last_status || "—"}</Badge>
                    )}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </Card>
      )}

      {/* Grouped sessions */}
      {!loading && groups.map((g) => (
        <Card key={g.key}>
          <CardHeader>
            <CardTitle>
              {g.kind === "project" ? (
                <span className="flex items-center gap-2">
                  <span className="font-mono text-[var(--tt-fg)] truncate" title={g.label}>
                    {g.label}
                  </span>
                  <Badge variant="neutral" size="xs">project</Badge>
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <SourceBadge source={g.label} size="sm" />
                  <span className="text-[11px] text-[var(--tt-fg-dim)] font-normal">no project</span>
                </span>
              )}
            </CardTitle>
            <div className="ml-auto text-[11px] tabular text-[var(--tt-fg-muted)]">
              {g.sessions.length} session{g.sessions.length === 1 ? "" : "s"}
              {g.totalCost > 0 && ` · ${formatCost(g.totalCost)}`}
            </div>
          </CardHeader>
          <Table>
            <THead>
              <TR>
                <TH className="pl-5">Source</TH>
                <TH>Model</TH>
                <TH>Message</TH>
                <TH className="text-right">Cost</TH>
                <TH className="text-right pr-5">Time</TH>
              </TR>
            </THead>
            <TBody>
              {g.sessions
                .slice()
                .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
                .map((s) => (
                  <TR key={s.id} interactive>
                    <TD className="pl-5">
                      <Link href={`/sessions/${s.id}?agent=hermes`} className="block">
                        <SourceBadge source={s.source_subtype} size="xs" />
                      </Link>
                    </TD>
                    <TD className="font-mono text-[11px] text-[var(--tt-fg-muted)] max-w-[180px] truncate" title={s.model}>
                      <Link href={`/sessions/${s.id}?agent=hermes`} className="block truncate">
                        {s.model || "—"}
                      </Link>
                    </TD>
                    <TD className="text-[var(--tt-fg)] max-w-[480px] truncate">
                      <Link href={`/sessions/${s.id}?agent=hermes`} className="block truncate">
                        <span className="inline-flex items-center gap-1.5">
                          {s.cost_anomaly && (
                            <span
                              title={`Reasoning tokens (${s.tokens?.reasoning?.toLocaleString() ?? 0}) dominate output (${s.tokens?.output?.toLocaleString() ?? 0}) — possible silent thinking-mode waste`}
                              className="inline-flex items-center gap-0.5 text-[9px] text-[var(--tt-warn-fg)] font-mono uppercase tracking-wider"
                            >
                              <AlertTriangle size={9} /> reasoning
                            </span>
                          )}
                          <span className="truncate">
                            {s.display || s.text || (
                              <span className="italic text-[var(--tt-fg-faint)]">No message content</span>
                            )}
                          </span>
                        </span>
                      </Link>
                    </TD>
                    <TD className="text-right tabular text-[11px] text-[var(--tt-fg-muted)]">
                      <Link href={`/sessions/${s.id}?agent=hermes`} className="block">
                        {s.cost && s.cost > 0 ? formatCost(s.cost) : "—"}
                        {s.tokens?.reasoning && s.tokens.reasoning > 0 ? (
                          <div className="text-[9px] text-[var(--tt-fg-faint)] uppercase tracking-wider">
                            +{formatTokens(s.tokens.reasoning)} reasoning
                          </div>
                        ) : null}
                      </Link>
                    </TD>
                    <TD className="text-right pr-5 tabular text-[11px] text-[var(--tt-fg-muted)]">
                      <Link href={`/sessions/${s.id}?agent=hermes`} className="block">
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
        </Card>
      ))}
    </div>
  );
}

function GatewayPill({ g }: { g: GatewayState }) {
  // Three semantic buckets:
  //   running  = gateway_state≈running AND pid alive
  //   stale    = state says running but pid dead, or unknown state
  //   stopped  = state==stopped/idle/null AND no live pid
  const state = (g.state || "").toLowerCase();
  const running = (state === "running" || state === "ready") && g.pid_alive;
  const stopped = !g.pid_alive && (state === "stopped" || state === "idle" || !state);
  const stale = !running && !stopped;

  const cls = running
    ? "text-emerald-300 bg-emerald-500/10 border-emerald-500/30"
    : stale
    ? "text-amber-300 bg-amber-500/10 border-amber-500/30"
    : "text-zinc-400 bg-zinc-500/10 border-zinc-500/30";
  const label = running ? "GATEWAY RUNNING" : stale ? "GATEWAY STALE" : "GATEWAY STOPPED";
  const platformsHealthy = g.platforms.filter((p) => (p.state || "").toLowerCase() === "connected").length;
  const platformsTotal = g.platforms.length;

  return (
    <div className="flex items-center gap-2">
      <span
        className={`inline-flex items-center gap-1.5 font-mono uppercase tracking-wider rounded border text-[10px] px-2 py-[3px] ${cls}`}
        title={
          g.updated_at
            ? `Updated ${formatDistanceToNow(new Date(g.updated_at), { addSuffix: true })}`
            : "No gateway state file"
        }
      >
        <Power size={11} />
        {label}
      </span>
      {platformsTotal > 0 && (
        <span className="text-[10px] text-[var(--tt-fg-muted)] tabular">
          {platformsHealthy}/{platformsTotal} platform{platformsTotal === 1 ? "" : "s"}
        </span>
      )}
      {g.active_agents > 0 && (
        <span className="text-[10px] text-[var(--tt-fg-muted)] tabular">
          · {g.active_agents} active
        </span>
      )}
    </div>
  );
}
