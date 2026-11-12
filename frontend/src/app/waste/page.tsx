"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { format } from "date-fns";
import {
  ShieldAlert, Info, Loader2, SearchCheck,
} from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";

import { cn } from "@/lib/cn";
import { useResource } from "@/lib/api";
import { getAgent } from "@/lib/agents";
import { AgentLogo } from "@/components/icons/AgentLogo";
import { useTheme } from "@/components/ThemeProvider";
import { formatCost } from "@/lib/format";
import { projectBasename } from "@/lib/paths";
import {
  FLAG_INFO, WASTE_FLAGS, COLUMN_CAPABILITY, thresholdLines,
  type WasteResponse, type WasteFlag, type WasteAgentRow,
} from "@/lib/waste";
import {
  PageHeader, StatTile, Section, Card, CardHeader, CardTitle,
  Table, THead, TBody, TR, TH, TD, AgentBadge, Badge, EmptyState, Skeleton,
} from "@/components/ui";

type RangeKey = "7d" | "30d" | "90d" | "month" | "year" | "all" | "custom";
const PRESETS: { key: RangeKey; label: string }[] = [
  { key: "7d", label: "7d" },
  { key: "30d", label: "30d" },
  { key: "90d", label: "90d" },
  { key: "month", label: "Month" },
  { key: "year", label: "Year" },
  { key: "all", label: "All" },
];

// Local YYYY-MM-DD, matching the backend's local-day keys.
function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function presetBounds(key: RangeKey): { from: string | null; to: string | null } {
  const now = new Date();
  const to = ymd(now);
  if (key === "all") return { from: null, to: null };
  if (key === "month") return { from: ymd(new Date(now.getFullYear(), now.getMonth(), 1)), to };
  if (key === "year") return { from: ymd(new Date(now.getFullYear(), 0, 1)), to };
  const days = key === "7d" ? 7 : key === "30d" ? 30 : 90;
  const f = new Date(now);
  f.setDate(f.getDate() - (days - 1));
  return { from: ymd(f), to };
}

function useChartTheme() {
  const { theme } = useTheme();
  const isDark = theme === "dark";
  return {
    axisStroke: isDark ? "rgba(255,255,255,0.18)" : "rgba(15,23,42,0.32)",
    tickFill: isDark ? "rgba(255,255,255,0.55)" : "rgba(15,23,42,0.65)",
    grid: isDark ? "rgba(255,255,255,0.05)" : "rgba(15,23,42,0.07)",
    tooltipStyle: {
      backgroundColor: "var(--tt-overlay)",
      border: "1px solid var(--tt-border-strong)",
      borderRadius: "10px",
      padding: "8px 10px",
    },
    tooltipItem: { fontSize: "calc(11px * var(--tt-text-scale))", color: "var(--tt-fg)" },
    tooltipLabel: { fontSize: "calc(10px * var(--tt-text-scale))", color: "var(--tt-fg-dim)" },
  };
}

const NA = "n/a";
const num = (v: number | null | undefined) => (v == null ? NA : v.toLocaleString());
const pct = (r: number | null | undefined) => (r == null ? NA : `${(r * 100).toFixed(1)}%`);

const NOT_RECORDED_TITLE = "This agent's logs do not include this data.";

function NotRecorded() {
  return (
    <span className="text-[11px] italic text-[var(--tt-fg-faint)]" title={NOT_RECORDED_TITLE}>
      not recorded
    </span>
  );
}

// One cell of the by-agent table. Shows "not recorded" when the agent's logs
// lack the data (capability false, or the backend sent null). Never 0.
function CapCell({ row, col, render }: {
  row: WasteAgentRow;
  col: keyof typeof COLUMN_CAPABILITY;
  render: (v: number) => string;
}) {
  const v = row[col];
  if (!row.capabilities[COLUMN_CAPABILITY[col]] || v == null) {
    return <TD className="text-right"><NotRecorded /></TD>;
  }
  return <TD className="text-right tabular">{render(v)}</TD>;
}

