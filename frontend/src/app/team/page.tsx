"use client";

import { Users, Server, TrendingUp, DollarSign, Cpu, Folder } from "lucide-react";
import { useResource } from "@/lib/api";
import { timeAgo } from "@/lib/notifications";
import { formatTokens, formatCost } from "@/lib/format";
import type { OrgSummary } from "@/lib/org";
import {
  PageHeader, StatTile, Section, Card, CardEyebrow, CardTitle,
  Table, THead, TBody, TR, TH, TD, AgentBadge, EmptyState, Skeleton,
} from "@/components/ui";

export default function TeamPage() {
  const { data, loading, error } = useResource<OrgSummary>("/org/summary", { pollMs: 30_000 });

  if (loading && !data) return <TeamLoading />;

  if (error) {
    return (
      <div className="px-8 py-8 max-w-[1200px] mx-auto">
        <EmptyState
          icon={<Users size={20} />}
          title="Couldn't load team data"
          description={`The collector didn't respond (${error.message}). If you're running org mode on a separate host, make sure this dashboard points at it.`}
        />
      </div>
    );
  }

  if (!data || !data.enabled) {
    return <TeamSetup />;
  }

  return (
    <div className="px-8 py-8 max-w-[1200px] mx-auto space-y-10 pb-20">
      <PageHeader
        eyebrow="Team"
        title="Team usage"
        description="Token consumption and cost rolled up across every machine reporting to this collector."
        icon={<Users size={20} strokeWidth={2.25} />}
      />

      <Section title="Totals" description="Across all reporting machines, all time.">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <StatTile
            label="Sessions"
            value={data.totals.sessions.toLocaleString()}
            hint={`${data.by_machine.length} machine${data.by_machine.length === 1 ? "" : "s"} reporting`}
            icon={<Server size={16} />}
            accent="var(--tt-brand)"
          />
          <StatTile
            label="Tokens"
            value={formatTokens(data.totals.tokens)}
            hint={`${data.totals.tokens.toLocaleString()} total`}
            icon={<TrendingUp size={16} />}
            accent="var(--tt-info)"
          />
          <StatTile
            label="Cost"
            value={formatCost(data.totals.cost)}
            hint="Sum of priced sessions"
            icon={<DollarSign size={16} />}
            accent="var(--tt-warn)"
          />
        </div>
      </Section>

      {/* By machine */}
      <Card padding="none">
        <div className="px-5 py-4 border-b border-[var(--tt-border)] flex items-center justify-between">
          <CardTitle><Server size={14} className="text-[var(--tt-brand)]" /> By machine</CardTitle>
          <CardEyebrow>{data.by_machine.length} machine{data.by_machine.length === 1 ? "" : "s"}</CardEyebrow>
        </div>
        <div className="overflow-x-auto">
          <Table>
            <THead>
              <TR>
                <TH className="pl-5">Machine</TH>
                <TH className="text-right">Sessions</TH>
                <TH className="text-right">Tokens</TH>
                <TH className="text-right">Cost</TH>
                <TH className="text-right pr-5">Last seen</TH>
              </TR>
            </THead>
            <TBody>
              {data.by_machine.length === 0 ? (
                <TR><TD className="pl-5 text-[var(--tt-fg-dim)]" colSpan={5}>No sessions ingested yet.</TD></TR>
              ) : (
                data.by_machine.map((m) => (
                  <TR key={m.machine} interactive>
                    <TD className="pl-5">
                      <span className="flex items-center gap-2 font-medium text-[var(--tt-fg)]">
                        <Server size={12} className="text-[var(--tt-fg-dim)]" /> {m.machine}
                      </span>
                    </TD>
                    <TD className="text-right tabular text-[var(--tt-fg-muted)]">{m.sessions.toLocaleString()}</TD>
                    <TD className="text-right tabular font-semibold text-[var(--tt-fg)]">{formatTokens(m.tokens)}</TD>
                    <TD className="text-right tabular font-semibold text-amber-300">{formatCost(m.cost)}</TD>
                    <TD className="text-right pr-5 tabular text-[var(--tt-fg-dim)]">
                      {m.last_seen ? timeAgo(m.last_seen) : "never"}
                    </TD>
                  </TR>
                ))
              )}
            </TBody>
          </Table>
        </div>
      </Card>

      {/* By agent + by project side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card padding="none">
          <div className="px-5 py-4 border-b border-[var(--tt-border)] flex items-center justify-between">
            <CardTitle><Cpu size={14} className="text-emerald-400" /> By agent</CardTitle>
            <CardEyebrow>{data.by_agent.length} agent{data.by_agent.length === 1 ? "" : "s"}</CardEyebrow>
          </div>
          <div className="overflow-x-auto">
            <Table>
              <THead>
                <TR>
                  <TH className="pl-5">Agent</TH>
                  <TH className="text-right">Sessions</TH>
                  <TH className="text-right">Tokens</TH>
                  <TH className="text-right pr-5">Cost</TH>
                </TR>
              </THead>
              <TBody>
                {data.by_agent.length === 0 ? (
                  <TR><TD className="pl-5 text-[var(--tt-fg-dim)]" colSpan={4}>No data.</TD></TR>
                ) : (
                  data.by_agent.map((a) => (
                    <TR key={a.agent} interactive>
                      <TD className="pl-5"><AgentBadge agent={a.agent} /></TD>
                      <TD className="text-right tabular text-[var(--tt-fg-muted)]">{a.sessions.toLocaleString()}</TD>
                      <TD className="text-right tabular font-semibold text-[var(--tt-fg)]">{formatTokens(a.tokens)}</TD>
                      <TD className="text-right pr-5 tabular font-semibold text-amber-300">{formatCost(a.cost)}</TD>
                    </TR>
                  ))
                )}
              </TBody>
            </Table>
          </div>
        </Card>

        <Card padding="none">
          <div className="px-5 py-4 border-b border-[var(--tt-border)] flex items-center justify-between">
            <CardTitle><Folder size={14} className="text-[var(--tt-brand)]" /> By project</CardTitle>
            <CardEyebrow>{data.by_project.length} project{data.by_project.length === 1 ? "" : "s"}</CardEyebrow>
          </div>
          <div className="overflow-x-auto">
            <Table>
              <THead>
                <TR>
                  <TH className="pl-5">Project</TH>
                  <TH className="text-right">Sessions</TH>
                  <TH className="text-right">Tokens</TH>
                  <TH className="text-right pr-5">Cost</TH>
                </TR>
              </THead>
              <TBody>
                {data.by_project.length === 0 ? (
                  <TR><TD className="pl-5 text-[var(--tt-fg-dim)]" colSpan={4}>No data.</TD></TR>
                ) : (
                  data.by_project.map((p) => (
                    <TR key={p.project} interactive>
                      <TD className="pl-5">
                        <span className="font-mono text-[12px] text-[var(--tt-fg)] truncate block max-w-[220px]" title={p.project}>
                          {p.project || "(unknown)"}
                        </span>
                      </TD>
                      <TD className="text-right tabular text-[var(--tt-fg-muted)]">{p.sessions.toLocaleString()}</TD>
                      <TD className="text-right tabular font-semibold text-[var(--tt-fg)]">{formatTokens(p.tokens)}</TD>
                      <TD className="text-right pr-5 tabular font-semibold text-amber-300">{formatCost(p.cost)}</TD>
                    </TR>
                  ))
                )}
              </TBody>
            </Table>
          </div>
        </Card>
      </div>

      {/* Recent sessions */}
      <Card padding="none">
        <div className="px-5 py-4 border-b border-[var(--tt-border)] flex items-center justify-between">
          <CardTitle><TrendingUp size={14} className="text-[var(--tt-brand)]" /> Recent sessions</CardTitle>
          <CardEyebrow>newest {data.recent.length}</CardEyebrow>
        </div>
        <div className="overflow-x-auto">
          <Table>
            <THead>
              <TR>
                <TH className="pl-5">When</TH>
                <TH>Machine</TH>
                <TH>Agent</TH>
                <TH>Project</TH>
                <TH className="text-right">Tokens</TH>
                <TH className="text-right pr-5">Cost</TH>
              </TR>
            </THead>
            <TBody>
              {data.recent.length === 0 ? (
                <TR><TD className="pl-5 text-[var(--tt-fg-dim)]" colSpan={6}>No sessions ingested yet.</TD></TR>
              ) : (
                data.recent.map((s) => (
                  <TR key={`${s.machine}:${s.id}`} interactive>
                    <TD className="pl-5 tabular text-[var(--tt-fg-dim)] whitespace-nowrap">{timeAgo(s.timestamp)}</TD>
                    <TD className="text-[var(--tt-fg-muted)] whitespace-nowrap">{s.machine}</TD>
                    <TD><AgentBadge agent={s.agent} /></TD>
                    <TD>
                      <span className="font-mono text-[12px] text-[var(--tt-fg-muted)] truncate block max-w-[220px]" title={s.project}>
                        {s.project || "(unknown)"}
                      </span>
                    </TD>
                    <TD className="text-right tabular font-semibold text-[var(--tt-fg)]">{formatTokens(s.tokens_total)}</TD>
                    <TD className="text-right pr-5 tabular text-amber-300">{s.cost == null ? "—" : formatCost(s.cost)}</TD>
                  </TR>
                ))
              )}
            </TBody>
          </Table>
        </div>
      </Card>
    </div>
  );
}

