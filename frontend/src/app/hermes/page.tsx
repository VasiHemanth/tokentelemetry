"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { format, formatDistanceToNow } from "date-fns";
import { useEffect, useMemo, useState } from "react";
import {
  Activity, DollarSign, Cpu, Power, AlertTriangle, Clock, CheckCircle2,
  BookOpen, Brain, ArrowRight, Sparkles, Users, Wrench, Signal, Timer,
  Kanban,
} from "lucide-react";
import { useResource } from "@/lib/api";
import {
  PageHeader, Card, CardHeader, CardTitle, StatTile, EmptyState, Section,
  Table, THead, TBody, TR, TH, TD, Badge,
} from "@/components/ui";
import {
  HermesTelemetry, CostStatus, COST_STATUS_ORDER, COST_STATUS_HINTS,
  COST_STATUS_LABELS, outcomeBucketLabel, outcomeBucketSplit,
} from "@/lib/hermesTelemetry";
import SourceBadge from "@/components/SourceBadge";
import HermesIcon from "@/components/icons/HermesIcon";
import { formatTokens, formatCost } from "@/lib/format";
import { profileColor, profileTint } from "@/lib/profileColor";
import { trackEvent } from "@/lib/telemetry";

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
  hermes_profile?: string;
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
  const pathname = usePathname();
  const sessionsRes = useResource<Session[]>("/sessions", { pollMs: 15_000, initial: [] });
  const overviewRes = useResource<Overview>("/hermes/overview", { pollMs: 30_000 });
  const profilesRes = useResource<{ profiles: { name: string }[] }>("/hermes/profiles", { pollMs: 60_000 });
  const gateway = overviewRes.data?.gateway;
  const cronJobs = overviewRes.data?.cron_jobs ?? [];
  // "all" | "default" | profile name. Scopes the summary tiles, the sources and
  // models cards, and the grouped session tables. The Telemetry section is not
  // profile-scoped: its endpoint always covers every profile.
  const [profileScope, setProfileScope] = useState<string>("all");
  const allHermesSessions = useMemo(
    () => (sessionsRes.data ?? []).filter((s) => s.agent === "hermes"),
    [sessionsRes.data]
  );
  // Pills come from the profiles endpoint (so a zero-session profile still
  // shows) unioned with whatever the sessions carry.
  const profileNames = useMemo(() => {
    const names = new Set<string>((profilesRes.data?.profiles ?? []).map((p) => p.name));
    for (const s of allHermesSessions) names.add(s.hermes_profile || "default");
    names.delete("default");
    return ["default", ...[...names].sort()];
  }, [profilesRes.data, allHermesSessions]);
  const hermesSessions = useMemo(
    () => profileScope === "all"
      ? allHermesSessions
      : allHermesSessions.filter((s) => (s.hermes_profile || "default") === profileScope),
    [allHermesSessions, profileScope]
  );

  // Explicit signal that the Hermes dashboard (the differentiator surface) was
  // opened — fires once per mount, through the proper content-free feature.used
  // channel. The generic page.viewed{route:"hermes"} also fires from
  // TelemetryNotice; this gives Hermes its own filterable event.
  useEffect(() => {
    trackEvent("feature.used", { name: "hermes-dashboard" });
  }, []);

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

      {/* Profile scope — desktop-style switcher; hidden when only the default home exists */}
      {profileNames.length > 1 && (
        <div className="flex items-center gap-1.5 flex-wrap">
          {["all", ...profileNames].map((name) => {
            const selected = profileScope === name;
            const color = profileColor(name);
            const count = name === "all"
              ? allHermesSessions.length
              : allHermesSessions.filter((s) => (s.hermes_profile || "default") === name).length;
            return (
              <button
                key={name}
                onClick={() => setProfileScope(name)}
                className={`inline-flex items-center gap-1.5 font-mono text-[11px] px-2.5 h-7 rounded-full border transition-colors ${
                  selected
                    ? "border-[var(--tt-border-strong)] bg-[var(--tt-sunken)] text-[var(--tt-fg)]"
                    : "border-[var(--tt-border)] text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)]"
                }`}
                style={selected && color ? { borderColor: color } : undefined}
              >
                {color && (
                  <span className="h-2 w-2 rounded-full shrink-0" style={{ background: color }} />
                )}
                {name === "all" ? "All profiles" : name}
                <span className="text-[9px] tabular text-[var(--tt-fg-dim)]">{count}</span>
              </button>
            );
          })}
        </div>
      )}

      {/* Summary tiles */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile
          icon={<Activity size={14} />}
          label="Sessions"
          value={loading ? "—" : String(hermesSessions.length)}
        />
        <StatTile
          icon={<DollarSign size={14} />}
          label="API equiv."
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
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
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
          href="/hermes/tools"
          className="group flex items-center gap-3 bg-[var(--tt-panel)] border border-[var(--tt-border)] rounded-[var(--tt-radius-lg)] p-4 hover:border-[var(--tt-border-strong)] hover:bg-[var(--tt-sunken)] transition-colors"
        >
          <div className="h-9 w-9 grid place-items-center rounded-md bg-orange-500/10 text-orange-500">
            <Wrench size={16} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[13px] font-semibold text-[var(--tt-fg)]">Tools</div>
            <div className="text-[11px] text-[var(--tt-fg-muted)]">Core enabled CLI toolsets</div>
          </div>
          <ArrowRight size={14} className="text-[var(--tt-fg-dim)] group-hover:text-[var(--tt-fg)] transition-colors" />
        </Link>
        <Link
          href="/hermes/profiles"
          className="group flex items-center gap-3 bg-[var(--tt-panel)] border border-[var(--tt-border)] rounded-[var(--tt-radius-lg)] p-4 hover:border-[var(--tt-border-strong)] hover:bg-[var(--tt-sunken)] transition-colors"
        >
          <div className="h-9 w-9 grid place-items-center rounded-md bg-blue-500/10 text-blue-500">
            <Users size={16} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[13px] font-semibold text-[var(--tt-fg)]">Profiles</div>
            <div className="text-[11px] text-[var(--tt-fg-muted)]">Local agent profiles (Agents)</div>
          </div>
          <ArrowRight size={14} className="text-[var(--tt-fg-dim)] group-hover:text-[var(--tt-fg)] transition-colors" />
        </Link>
        <Link
          href="/hermes/soul"
          className="group flex items-center gap-3 bg-[var(--tt-panel)] border border-[var(--tt-border)] rounded-[var(--tt-radius-lg)] p-4 hover:border-[var(--tt-border-strong)] hover:bg-[var(--tt-sunken)] transition-colors"
        >
          <div className="h-9 w-9 grid place-items-center rounded-md bg-fuchsia-500/10 text-fuchsia-500">
            <Sparkles size={16} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[13px] font-semibold text-[var(--tt-fg)]">Soul</div>
            <div className="text-[11px] text-[var(--tt-fg-muted)]">Core persona (SOUL.md)</div>
          </div>
          <ArrowRight size={14} className="text-[var(--tt-fg-dim)] group-hover:text-[var(--tt-fg)] transition-colors" />
        </Link>
        <Link
          href="/hermes/memory"
          className="group flex items-center gap-3 bg-[var(--tt-panel)] border border-[var(--tt-border)] rounded-[var(--tt-radius-lg)] p-4 hover:border-[var(--tt-border-strong)] hover:bg-[var(--tt-sunken)] transition-colors"
        >
          <div className="h-9 w-9 grid place-items-center rounded-md bg-cyan-500/10 text-cyan-500">
            <Brain size={16} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[13px] font-semibold text-[var(--tt-fg)]">Memory</div>
            <div className="text-[11px] text-[var(--tt-fg-muted)]">Agent facts (MEMORY.md)</div>
          </div>
          <ArrowRight size={14} className="text-[var(--tt-fg-dim)] group-hover:text-[var(--tt-fg)] transition-colors" />
        </Link>
        <Link
          href="/hermes/gateway"
          className="group flex items-center gap-3 bg-[var(--tt-panel)] border border-[var(--tt-border)] rounded-[var(--tt-radius-lg)] p-4 hover:border-[var(--tt-border-strong)] hover:bg-[var(--tt-sunken)] transition-colors"
        >
          <div className="h-9 w-9 grid place-items-center rounded-md bg-emerald-500/10 text-emerald-500">
            <Signal size={16} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[13px] font-semibold text-[var(--tt-fg)]">Gateway</div>
            <div className="text-[11px] text-[var(--tt-fg-muted)]">Live platform connections</div>
          </div>
          <ArrowRight size={14} className="text-[var(--tt-fg-dim)] group-hover:text-[var(--tt-fg)] transition-colors" />
        </Link>
        <Link
          href="/hermes/kanban"
          className="group flex items-center gap-3 bg-[var(--tt-panel)] border border-[var(--tt-border)] rounded-[var(--tt-radius-lg)] p-4 hover:border-[var(--tt-border-strong)] hover:bg-[var(--tt-sunken)] transition-colors"
        >
          <div className="h-9 w-9 grid place-items-center rounded-md bg-rose-500/10 text-rose-500">
            <Kanban size={16} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[13px] font-semibold text-[var(--tt-fg)]">Kanban</div>
            <div className="text-[11px] text-[var(--tt-fg-muted)]">Swarm board with per-task cost</div>
          </div>
          <ArrowRight size={14} className="text-[var(--tt-fg-dim)] group-hover:text-[var(--tt-fg)] transition-colors" />
        </Link>
        <Link
          href="/hermes/schedules"
          className="group flex items-center gap-3 bg-[var(--tt-panel)] border border-[var(--tt-border)] rounded-[var(--tt-radius-lg)] p-4 hover:border-[var(--tt-border-strong)] hover:bg-[var(--tt-sunken)] transition-colors"
        >
          <div className="h-9 w-9 grid place-items-center rounded-md bg-indigo-500/10 text-indigo-500">
            <Timer size={16} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[13px] font-semibold text-[var(--tt-fg)]">Schedules</div>
            <div className="text-[11px] text-[var(--tt-fg-muted)]">Background cron jobs</div>
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

      {/* Telemetry: outcomes, cost provenance, latency, tool reliability */}
      <TelemetrySection />

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
                <TH className="text-right">API equiv.</TH>
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
                      <Link href={`/sessions/${s.id}?agent=hermes&from=${encodeURIComponent(pathname)}`} className="block">
                        <span className="inline-flex items-center gap-1.5">
                          <SourceBadge source={s.source_subtype} size="xs" />
                          {s.hermes_profile && profileScope === "all" && (
                            <span
                              className="inline-flex items-center gap-1 font-mono text-[9px] px-1.5 h-4 rounded-full border"
                              style={{
                                color: profileColor(s.hermes_profile) ?? undefined,
                                borderColor: profileColor(s.hermes_profile) ?? undefined,
                                background: profileTint(s.hermes_profile) ?? undefined,
                              }}
                              title={`Profile: ${s.hermes_profile}`}
                            >
                              {s.hermes_profile}
                            </span>
                          )}
                        </span>
                      </Link>
                    </TD>
                    <TD className="font-mono text-[11px] text-[var(--tt-fg-muted)] max-w-[180px] truncate" title={s.model}>
                      <Link href={`/sessions/${s.id}?agent=hermes&from=${encodeURIComponent(pathname)}`} className="block truncate">
                        {s.model || "—"}
                      </Link>
                    </TD>
                    <TD className="text-[var(--tt-fg)] max-w-[480px] truncate">
                      <Link href={`/sessions/${s.id}?agent=hermes&from=${encodeURIComponent(pathname)}`} className="block truncate">
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
                      <Link href={`/sessions/${s.id}?agent=hermes&from=${encodeURIComponent(pathname)}`} className="block">
                        {s.cost && s.cost > 0 ? formatCost(s.cost) : "—"}
                        {s.tokens?.reasoning && s.tokens.reasoning > 0 ? (
                          <div className="text-[9px] text-[var(--tt-fg-faint)] uppercase tracking-wider">
                            +{formatTokens(s.tokens.reasoning)} reasoning
                          </div>
                        ) : null}
                      </Link>
                    </TD>
                    <TD className="text-right pr-5 tabular text-[11px] text-[var(--tt-fg-muted)]">
                      <Link href={`/sessions/${s.id}?agent=hermes&from=${encodeURIComponent(pathname)}`} className="block">
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

/** Telemetry from /hermes/telemetry. The endpoint is not profile-scoped, so
 *  this section always covers every profile regardless of the pill selection.
 *  Renders nothing while loading, on error (older backend without the route),
 *  or when Hermes isn't installed. The page's own empty state covers that. */
function TelemetrySection() {
  const res = useResource<HermesTelemetry>("/hermes/telemetry", { pollMs: 60_000 });
  const t = res.data;
  if (!t || !t.available) return null;

  const { outcomes, cost, latency, tools, log_coverage } = t;
  const latencySessions = latency.captured_sessions + latency.uncaptured_sessions;
  // Sessions in the unknown bucket split two ways: ones whose raw end_reason
  // has no mapping yet (listed by name) and ones where Hermes recorded no
  // end_reason at all (no raw string to list, so they need saying separately).
  const unknownTotal = outcomes.buckets.find((b) => b.outcome === "unknown")?.count ?? 0;
  const unknownNamed = outcomes.unknown_raw.reduce((acc, u) => acc + u.count, 0);
  const unknownBlank = Math.max(0, unknownTotal - unknownNamed);
  // Statuses that carry a real API-equivalent figure. `zero-marginal` and
  // `unpriced` both sit at $0 for different reasons and neither belongs here.
  const PRICED: CostStatus[] = ["provider-reported", "provider-estimated", "tt-computed"];
  const pricedSessions = PRICED.reduce((acc, k) => acc + (cost.confidence[k] ?? 0), 0);
  const zeroMarginalSessions = cost.confidence["zero-marginal"] ?? 0;
  // Nothing could be priced: total_usd is 0 because there was nothing to price,
  // not because the sessions cost nothing.
  const nothingPriced = pricedSessions === 0 && zeroMarginalSessions === 0;
  // Everything priceable priced out at $0 because the models are local or
  // subscription-covered. total_usd is 0 and that IS the answer, but it is an
  // answer about marginal cost, not about what the tokens would cost at API
  // rates. Printing "API equiv. $0.00" here would be the false claim.
  const allZeroMarginal = pricedSessions === 0 && zeroMarginalSessions > 0;
  // Slice of total_usd covered by a flat subscription. Older backends don't send
  // the field, so treat a missing value as 0 and drop the line rather than
  // rendering "$NaN". The share is only meaningful against a non-zero total.
  const includedUsd = cost.subscription_included_usd ?? 0;
  const includedPct = cost.total_usd > 0 ? (includedUsd / cost.total_usd) * 100 : null;
  // Same reason as subscription_included_usd above: a dev running this build
  // against an older backend gets no breakdowns, and an undefined .length here
  // would white-screen the page instead of dropping two panels.
  const bySource = outcomes.by_source ?? [];
  const byModel = outcomes.by_model ?? [];
  // by_model is capped at the 10 largest, so it can sum to less than
  // session_count. Say so rather than letting the numbers quietly not add up.
  const modelsTotal = outcomes.models_total ?? byModel.length;
  const modelsHidden = Math.max(0, modelsTotal - byModel.length);
  const latencyStats = [
    ["avg", latency.avg_s],
    ["p50", latency.p50_s],
    ["p95", latency.p95_s],
  ] as const;

  return (
    <Section
      title="Telemetry"
      description="Outcomes, cost provenance, latency and tool reliability across every Hermes profile."
    >
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Outcomes */}
        <Card>
          <CardHeader>
            <CardTitle>Session outcomes</CardTitle>
            <div className="ml-auto text-[11px] tabular text-[var(--tt-fg-muted)]">
              {(outcomes.completion_rate * 100).toFixed(1)}% completed · {t.session_count} sessions
            </div>
          </CardHeader>
          <div className="px-5 pb-5 space-y-2">
            {outcomes.buckets.map((b) => (
              <div key={b.outcome} className="flex items-center justify-between text-[12px]">
                <span className="text-[var(--tt-fg)]">{outcomeBucketLabel(b.outcome)}</span>
                <span className="tabular text-[var(--tt-fg-muted)]">
                  {b.count} · {b.pct.toFixed(1)}%
                </span>
              </div>
            ))}
            {outcomes.buckets.some((b) => b.outcome === "continued") && (
              <p className="text-[10px] text-[var(--tt-fg-dim)] pt-1 leading-snug">
                Continued means the session handed off to a child through compression, a branch, or
                a resume. That is neither a completion nor a failure, so it is left out of the
                completed share above.
              </p>
            )}
            {(outcomes.unknown_raw.length > 0 || unknownBlank > 0) && (
              <div className="pt-2 space-y-1 border-t border-[var(--tt-border)]">
                {outcomes.unknown_raw.map((u) => (
                  <div key={u.raw} className="flex items-center justify-between text-[11px]">
                    <span className="font-mono text-[var(--tt-fg-muted)] truncate max-w-[70%]" title={u.raw}>
                      unknown: {u.raw}
                    </span>
                    <span className="tabular text-[var(--tt-fg-dim)]">({u.count})</span>
                  </div>
                ))}
                {unknownBlank > 0 && (
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="text-[var(--tt-fg-muted)]">no end_reason recorded</span>
                    <span className="tabular text-[var(--tt-fg-dim)]">({unknownBlank})</span>
                  </div>
                )}
                <p className="text-[10px] text-[var(--tt-fg-dim)] pt-1 leading-snug">
                  {outcomes.unknown_raw.length > 0
                    ? "Values Hermes reports that TokenTelemetry has no mapping for. They stay unknown instead of counting as completed."
                    : "Hermes left these sessions without an end_reason, so there is nothing to classify. They stay unknown instead of counting as completed."}
                </p>
              </div>
            )}
            {bySource.length > 0 && (
              <OutcomeBreakdown
                title="By source"
                rows={bySource.map((r) => ({ key: r.source, total: r.total, buckets: r.buckets }))}
              />
            )}
            {byModel.length > 0 && (
              <OutcomeBreakdown
                title="By model"
                rows={byModel.map((r) => ({ key: r.model, total: r.total, buckets: r.buckets }))}
                note={
                  modelsHidden > 0
                    ? `Top ${byModel.length} of ${modelsTotal} models. ${modelsHidden} smaller model${modelsHidden === 1 ? "" : "s"} not shown, so these rows sum to less than ${t.session_count}.`
                    : undefined
                }
              />
            )}
          </div>
        </Card>

        {/* Cost provenance */}
        <Card>
          <CardHeader>
            <CardTitle>Cost confidence</CardTitle>
            <div className="ml-auto flex items-center gap-1.5 text-[11px] tabular text-[var(--tt-fg-muted)]">
              {/* Same labels the session pill uses. "API equiv." is what the
                  tokens would cost at API rates, which is not what the user was
                  billed for subscription-included sessions. When every priced
                  session is zero-marginal the total is a statement about
                  marginal cost instead, so the label says that. */}
              <span
                className="text-[10px] font-medium text-[var(--tt-fg-dim)] uppercase tracking-[0.14em]"
                title={allZeroMarginal ? COST_STATUS_HINTS["zero-marginal"] : undefined}
              >
                {allZeroMarginal ? "Marginal cost" : "API equiv."}
              </span>
              {/* formatCost renders 0 as "$0.00", which reads as "these sessions
                  were free". When nothing could be priced there is no total to
                  show, so say that instead of printing a zero. */}
              {nothingPriced ? (
                <span className="text-[var(--tt-fg-dim)]">not captured</span>
              ) : allZeroMarginal ? (
                formatCost(0)
              ) : (
                formatCost(cost.total_usd)
              )}
            </div>
          </CardHeader>
          <div className="px-5 pb-5 space-y-2">
            {COST_STATUS_ORDER.map((k) => {
              const n = cost.confidence[k] ?? 0;
              const usd = cost.usd_by_confidence[k] ?? 0;
              return (
                <div key={k} className="flex items-center justify-between text-[12px]">
                  {/* Readable label, not the wire key: a `title` tooltip does
                      not exist on touch devices, so the jargon must not be the
                      only discoverable text. */}
                  <span className="text-[11px] text-[var(--tt-fg)]" title={COST_STATUS_HINTS[k]}>
                    {COST_STATUS_LABELS[k]}
                  </span>
                  <span className="tabular text-[var(--tt-fg-muted)]">
                    {n} session{n === 1 ? "" : "s"} ·{" "}
                    {k === "unpriced" ? (
                      <span className="text-[var(--tt-fg-dim)]">not captured</span>
                    ) : (
                      formatCost(usd)
                    )}
                  </span>
                </div>
              );
            })}
            {/* Session-count gate, not a dollar gate. Zero-marginal sessions
                contribute $0 to every total on this card, so gating their
                explanation on dollars suppressed it exactly when the zeros
                needed explaining. */}
            {zeroMarginalSessions > 0 && (
              <p className="text-[10px] text-[var(--tt-fg-dim)] pt-1 leading-snug">
                {zeroMarginalSessions} session{zeroMarginalSessions === 1 ? "" : "s"} ran on a local
                model or a model covered by a subscription you already pay for. Their marginal cost
                is {formatCost(0)}, which is an answer, not a missing number. What the same tokens
                would cost at API rates is not counted in the total above.
              </p>
            )}
            {/* Prose, not another row: this is a slice of the total above, and
                another justify-between row would read as a bucket that sums
                with the rest. Kept on its own dollar gate because it describes
                a share of a non-zero total, unlike the line above. */}
            {includedUsd > 0 && (
              <p className="text-[10px] text-[var(--tt-fg-dim)] pt-1 leading-snug">
                Of that total, {formatCost(includedUsd)}
                {includedPct == null ? "" : ` (${includedPct.toFixed(1)}%)`} came from sessions
                Hermes marked subscription-included, so it carries no marginal cost.
              </p>
            )}
            <p className="text-[10px] text-[var(--tt-fg-dim)] pt-1 leading-snug">
              Reported by Hermes means Hermes returned the number itself; priced by TokenTelemetry
              means the tokens were priced locally from public rates.
            </p>
          </div>
        </Card>

        {/* Latency */}
        <Card>
          <CardHeader>
            <CardTitle>Latency</CardTitle>
            <div className="ml-auto text-[11px] tabular text-[var(--tt-fg-muted)]">
              {latency.api_calls.toLocaleString()} API call{latency.api_calls === 1 ? "" : "s"}
            </div>
          </CardHeader>
          <div className="px-5 pb-5 space-y-3">
            <div className="grid grid-cols-3 gap-2">
              {latencyStats.map(([label, v]) => (
                <div
                  key={label}
                  className="bg-[var(--tt-sunken)] border border-[var(--tt-border)] rounded-[var(--tt-radius)] px-3 py-2"
                >
                  <div className="text-[9px] uppercase tracking-[0.18em] text-[var(--tt-fg-dim)]">{label}</div>
                  {v == null ? (
                    <div className="text-[11px] text-[var(--tt-fg-dim)]">not captured</div>
                  ) : (
                    <div className="text-[14px] font-mono tabular text-[var(--tt-fg)]">{v}s</div>
                  )}
                </div>
              ))}
            </div>
            <div className="text-[11px] text-[var(--tt-fg-muted)]">
              Captured for {latency.captured_sessions} of {latencySessions} session
              {latencySessions === 1 ? "" : "s"}. Hermes only writes API-call timings to its
              rotating log, so older sessions lose them.
            </div>
            {latency.by_model.length > 0 && (
              <div className="space-y-1 pt-1 border-t border-[var(--tt-border)]">
                {latency.by_model.slice(0, 4).map((m) => (
                  <div key={m.model} className="flex items-center justify-between text-[11px] pt-1">
                    <span className="font-mono text-[var(--tt-fg-muted)] truncate max-w-[50%]" title={m.model}>
                      {m.model}
                    </span>
                    <span className="tabular text-[var(--tt-fg-dim)]">
                      {m.calls} · avg {m.avg_s == null ? "not captured" : `${m.avg_s}s`}
                      {m.p95_s == null ? "" : ` · p95 ${m.p95_s}s`}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Card>

        {/* Tools */}
        <Card>
          <CardHeader>
            <CardTitle>Tools</CardTitle>
          </CardHeader>
          <div className="px-5 pb-5 space-y-3">
            {!tools.captured ? (
              <div className="text-[12px] text-[var(--tt-fg-dim)]">
                Tool calls not captured. No tool lines were found in the Hermes logs.
              </div>
            ) : (
              <>
                {tools.top_by_calls.length > 0 && (
                  <div className="space-y-1">
                    <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--tt-fg-dim)]">
                      Most used
                    </div>
                    {tools.top_by_calls.map((row) => (
                      <div key={row.tool} className="flex items-center justify-between text-[12px]">
                        <span className="font-mono text-[var(--tt-fg)] truncate max-w-[50%]" title={row.tool}>
                          {row.tool}
                        </span>
                        <span className="tabular text-[var(--tt-fg-muted)]">
                          {row.calls} call{row.calls === 1 ? "" : "s"} ·{" "}
                          {row.avg_duration_s == null ? "duration not captured" : `${row.avg_duration_s}s avg`}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {/* The backend only lists tools that actually failed, so an empty
                    list means no failures were found, not that failures went
                    unread. Say which, or the panel disappears without a word. */}
                <div className="space-y-1 pt-2 border-t border-[var(--tt-border)]">
                  <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--tt-fg-dim)]">
                    Highest failure rate
                  </div>
                  {tools.top_by_failure_rate.length === 0 ? (
                    <div className="text-[12px] text-[var(--tt-fg-muted)]">
                      No failures recorded for tools with at least 3 calls.
                    </div>
                  ) : (
                    <>
                      {tools.top_by_failure_rate.map((row) => (
                        <div key={row.tool} className="flex items-center justify-between text-[12px]">
                          <span className="font-mono text-[var(--tt-fg)] truncate max-w-[50%]" title={row.tool}>
                            {row.tool}
                          </span>
                          <span className="tabular text-[var(--tt-fg-muted)]">
                            {(row.failure_rate * 100).toFixed(1)}% of {row.calls} call
                            {row.calls === 1 ? "" : "s"}
                          </span>
                        </div>
                      ))}
                      <p className="text-[10px] text-[var(--tt-fg-dim)] pt-1 leading-snug">
                        Tools with at least 3 calls only.
                      </p>
                    </>
                  )}
                </div>
              </>
            )}
          </div>
        </Card>
      </div>

      <div className="text-[10px] text-[var(--tt-fg-dim)] px-0.5 leading-snug">
        {log_coverage.files_read.length > 0
          ? `Read from ${log_coverage.files_read.join(", ")}.`
          : "No Hermes log files were readable."}{" "}
        {log_coverage.sessions_with_log} of {log_coverage.sessions_total} sessions have log lines.
      </div>
    </Section>
  );
}

/** Outcome split for one dimension (source or model). Rows carry the total plus
 *  the bucket breakdown, so a source that never completes is visible instead of
 *  being averaged into the page-wide completion rate. Unknown buckets are shown
 *  like any other; the raw end_reason strings stay in the list above. */
function OutcomeBreakdown({
  title, rows, note,
}: {
  title: string;
  rows: { key: string; total: number; buckets: Record<string, number> }[];
  note?: string;
}) {
  return (
    <div className="pt-2 space-y-1 border-t border-[var(--tt-border)]">
      <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--tt-fg-dim)]">
        {title}
      </div>
      {rows.map((r) => (
        <div key={r.key} className="flex items-baseline justify-between gap-3 text-[11px]">
          <span className="font-mono text-[var(--tt-fg-muted)] truncate max-w-[45%]" title={r.key}>
            {r.key}
          </span>
          <span className="tabular text-[var(--tt-fg-dim)] text-right">
            {r.total} · {outcomeBucketSplit(r.buckets)}
          </span>
        </div>
      ))}
      {note && <p className="text-[10px] text-[var(--tt-fg-dim)] pt-1 leading-snug">{note}</p>}
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