export default function WastePage() {
  const pathname = usePathname();
  const ct = useChartTheme();
  const [range, setRange] = useState<RangeKey>("30d");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  const [selAgents, setSelAgents] = useState<string[]>([]);
  const [flagFilter, setFlagFilter] = useState<WasteFlag | "all">("all");

  const queryPath = useMemo(() => {
    const p = new URLSearchParams();
    let from: string | null, to: string | null;
    if (range === "custom") { from = customFrom || null; to = customTo || null; }
    else ({ from, to } = presetBounds(range));
    if (from) p.set("from", from);
    if (to) p.set("to", to);
    selAgents.forEach(a => p.append("agents", a));
    const qs = p.toString();
    return qs ? `/waste?${qs}` : "/waste";
  }, [range, customFrom, customTo, selAgents]);

  // The backend scan is expensive, so poll slowly.
  const { data, loading } = useResource<WasteResponse>(queryPath, { pollMs: 180_000 });
  const agentOptions = useResource<string[]>("/agents").data ?? [];

  const toggle = (a: string) =>
    setSelAgents(l => (l.includes(a) ? l.filter(x => x !== a) : [...l, a]));

  const flagChart = useMemo(
    () => (data?.by_flag ?? []).map(f => ({
      flag: f.flag, name: FLAG_INFO[f.flag]?.label ?? f.flag, sessions: f.sessions, cost: f.cost,
    })),
    [data],
  );

  const shownSessions = useMemo(() => {
    const rows = data?.sessions ?? [];
    return flagFilter === "all" ? rows : rows.filter(s => s.flags.includes(flagFilter));
  }, [data, flagFilter]);

  const AXIS = {
    stroke: ct.axisStroke, fontSize: "calc(10px * var(--tt-text-scale))",
    tickLine: false, axisLine: false, tick: { fill: ct.tickFill },
  } as const;

  const toolbar = (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-3 -mt-4">
      <div className="flex items-center gap-2">
        <span className="text-[10px] uppercase tracking-[0.16em] text-[var(--tt-fg-dim)]">Range</span>
        <div className="flex gap-0.5 bg-[var(--tt-sunken)] border border-[var(--tt-border)] rounded-[var(--tt-radius)] p-0.5">
          {PRESETS.map(r => (
            <button
              key={r.key}
              onClick={() => setRange(r.key)}
              className={cn(
                "px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] rounded-[calc(var(--tt-radius)-2px)] transition-colors",
                range === r.key
                  ? "bg-[var(--tt-panel)] text-[var(--tt-fg)] shadow-sm"
                  : "text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)]",
              )}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <span className="text-[10px] uppercase tracking-[0.16em] text-[var(--tt-fg-dim)]">Custom</span>
        <input
          type="date" value={customFrom}
          onChange={e => { setCustomFrom(e.target.value); setRange("custom"); }}
          className="bg-[var(--tt-sunken)] border border-[var(--tt-border)] rounded-[var(--tt-radius)] px-2 py-1 text-[11px] text-[var(--tt-fg)]"
        />
        <span className="text-[var(--tt-fg-dim)] text-[11px]">to</span>
        <input
          type="date" value={customTo}
          onChange={e => { setCustomTo(e.target.value); setRange("custom"); }}
          className="bg-[var(--tt-sunken)] border border-[var(--tt-border)] rounded-[var(--tt-radius)] px-2 py-1 text-[11px] text-[var(--tt-fg)]"
        />
      </div>

      {agentOptions.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-[10px] uppercase tracking-[0.16em] text-[var(--tt-fg-dim)]">Agents</span>
          {agentOptions.map(a => (
            <button
              key={a}
              onClick={() => toggle(a)}
              className={cn(
                "px-2 py-0.5 text-[10px] font-medium rounded-full border transition-colors",
                selAgents.includes(a)
                  ? "border-[var(--tt-brand)] text-[var(--tt-fg)] bg-[var(--tt-brand)]/10"
                  : "border-[var(--tt-border)] text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)]",
              )}
            >
              <AgentLogo agent={a} size={11} />
              {getAgent(a).label}
            </button>
          ))}
          {selAgents.length > 0 && (
            <button onClick={() => setSelAgents([])} className="text-[10px] text-[var(--tt-fg-dim)] underline ml-1">clear</button>
          )}
        </div>
      )}
    </div>
  );

  const header = (
    <PageHeader
      eyebrow="Waste"
      title="Waste"
      description="Sessions where tool failures, retries, repeated reads or a missing result suggest spend that did not move work forward."
      icon={<ShieldAlert size={20} strokeWidth={2.25} />}
    />
  );

  if (!data) {
    return (
      <div className="px-8 py-8 max-w-[1600px] mx-auto space-y-10 pb-20">
        {header}
        {toolbar}
        {loading ? (
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-24" />)}
          </div>
        ) : (
          <EmptyState
            icon={<Info size={20} />}
            title="Could not load waste data"
            description="The backend did not return a result. It will retry automatically."
          />
        )}
      </div>
    );
  }

  const sm = data.summary;
  const flaggedShare = sm.total_cost > 0 ? `${((sm.flagged_cost / sm.total_cost) * 100).toFixed(1)}% of ${formatCost(sm.total_cost)}` : "no spend in range";

  return (
    <div className="px-8 py-8 max-w-[1600px] mx-auto space-y-10 pb-20">
      {header}
      {toolbar}

      {sm.sessions === 0 ? (
        <EmptyState
          icon={<SearchCheck size={20} />}
          title="No sessions in this range"
          description="Widen the date range or clear the agent filter."
        />
      ) : sm.analysed === 0 ? (
        <EmptyState
          icon={<Loader2 size={20} className="animate-spin" />}
          title="Analysing sessions"
          description={`${sm.sessions.toLocaleString()} sessions found. They are being analysed in the background, newest first. Results appear here as they finish.`}
        />
      ) : (
        <>
          <p className="text-[12px] text-[var(--tt-fg-muted)] -mt-4" role="status">
            <span className="tabular text-[var(--tt-fg)]">{sm.analysed.toLocaleString()}</span> of{" "}
            <span className="tabular text-[var(--tt-fg)]">{sm.sessions.toLocaleString()}</span> sessions analysed.
            {sm.pending > 0 && ` The remaining ${sm.pending.toLocaleString()} are being analysed in the background.`}
            {sm.failed > 0 && ` ${sm.failed.toLocaleString()} could not be read and have no signals.`}
          </p>

          <Section title="Overview" description="Totals for the selected range and agents.">
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
              <StatTile label="Flagged spend" value={formatCost(sm.flagged_cost)} hint={flaggedShare} accent="var(--tt-brand)" />
              <StatTile label="Flagged sessions" value={sm.flagged_sessions.toLocaleString()} hint={`of ${sm.sessions.toLocaleString()} sessions`} />
              <StatTile label="Tool failure rate" value={pct(sm.failure_rate)} hint={sm.failure_rate == null ? "No agent in range records tool errors" : `${sm.tool_errors.toLocaleString()} failed calls, measured on agents that record errors`} />
              <StatTile label="Retry calls" value={num(sm.retry_calls)} hint="Identical calls repeated in a row" />
              <StatTile label="Repeated reads" value={num(sm.reread_calls)} hint="Files read again in the same session" />
              <StatTile label="No edits" value={num(sm.no_artifact_sessions)} hint="Sessions with many tool calls and no file edit" />
            </div>
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 mt-4">
              <StatTile label="Cost per session" value={formatCost(sm.cost_per_session)} />
              <StatTile label="Turns per session" value={sm.turns_per_session ? sm.turns_per_session.toFixed(1) : NA} hint="User turns" />
              <StatTile label="Cost per turn" value={sm.cost_per_turn ? formatCost(sm.cost_per_turn) : NA} />
            </div>
          </Section>

          <Section title="By signal" description="A session can carry more than one flag, so counts overlap.">
            <Card>
              <CardHeader>
                <CardTitle><ShieldAlert size={14} className="text-[var(--tt-brand)]" /> Flagged sessions by signal</CardTitle>
              </CardHeader>
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={flagChart} layout="vertical" margin={{ top: 4, right: 24, bottom: 0, left: 8 }}>
                    <CartesianGrid stroke={ct.grid} horizontal={false} />
                    <XAxis type="number" allowDecimals={false} {...AXIS} />
                    <YAxis type="category" dataKey="name" width={120} {...AXIS} />
                    <Tooltip
                      contentStyle={ct.tooltipStyle}
                      itemStyle={ct.tooltipItem}
                      labelStyle={ct.tooltipLabel}
                      cursor={{ fill: ct.grid }}
                      formatter={(v, _n, p) => [`${Number(v).toLocaleString()} sessions, ${formatCost(p.payload.cost)}`, "Flagged"]}
                    />
                    <Bar dataKey="sessions" fill="#60a5fa" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <dl className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {WASTE_FLAGS.map(f => (
                  <div key={f}>
                    <dt className="text-[12px] font-semibold text-[var(--tt-fg)]">{FLAG_INFO[f].label}</dt>
                    <dd className="text-[12px] text-[var(--tt-fg-muted)]">{FLAG_INFO[f].description}</dd>
                  </div>
                ))}
              </dl>
            </Card>
          </Section>

          <Section title="By agent" description="Not every agent logs every signal. Missing data is marked, not shown as zero.">
            <Card className="p-0 overflow-hidden">
              <Table>
                <THead>
                  <TR>
                    <TH className="pl-5">Agent</TH>
                    <TH className="text-right">Sessions</TH>
                    <TH className="text-right">Analysed</TH>
                    <TH className="text-right">Cost</TH>
                    <TH className="text-right">Flagged</TH>
                    <TH className="text-right">Failure rate</TH>
                    <TH className="text-right">Retry calls</TH>
                    <TH className="text-right">Repeated reads</TH>
                    <TH className="text-right">Cost / session</TH>
                    <TH className="text-right pr-5">Turns / session</TH>
                  </TR>
                </THead>
                <TBody>
                  {data.by_agent.map(a => (
                    <TR key={a.agent}>
                      <TD className="pl-5"><AgentBadge agent={a.agent} /></TD>
                      <TD className="text-right tabular">{a.sessions.toLocaleString()}</TD>
                      <TD className="text-right tabular">{a.analysed.toLocaleString()}</TD>
                      <TD className="text-right tabular">{formatCost(a.cost)}</TD>
                      <TD className="text-right tabular">{a.flagged_sessions.toLocaleString()}</TD>
                      <CapCell row={a} col="failure_rate" render={v => pct(v)} />
                      <CapCell row={a} col="retry_calls" render={v => v.toLocaleString()} />
                      <CapCell row={a} col="reread_calls" render={v => v.toLocaleString()} />
                      <TD className="text-right tabular">{formatCost(a.cost_per_session)}</TD>
                      <CapCell row={a} col="turns_per_session" render={v => v.toFixed(1)} />
                    </TR>
                  ))}
                </TBody>
              </Table>
            </Card>
          </Section>

          <Section
            title="Flagged sessions"
            description={
              sm.flagged_sessions > data.sessions.length
                ? `${sm.flagged_sessions.toLocaleString()} sessions are flagged, showing the ${data.sessions.length.toLocaleString()} most expensive.`
                : `${sm.flagged_sessions.toLocaleString()} flagged.`
            }
            actions={
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-[10px] uppercase tracking-[0.16em] text-[var(--tt-fg-dim)]">Flag</span>
                {(["all", ...WASTE_FLAGS] as const).map(f => (
                  <button
                    key={f}
                    onClick={() => setFlagFilter(f)}
                    className={cn(
                      "px-2 py-0.5 text-[10px] font-medium rounded-full border transition-colors",
                      flagFilter === f
                        ? "border-[var(--tt-brand)] text-[var(--tt-fg)] bg-[var(--tt-brand)]/10"
                        : "border-[var(--tt-border)] text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)]",
                    )}
                  >
                    {f === "all" ? "All" : FLAG_INFO[f].label}
                  </button>
                ))}
              </div>
            }
          >
            {shownSessions.length === 0 ? (
              <EmptyState title="No flagged sessions" description={flagFilter === "all" ? "Nothing in this range crossed a threshold." : "No listed session has this flag."} />
            ) : (
              <Card className="p-0 overflow-hidden">
                <Table>
                  <THead>
                    <TR>
                      <TH className="pl-5">Session</TH>
                      <TH>Agent</TH>
                      <TH>Project</TH>
                      <TH>When</TH>
                      <TH className="text-right">Cost</TH>
                      <TH className="text-right">Turns</TH>
                      <TH className="text-right">Tool calls</TH>
                      <TH className="pr-5">Flags</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {shownSessions.map(s => {
                      const href = `/sessions/${s.id}?agent=${s.agent}&from=${encodeURIComponent(pathname)}`;
                      return (
                        <TR key={`${s.agent}-${s.id}`} interactive>
                          <TD className="pl-5 max-w-[420px] truncate text-[var(--tt-fg)]">
                            <Link href={href} className="block truncate">
                              {s.display || <span className="italic text-[var(--tt-fg-faint)]">No message content</span>}
                            </Link>
                          </TD>
                          <TD><Link href={href} className="block"><AgentBadge agent={s.agent} /></Link></TD>
                          <TD className="font-mono text-[12px] text-[var(--tt-fg-muted)] max-w-[160px] truncate" title={s.project}>
                            <Link href={href} className="block truncate">{projectBasename(s.project) || NA}</Link>
                          </TD>
                          <TD className="tabular text-[11px] text-[var(--tt-fg-muted)]">
                            <Link href={href} className="block">
                              {s.timestamp ? format(new Date(s.timestamp), "MMM d, HH:mm") : NA}
                            </Link>
                          </TD>
                          <TD className="text-right tabular">{formatCost(s.cost)}</TD>
                          <TD className="text-right tabular">{num(s.user_turns)}</TD>
                          <TD className="text-right tabular">{s.tool_calls.toLocaleString()}</TD>
                          <TD className="pr-5">
                            <div className="flex flex-wrap gap-1">
                              {s.flags.map(f => (
                                <Badge key={f} variant="warn" title={FLAG_INFO[f]?.description}>
                                  {FLAG_INFO[f]?.label ?? f}
                                </Badge>
                              ))}
                            </div>
                          </TD>
                        </TR>
                      );
                    })}
                  </TBody>
                </Table>
              </Card>
            )}
          </Section>

          <details className="group rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-sunken)] p-4">
            <summary className="cursor-pointer text-[13px] font-medium text-[var(--tt-fg)]">How this is measured</summary>
            <div className="mt-3 space-y-4 text-[12px] text-[var(--tt-fg-muted)]">
              <div>
                <p className="font-semibold text-[var(--tt-fg)] mb-1">Thresholds</p>
                <ul className="list-disc pl-5 space-y-1">
                  {thresholdLines(data.thresholds).map(l => (
                    <li key={l.flag}><span className="text-[var(--tt-fg)]">{FLAG_INFO[l.flag].label}:</span> {l.text}</li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="font-semibold text-[var(--tt-fg)] mb-1">Caveats</p>
                <ul className="list-disc pl-5 space-y-1">
                  <li>The units are the session and the user turn, because agent logs carry no task boundary.</li>
                  <li>Flagged spend is the cost of flagged sessions. It is not an estimate of wasted money.</li>
                  <li>Labels and counts are computed on this machine. No prompt or code is stored.</li>
                </ul>
              </div>
            </div>
          </details>
        </>
      )}
    </div>
  );
}
