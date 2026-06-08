"use client";

import React, { useMemo } from "react";
import { Zap, Leaf, Cpu, CheckCircle2 } from "lucide-react";
import { useResource } from "@/lib/api";
import { Section, Card, CardTitle, Table, THead, TBody, TR, TH, TD, Badge, Skeleton } from "@/components/ui";
import { isLocalModel, estimateEnergyWh } from "@/lib/insights";

interface Session {
  id: string;
  agent: string;
  model?: string;
  tokens?: { input: number; output: number; cached: number; total: number };
}

interface AnalyticsData {
  by_model?: Record<string, { total: number; session_count: number; agent: string }>;
  by_agent?: Record<string, { energy_wh?: number; savings_usd?: number }>;
  total?: { energy_wh?: number; savings_usd?: number };
}

export default function LocalPowerInsights() {
  const sessionsRes = useResource<Session[]>("/sessions", { pollMs: 15_000, initial: [] });
  const analyticsRes = useResource<AnalyticsData>("/analytics", { pollMs: 30_000 });

  const loading = sessionsRes.loading || analyticsRes.loading;
  
  const sessions = sessionsRes.data ?? [];
  const analytics = analyticsRes.data;

  const localModelsMap = useMemo(() => {
    const map = new Map<string, { session_count: number; total_tokens: number; output_tokens: number }>();
    sessions.forEach(s => {
      const model = s.model || "unknown";
      if (isLocalModel(model)) {
        const existing = map.get(model) || { session_count: 0, total_tokens: 0, output_tokens: 0 };
        existing.session_count += 1;
        existing.total_tokens += s.tokens?.total || 0;
        existing.output_tokens += s.tokens?.output || 0;
        map.set(model, existing);
      }
    });
    return map;
  }, [sessions]);

  const hasLocalModels = localModelsMap.size > 0;

  if (!loading && !hasLocalModels) {
    return null;
  }

  let totalEnergyWh: number | undefined = analytics?.total?.energy_wh;
  let savingsUsd: number | undefined = analytics?.total?.savings_usd;
  let isEstimate = false;

  if (totalEnergyWh === undefined) {
    isEstimate = true;
    totalEnergyWh = Array.from(localModelsMap.values()).reduce((acc, m) => acc + estimateEnergyWh(m.output_tokens), 0);
  }

  const modelRows = Array.from(localModelsMap.entries()).sort((a, b) => b[1].total_tokens - a[1].total_tokens);

  return (
    <Section
      title="Local & Power Insights"
      description="Efficiency and cost savings from running models locally."
      actions={<Badge variant="success" size="sm"><Leaf size={12} className="mr-1.5 inline-block"/>Local Mode</Badge>}
    >
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="space-y-4">
          <Card padding="lg" className="flex flex-col justify-center">
            <div className="flex items-center gap-3 mb-2">
              <div className="p-2 rounded-md bg-emerald-500/10 text-emerald-500">
                <Zap size={20} />
              </div>
              <div>
                <div className="text-[12px] font-medium text-[var(--tt-fg-muted)] uppercase tracking-wider">
                  Total Local Energy
                </div>
                <div className="text-2xl font-semibold text-[var(--tt-fg)]">
                  {loading ? <Skeleton className="h-8 w-24" /> : (
                    totalEnergyWh! > 1000 
                      ? `${(totalEnergyWh! / 1000).toFixed(2)} kWh` 
                      : `${totalEnergyWh!.toFixed(2)} Wh`
                  )}
                </div>
              </div>
            </div>
            {isEstimate && !loading && (
              <div className="text-[11px] text-[var(--tt-fg-faint)] italic mt-2">
                *Estimated based on 0.05 Wh per output token. Awaiting backend telemetry.
              </div>
            )}
          </Card>

          {(!loading && savingsUsd !== undefined) ? (
            <Card padding="lg" className="flex flex-col justify-center border-emerald-500/30">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-md bg-emerald-500/20 text-emerald-400">
                  <CheckCircle2 size={20} />
                </div>
                <div>
                  <div className="text-[12px] font-medium text-emerald-400/80 uppercase tracking-wider">
                    Cloud Savings
                  </div>
                  <div className="text-2xl font-semibold text-emerald-400">
                    ${savingsUsd.toFixed(2)}
                  </div>
                </div>
              </div>
              <div className="text-[11px] text-[var(--tt-fg-faint)] mt-2">
                Running locally saved vs cloud API rates.
              </div>
            </Card>
          ) : null}
        </div>

        <Card padding="none" className="lg:col-span-2">
          <div className="px-5 py-4 border-b border-[var(--tt-border)] flex items-center justify-between">
            <CardTitle><Cpu size={14} className="text-[var(--tt-brand)]" /> Local Model Throughput</CardTitle>
            <div className="text-[10px] text-[var(--tt-fg-faint)] uppercase tracking-wider">
              *Identified by name heuristic
            </div>
          </div>
          <div className="overflow-y-auto max-h-[300px]">
            <Table>
              <THead>
                <TR>
                  <TH className="pl-5">Model</TH>
                  <TH className="text-right">Sessions</TH>
                  <TH className="text-right pr-5">Total Tokens</TH>
                </TR>
              </THead>
              <TBody>
                {loading ? (
                  <TR>
                    <TD className="pl-5"><Skeleton className="h-4 w-24" /></TD>
                    <TD className="text-right"><Skeleton className="h-4 w-8 ml-auto" /></TD>
                    <TD className="text-right pr-5"><Skeleton className="h-4 w-12 ml-auto" /></TD>
                  </TR>
                ) : modelRows.length > 0 ? (
                  modelRows.map(([name, stats]) => (
                    <TR key={name}>
                      <TD className="pl-5 font-mono text-[12px] text-[var(--tt-fg)] truncate max-w-[200px]" title={name}>
                        {name}
                      </TD>
                      <TD className="text-right tabular text-[var(--tt-fg-muted)]">
                        {stats.session_count}
                      </TD>
                      <TD className="text-right pr-5 tabular font-semibold text-[var(--tt-fg)]">
                        {stats.total_tokens.toLocaleString()}
                      </TD>
                    </TR>
                  ))
                ) : (
                  <TR>
                    <TD colSpan={3} className="text-center py-6 text-[var(--tt-fg-muted)] text-[12px]">
                      No local models detected yet.
                    </TD>
                  </TR>
                )}
              </TBody>
            </Table>
          </div>
        </Card>
      </div>
    </Section>
  );
}
