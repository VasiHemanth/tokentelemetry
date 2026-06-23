"use client";

import { HardDrive, AlertTriangle } from "lucide-react";
import { useResource } from "@/lib/api";
import {
  Card, CardHeader, CardTitle, CardEyebrow,
  Table, THead, TBody, TR, TH, TD, EmptyState, Skeleton,
} from "@/components/ui";

interface AgentProcess {
  pid: number;
  name: string;
  agent_type: string;
  cpu_percent: number;
  memory_rss_mb: number;
  io_read_mb_s: number;
  io_write_mb_s: number;
  status: string;
  uptime_seconds: number;
}

interface AgentProcessesResponse {
  error?: string;
  processes: AgentProcess[];
  total_write_mb_s?: number;
  total_read_mb_s?: number;
  total_memory_rss_mb?: number;
  sampled_at?: number;
}

const AGENT_LABELS: Record<string, string> = {
  "claude-code": "Claude Code",
  codex: "Codex",
  ollama: "Ollama",
  "local-models": "Local Models",
  hermes: "Hermes",
  grok: "Grok Build",
};

function agentLabel(t: string): string {
  return AGENT_LABELS[t] ?? t;
}

// green < 1MB/s, yellow 1-5MB/s, red > 5MB/s
function writeColor(rate: number): string {
  if (rate > 5) return "text-[var(--tt-danger,#f87171)]";
  if (rate >= 1) return "text-[var(--tt-warn,#fbbf24)]";
  return "text-[var(--tt-success,#34d399)]";
}

function formatUptime(sec: number): string {
  if (sec <= 0) return "—";
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

export default function AgentProcessCard() {
  const res = useResource<AgentProcessesResponse>("/api/agent-processes", { pollMs: 5_000 });
  const data = res.data;
  const processes = data?.processes ?? [];

  const hot = processes.filter((p) => p.io_write_mb_s > 5);

  return (
    <Card padding="none" className="overflow-hidden">
      <CardHeader className="px-5 py-4 mb-0 border-b border-[var(--tt-border)]">
        <CardTitle>
          <HardDrive size={14} className="text-[var(--tt-brand)]" />
          Agent process monitor
        </CardTitle>
        <CardEyebrow>{processes.length} running · auto-sync 5s</CardEyebrow>
      </CardHeader>

      {hot.map((p) => (
        <div
          key={`warn-${p.pid}`}
          className="flex items-center gap-2 px-5 py-2.5 text-[12px] text-[var(--tt-danger,#f87171)] bg-[var(--tt-danger,#f87171)]/8 border-b border-[var(--tt-border)]"
        >
          <AlertTriangle size={13} className="shrink-0" />
          <span>
            {agentLabel(p.agent_type)} is writing at {p.io_write_mb_s.toFixed(2)} MB/s — check for log bloat
          </span>
        </div>
      ))}

      {res.loading && !data ? (
        <div className="p-5 space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-5 w-full" />
          ))}
        </div>
      ) : data?.error ? (
        <EmptyState
          icon={<HardDrive size={20} />}
          title="Process monitor unavailable"
          description={`${data.error}. Install it in the backend (pip install psutil) to see live agent resource use.`}
        />
      ) : processes.length === 0 ? (
        <EmptyState
          icon={<HardDrive size={20} />}
          title="No agent processes running"
          description="No known AI agent processes (Claude Code, Codex, Ollama, local models, Hermes, Grok) were found on this machine."
        />
      ) : (
        <div className="max-h-[420px] overflow-y-auto">
          <Table>
            <THead>
              <TR>
                <TH className="pl-5">Agent</TH>
                <TH>Process</TH>
                <TH className="text-right">PID</TH>
                <TH className="text-right">CPU %</TH>
                <TH className="text-right">Mem (MB)</TH>
                <TH className="text-right">Write MB/s</TH>
                <TH className="text-right">Read MB/s</TH>
                <TH className="text-right pr-5">Uptime</TH>
              </TR>
            </THead>
            <TBody>
              {processes.map((p) => (
                <TR key={p.pid}>
                  <TD className="pl-5 font-medium">{agentLabel(p.agent_type)}</TD>
                  <TD className="font-mono text-[12px] text-[var(--tt-fg-muted)] max-w-[180px] truncate" title={p.name}>
                    {p.name}
                  </TD>
                  <TD className="text-right tabular text-[var(--tt-fg-muted)]">{p.pid}</TD>
                  <TD className="text-right tabular">{p.cpu_percent.toFixed(1)}</TD>
                  <TD className="text-right tabular">{p.memory_rss_mb.toFixed(1)}</TD>
                  <TD className={`text-right tabular font-semibold ${writeColor(p.io_write_mb_s)}`}>
                    {p.io_write_mb_s.toFixed(2)}
                  </TD>
                  <TD className="text-right tabular text-[var(--tt-fg-muted)]">{p.io_read_mb_s.toFixed(2)}</TD>
                  <TD className="text-right pr-5 tabular text-[var(--tt-fg-muted)]">{formatUptime(p.uptime_seconds)}</TD>
                </TR>
              ))}
              <TR className="font-semibold">
                <TD className="pl-5 uppercase tracking-[0.14em] text-[10px] text-[var(--tt-fg-dim)]">Totals</TD>
                <TD />
                <TD />
                <TD />
                <TD className="text-right tabular">{(data?.total_memory_rss_mb ?? 0).toFixed(1)}</TD>
                <TD className={`text-right tabular ${writeColor(data?.total_write_mb_s ?? 0)}`}>
                  {(data?.total_write_mb_s ?? 0).toFixed(2)}
                </TD>
                <TD className="text-right tabular">{(data?.total_read_mb_s ?? 0).toFixed(2)}</TD>
                <TD className="pr-5" />
              </TR>
            </TBody>
          </Table>
        </div>
      )}
    </Card>
  );
}
