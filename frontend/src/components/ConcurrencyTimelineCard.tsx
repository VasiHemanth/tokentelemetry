"use client";

import React, { useMemo } from "react";
import { Layers, Zap, DollarSign, Clock } from "lucide-react";
import { useResource } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardEyebrow, Badge, Skeleton } from "@/components/ui";
import { getAgent } from "@/lib/agents";
import { formatCost } from "@/lib/format";

interface ConcurrencyWindow {
  start: number; // epoch seconds
  end: number; // epoch seconds
  session_ids: string[];
  agent_types: string[];
  combined_cost_usd: number;
  combined_write_mb_estimate: number | null;
}

interface ConcurrencyResponse {
  windows: ConcurrencyWindow[];
  peak_concurrent_count: number;
  peak_combined_cost_per_hour: number;
  total_concurrent_hours: number;
}

const WINDOW_DAYS = 7;
const WINDOW_MS = WINDOW_DAYS * 24 * 60 * 60 * 1000;

// Bar colour by concurrency depth: 1 (shouldn't appear — windows are 2+) light,
// 3+ dark. Uses the brand info hue so it reads as "activity" not "warning".
function depthColor(n: number): string {
  if (n >= 4) return "rgba(96,165,250,0.95)";
  if (n === 3) return "rgba(96,165,250,0.75)";
  return "rgba(96,165,250,0.5)"; // 2
}

export default function ConcurrencyTimelineCard() {
  const res = useResource<ConcurrencyResponse>("/sessions/concurrency", {
    pollMs: 30_000,
  });

  const data = res.data;
  const loading = res.loading;

  // Window of the last 7 days, in ms.
  const now = Date.now();
  const rangeStart = now - WINDOW_MS;

  const rows = useMemo(() => {
    if (!data?.windows) return [];
    return data.windows
      .map((w) => {
        const startMs = w.start * 1000;
        const endMs = w.end * 1000;
        // Clamp to the visible 7-day range.
        const vis0 = Math.max(startMs, rangeStart);
        const vis1 = Math.min(endMs, now);
        return { w, startMs, endMs, vis0, vis1 };
      })
      .filter((r) => r.vis1 > r.vis0) // intersects the visible range
      .sort((a, b) => a.startMs - b.startMs);
  }, [data, rangeStart, now]);

  const hasRows = rows.length > 0;

  // Day gridlines (7 slots).
  const dayTicks = useMemo(() => {
    const ticks: { left: number; label: string }[] = [];
    for (let i = 0; i <= WINDOW_DAYS; i++) {
      const t = rangeStart + (i / WINDOW_DAYS) * WINDOW_MS;
      ticks.push({
        left: (i / WINDOW_DAYS) * 100,
        label: new Date(t).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
      });
    }
    return ticks;
  }, [rangeStart]);

  return (
    <Card padding="lg">
      <CardHeader>
        <div>
          <CardEyebrow>Concurrency</CardEyebrow>
          <CardTitle className="mt-1">
            <Layers size={15} /> Overlapping agent sessions
          </CardTitle>
        </div>
        <Badge variant="info" size="sm">
          Last {WINDOW_DAYS} days
        </Badge>
      </CardHeader>

      {loading ? (
        <div className="space-y-2">
          <Skeleton className="h-6 w-full" />
          <Skeleton className="h-6 w-3/4" />
          <Skeleton className="h-6 w-1/2" />
        </div>
      ) : !hasRows ? (
        <p className="text-[13px] text-[var(--tt-fg-muted)] py-6 text-center">
          No overlapping sessions in the last {WINDOW_DAYS} days.
        </p>
      ) : (
        <>
          {/* Timeline */}
          <div className="relative">
            {/* Day gridlines */}
            <div className="absolute inset-0 pointer-events-none">
              {dayTicks.map((t, i) => (
                <div
                  key={i}
                  className="absolute top-0 bottom-5 w-px bg-[var(--tt-border)]"
                  style={{ left: `${t.left}%` }}
                />
              ))}
            </div>

            {/* Window bars */}
            <div className="relative space-y-1.5 pb-5">
              {rows.map(({ w, vis0, vis1 }, idx) => {
                const left = ((vis0 - rangeStart) / WINDOW_MS) * 100;
                const width = Math.max(((vis1 - vis0) / WINDOW_MS) * 100, 0.6);
                const n = w.session_ids.length;
                const durHours = (w.end - w.start) / 3600;
                const cph = durHours > 0 ? w.combined_cost_usd / durHours : 0;
                const tip = `${n} agents active — combined ${formatCost(cph)}/hr`;
                return (
                  <div key={idx} className="relative h-6">
                    <div
                      className="absolute top-0 h-6 rounded-[var(--tt-radius-sm)] flex items-center px-1.5 gap-1 overflow-hidden cursor-default transition-[filter] hover:brightness-110"
                      style={{
                        left: `${left}%`,
                        width: `${width}%`,
                        background: depthColor(n),
                      }}
                      title={tip}
                    >
                      <span className="text-[10px] font-semibold text-white/95 whitespace-nowrap">
                        {n}×
                      </span>
                      <span className="flex items-center gap-0.5 overflow-hidden">
                        {w.agent_types.slice(0, 4).map((a) => {
                          const meta = getAgent(a);
                          return (
                            <span
                              key={a}
                              className="inline-block w-1.5 h-1.5 rounded-full shrink-0"
                              style={{ background: meta.hex }}
                              title={meta.label}
                            />
                          );
                        })}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Day axis labels */}
            <div className="relative h-4">
              {dayTicks.map((t, i) => (
                <span
                  key={i}
                  className="absolute -translate-x-1/2 text-[9px] text-[var(--tt-fg-dim)] tabular-nums"
                  style={{ left: `${t.left}%` }}
                >
                  {i % 2 === 0 ? t.label : ""}
                </span>
              ))}
            </div>
          </div>

          {/* Stat chips */}
          <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-3">
            <StatChip
              icon={<Zap size={14} />}
              label="Peak concurrent"
              value={`${data?.peak_concurrent_count ?? 0} agents`}
            />
            <StatChip
              icon={<DollarSign size={14} />}
              label="Most expensive overlap"
              value={`${formatCost(data?.peak_combined_cost_per_hour ?? 0)}/hr`}
            />
            <StatChip
              icon={<Clock size={14} />}
              label="Total concurrent time"
              value={`${(data?.total_concurrent_hours ?? 0).toFixed(1)}h`}
            />
          </div>
        </>
      )}
    </Card>
  );
}

function StatChip({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-2.5 rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-sunken)] px-3 py-2.5">
      <span className="text-[var(--tt-info)] shrink-0">{icon}</span>
      <div className="min-w-0">
        <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--tt-fg-dim)] truncate">
          {label}
        </div>
        <div className="text-[13px] font-semibold text-[var(--tt-fg)] tabular-nums truncate">
          {value}
        </div>
      </div>
    </div>
  );
}
