"use client";

import { useMemo } from "react";
import {
  CartesianGrid, Legend, Line, LineChart, ReferenceArea, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import type { HostImpactPoint, PersonalBaseline } from "@/lib/resources";

const MIB = 1024 * 1024;

export default function SystemImpactTimeline({
  series,
  baseline,
}: {
  series: HostImpactPoint[];
  baseline: PersonalBaseline;
}) {
  const data = useMemo(() => series.map((point) => ({
    ...point,
    label: new Date(point.timestamp * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
    agentRssMiB: point.agent_rss_bytes / MIB,
    wiredMiB: point.wired_bytes ? point.wired_bytes / MIB : null,
  })), [series]);
  const low = baseline.range_low === null ? undefined : baseline.range_low / MIB;
  const high = baseline.range_high === null ? undefined : baseline.range_high / MIB;

  if (data.length < 2) {
    return (
      <div className="h-72 grid place-items-center text-center px-6" role="status">
        <p className="text-[13px] leading-relaxed text-[var(--tt-fg-dim)] max-w-md">
          Recording the first local observation. Keep this page open for a short timeline; your personal range becomes useful after comparable sessions accumulate.
        </p>
      </div>
    );
  }

  return (
    <div className="h-72 w-full" aria-label="Agent and host memory timeline">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 16, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--tt-border)" strokeDasharray="3 3" vertical={false} />
          {low !== undefined && high !== undefined && (
            <ReferenceArea y1={low} y2={high} fill="var(--tt-success)" fillOpacity={0.09} />
          )}
          <XAxis dataKey="label" tick={{ fill: "var(--tt-fg-dim)", fontSize: 10 }} axisLine={false} tickLine={false} minTickGap={28} />
          <YAxis tickFormatter={(value) => `${Math.round(value)} MB`} tick={{ fill: "var(--tt-fg-dim)", fontSize: 10 }} axisLine={false} tickLine={false} width={54} />
          <Tooltip
            contentStyle={{ background: "var(--tt-panel)", border: "1px solid var(--tt-border)", borderRadius: "var(--tt-radius)", fontSize: 12 }}
            formatter={(value, name) => [`${Math.round(Number(value) || 0)} MB`, name === "agentRssMiB" ? "Detected agents" : "Host wired memory"]}
          />
          <Legend formatter={(value) => value === "agentRssMiB" ? "Detected agents" : "Host wired memory"} wrapperStyle={{ fontSize: 11, color: "var(--tt-fg-dim)" }} />
          <Line type="monotone" dataKey="agentRssMiB" stroke="var(--tt-brand)" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
          <Line type="monotone" dataKey="wiredMiB" stroke="var(--tt-warn)" strokeWidth={2} dot={false} activeDot={{ r: 4 }} connectNulls />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
