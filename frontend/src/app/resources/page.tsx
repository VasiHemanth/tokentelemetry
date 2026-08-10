"use client";

import { Activity, Cpu, Database, Info, MemoryStick, ShieldCheck } from "lucide-react";
import { useResource } from "@/lib/api";
import { getAgent } from "@/lib/agents";
import { formatBytes, type HostImpactHealth } from "@/lib/resources";
import SystemImpactTimeline from "@/components/resources/SystemImpactTimeline";
import {
  Badge, Card, CardHeader, CardTitle, PageHeader, Section, Skeleton, StatTile,
} from "@/components/ui";

const COPY = {
  learning: "Learning your normal range",
  normal: "Normal for this Mac",
  unusual: "Unusual for this Mac",
  extreme: "Extreme for this Mac",
} as const;

const VARIANT = {
  learning: "neutral",
  normal: "success",
  unusual: "warn",
  extreme: "danger",
} as const;

export default function SystemImpactPage() {
  const health = useResource<HostImpactHealth>("/resources/host/health", { pollMs: 5_000 });
  const data = health.data;
  const current = data?.current;
  const baseline = data?.baseline.agent_rss_bytes;
  const agentLabel = current?.agents?.length
    ? current.agents.map((agent) => getAgent(agent).label).join(", ")
    : "No supported agent process";
  const memoryUsed = current?.memory_total_bytes && current.memory_available_bytes
    ? current.memory_total_bytes - current.memory_available_bytes
    : null;

  return (
    <div className="px-8 py-8 max-w-[1600px] mx-auto space-y-10 pb-20">
      <PageHeader
        eyebrow="Local resource telemetry"
        title="System Impact"
        description="See how supported agents relate to memory pressure on this laptop. Measurements and baselines stay on this device."
        icon={<Activity size={20} strokeWidth={2.25} />}
        actions={baseline ? <Badge variant={VARIANT[baseline.state]} size="sm">{COPY[baseline.state]}</Badge> : null}
      />

      <Section title="Current context" description="Compared with your own prior observations at a similar number of active agents.">
        <div className="grid grid-cols-1 sm:grid-cols-2 2xl:grid-cols-4 gap-4">
          <StatTile label="Detected-agent memory" value={current ? formatBytes(current.agent_rss_bytes) : <Skeleton className="h-8 w-20" />} hint={agentLabel} icon={<MemoryStick size={16} />} accent="var(--tt-brand)" />
          <StatTile label="Host wired memory" value={current ? formatBytes(current.wired_bytes) : <Skeleton className="h-8 w-20" />} hint="Host-level; correlated, not process-owned" icon={<Cpu size={16} />} accent="var(--tt-warn)" />
          <StatTile label="Memory in use" value={current ? formatBytes(memoryUsed) : <Skeleton className="h-8 w-20" />} hint={current ? `${formatBytes(current.memory_available_bytes)} available` : ""} icon={<Database size={16} />} accent="var(--tt-info)" />
          <StatTile label="Background context" value={current ? `${current.process_count} processes` : <Skeleton className="h-8 w-20" />} hint={current ? `${current.active_agent_count} supported agents active` : ""} icon={<Activity size={16} />} accent="var(--tt-success)" />
        </div>
      </Section>

      <Section title="Memory over time" description="Blue is detected-agent memory. Amber is host wired memory. The shaded area is your usual detected-agent-memory range when enough comparable local samples exist.">
        <Card padding="lg">
          {!data || !baseline ? <Skeleton className="h-72 w-full" /> : <SystemImpactTimeline series={data.series} baseline={baseline} />}
        </Card>
      </Section>

      <Section title="What this means">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card padding="lg">
            <CardHeader>
              <CardTitle><Info size={14} className="text-[var(--tt-brand)]" /> Your personal baseline</CardTitle>
              {baseline && <Badge variant={VARIANT[baseline.state]} size="sm">{COPY[baseline.state]}</Badge>}
            </CardHeader>
            {!baseline ? <Skeleton className="h-20 w-full" /> : baseline.state === "learning" ? (
              <p className="text-[13px] leading-relaxed text-[var(--tt-fg-dim)]">
                TokenTelemetry has {baseline.sample_count} comparable local observation{baseline.sample_count === 1 ? "" : "s"}. It will show a normal range after 20 observations, instead of guessing from a generic benchmark.
              </p>
            ) : (
              <p className="text-[13px] leading-relaxed text-[var(--tt-fg-dim)]">
                With {data?.baseline.comparison}, detected agents usually use {formatBytes(baseline.range_low)}–{formatBytes(baseline.range_high)} on this Mac. Right now they use {formatBytes(current?.agent_rss_bytes)}{baseline.ratio_to_typical ? ` (${baseline.ratio_to_typical}× your typical level)` : ""}.
              </p>
            )}
          </Card>

          <Card padding="lg">
            <CardHeader>
              <CardTitle><ShieldCheck size={14} className="text-[var(--tt-success-fg)]" /> Evidence, not blame</CardTitle>
            </CardHeader>
            <p className="text-[13px] leading-relaxed text-[var(--tt-fg-dim)]">
              Agent memory is measured directly. Wired memory belongs to the host kernel, so this page shows it as a correlation while agents are active—not proof that one process owns it. No prompts, project paths, or process command lines are stored here, and this sampler makes no network requests.
            </p>
          </Card>
        </div>
      </Section>
    </div>
  );
}