/* Empty state shown when org mode isn't configured. Explains what org mode is
   and how to turn it on. The snippet is illustrative setup, not live values. */
function TeamSetup() {
  return (
    <div className="px-8 py-8 max-w-[900px] mx-auto space-y-10 pb-20">
      <PageHeader
        eyebrow="Team"
        title="Team usage"
        description="Roll up token usage across your whole team on a collector you host yourself."
        icon={<Users size={20} strokeWidth={2.25} />}
      />

      <Section title="What org mode is">
        <div className="rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-sunken)] p-6 space-y-4 text-sm text-[var(--tt-fg-dim)]">
          <p>
            Org mode lets several developers report their agent usage to one
            TokenTelemetry instance you run as a central collector. Each machine
            keeps working locally as usual and, on a schedule, sends its session
            totals (agent, project, tokens, cost) to the collector over a
            token-authenticated endpoint. Nothing else leaves the machine, and no
            prompt or transcript content is sent. This page then shows the
            combined picture: usage by machine, by agent, and by project.
          </p>
          <p>
            It&apos;s off until you configure at least one machine on the collector.
          </p>
        </div>
      </Section>

      <Section title="Turn it on" description="Two steps: register machines on the collector, then run the shipper on each dev box.">
        <div className="rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-sunken)] p-6 space-y-5 text-sm text-[var(--tt-fg-dim)]">
          <ol className="list-decimal list-inside space-y-4 text-[var(--tt-fg)]">
            <li>
              <span className="font-medium">On the collector,</span> create an{" "}
              <code className="font-mono text-[12px] text-[var(--tt-fg-muted)] bg-[var(--tt-panel)] border border-[var(--tt-border)] rounded px-1 py-0.5">org.json</code>{" "}
              in your data directory with one entry per machine and a random token for each:
              <pre className="mt-2 text-[11px] font-mono text-[var(--tt-fg-muted)] whitespace-pre-wrap bg-[var(--tt-panel)] border border-[var(--tt-border)] rounded-lg p-3 overflow-x-auto">
{`{
  "machines": [
    { "label": "kyle-laptop", "token": "` + `<random hex>` + `" }
  ]
}`}
              </pre>
            </li>
            <li>
              <span className="font-medium">On each dev machine,</span> run the shipper,
              pointing it at the collector with that machine&apos;s token:
              <pre className="mt-2 text-[11px] font-mono text-[var(--tt-fg-muted)] whitespace-pre-wrap bg-[var(--tt-panel)] border border-[var(--tt-border)] rounded-lg p-3 overflow-x-auto">
{`python backend/org_ship.py \\
  --central-url https://collector.example:8000 \\
  --token <this machine's token>`}
              </pre>
            </li>
          </ol>
          <p>
            Re-running the shipper is safe: ingestion is idempotent per machine and
            session, so the same sessions never double-count. Once a machine
            reports, this page fills in automatically.
          </p>
        </div>
      </Section>
    </div>
  );
}

function TeamLoading() {
  return (
    <div className="px-8 py-8 max-w-[1200px] mx-auto space-y-10">
      <Skeleton className="h-12 w-72" />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-28 w-full" />)}
      </div>
      <Skeleton className="h-64 w-full" />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Skeleton className="h-64" />
        <Skeleton className="h-64" />
      </div>
    </div>
  );
}
