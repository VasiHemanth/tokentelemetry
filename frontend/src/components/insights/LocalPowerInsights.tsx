"use client";

import React, { useMemo } from "react";
import { Zap, Leaf, Cpu, CheckCircle2, Gauge, Cloud } from "lucide-react";
import { useResource } from "@/lib/api";
import { Section, Card, CardTitle, Table, THead, TBody, TR, TH, TD, Badge, Skeleton } from "@/components/ui";
import {
  isLocalSession,
  formatEnergy,
  formatCo2,
  formatTokPerSec,
  formatWhPer1M,
  type LocalSessionMetrics,
} from "@/lib/insights";

interface Session {
  id: string;
  agent: string;
  model?: string;
  provider?: string;
  billing_mode?: string;
  tokens?: { input: number; output: number; cached: number; total: number };
  cost?: number;
  tok_per_sec?: number;
  local?: LocalSessionMetrics;
}

interface ModelRow {
  total: number;
  output?: number;
  session_count: number;
  local_session_count?: number;
  agent: string;
  energy_wh?: number;
  savings_usd?: number;
  co2_g?: number;
  is_local?: boolean;
  avg_tok_per_sec?: number | null;
  tok_per_sec_samples?: number;
  wh_per_1m_output?: number | null;
  cost_per_1m_output?: number | null;
  quant?: string | null;
  params_b?: number | null;
  provider?: string | null;
}

interface AnalyticsData {
  by_model?: Record<string, ModelRow>;
  total?: {
    energy_wh?: number;
    savings_usd?: number;
    co2_g?: number;
    local_session_count?: number;
    avg_tok_per_sec?: number | null;
    wh_per_1m_output?: number | null;
  };
  local?: {
    energy_wh?: number;
    savings_usd?: number;
    co2_g?: number;
    session_count?: number;
    avg_tok_per_sec?: number | null;
    wh_per_1m_output?: number | null;
    reference_cloud_model?: string;
  };
}

export default function LocalPowerInsights({ forceShow = false }: { forceShow?: boolean } = {}) {
  const sessionsRes = useResource<Session[]>("/sessions", { pollMs: 15_000, initial: [] });
  const analyticsRes = useResource<AnalyticsData>("/analytics?local_only=true", { pollMs: 30_000 });

  const loading = sessionsRes.loading || analyticsRes.loading;
  const sessions = sessionsRes.data ?? [];
  const analytics = analyticsRes.data;

  const localSessions = useMemo(
    () =>
      sessions.filter((s) =>
        isLocalSession(s.model, s.provider, s.billing_mode, s.local),
      ),
    [sessions],
  );

  const modelRows = useMemo(() => {
    const fromAnalytics = analytics?.by_model
      ? Object.entries(analytics.by_model)
          .filter(([, s]) => s.is_local || (s.local_session_count ?? 0) > 0 || (s.energy_wh ?? 0) > 0)
          .map(([name, s]) => ({
            name,
            session_count: s.local_session_count || s.session_count,
            total_tokens: s.total,
            output_tokens: s.output ?? 0,
            energy_wh: s.energy_wh ?? 0,
            savings_usd: s.savings_usd ?? 0,
            co2_g: s.co2_g ?? 0,
            avg_tok_per_sec: s.avg_tok_per_sec,
            tok_per_sec_samples: s.tok_per_sec_samples ?? 0,
            wh_per_1m_output: s.wh_per_1m_output,
            cost_per_1m_output: s.cost_per_1m_output,
            quant: s.quant,
            params_b: s.params_b,
            provider: s.provider,
          }))
          .sort((a, b) => b.total_tokens - a.total_tokens)
      : [];

    if (fromAnalytics.length > 0) return fromAnalytics;

    // Fallback: aggregate from live sessions when analytics is empty.
    const map = new Map<
      string,
      {
        session_count: number;
        total_tokens: number;
        output_tokens: number;
        energy_wh: number;
        savings_usd: number;
        co2_g: number;
        tps_sum: number;
        tps_n: number;
      }
    >();
    for (const s of localSessions) {
      const model = s.model || "unknown";
      const existing = map.get(model) || {
        session_count: 0,
        total_tokens: 0,
        output_tokens: 0,
        energy_wh: 0,
        savings_usd: 0,
        co2_g: 0,
        tps_sum: 0,
        tps_n: 0,
      };
      existing.session_count += 1;
      existing.total_tokens += s.tokens?.total || 0;
      existing.output_tokens += s.tokens?.output || 0;
      if (s.local) {
        existing.energy_wh += s.local.energy_wh || 0;
        existing.savings_usd += s.local.savings_usd || 0;
        existing.co2_g += s.local.co2_g || 0;
        if (s.local.tok_per_sec > 0) {
          existing.tps_sum += s.local.tok_per_sec;
          existing.tps_n += 1;
        }
      }
      map.set(model, existing);
    }
    return Array.from(map.entries())
      .map(([name, m]) => ({
        name,
        ...m,
        avg_tok_per_sec: m.tps_n > 0 ? m.tps_sum / m.tps_n : null,
        tok_per_sec_samples: m.tps_n,
        wh_per_1m_output:
          m.output_tokens > 0 ? (m.energy_wh / m.output_tokens) * 1_000_000 : null,
        cost_per_1m_output: null as number | null,
        quant: null as string | null,
        params_b: null as number | null,
        provider: null as string | null,
      }))
      .sort((a, b) => b.total_tokens - a.total_tokens);
  }, [analytics, localSessions]);

  const hasLocalModels = modelRows.length > 0 || localSessions.length > 0;

  if (!loading && !hasLocalModels && !forceShow) {
    return null;
  }

  const totalEnergyWh = analytics?.local?.energy_wh ?? analytics?.total?.energy_wh ?? 0;
  const savingsUsd = analytics?.local?.savings_usd ?? analytics?.total?.savings_usd ?? 0;
  const co2g = analytics?.local?.co2_g ?? analytics?.total?.co2_g ?? 0;
  const avgTps = analytics?.local?.avg_tok_per_sec ?? analytics?.total?.avg_tok_per_sec;
  const refModel = analytics?.local?.reference_cloud_model || "claude-sonnet-4-6";

  return (
    <Section
      title="Local & Power Insights"
      description="Energy, throughput, cloud savings, and efficiency for models you run on your machine."
      actions={
        <Badge variant="success" size="sm">
          <Leaf size={12} className="mr-1.5 inline-block" />
          Local Mode
        </Badge>
      }
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <Card padding="lg">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-md bg-emerald-500/10 text-emerald-500">
              <Zap size={18} />
            </div>
            <div className="min-w-0">
              <div className="text-[11px] font-medium text-[var(--tt-fg-muted)] uppercase tracking-wider">
                Local energy
              </div>
              <div className="text-xl font-semibold text-[var(--tt-fg)] tabular">
                {loading ? <Skeleton className="h-7 w-20" /> : formatEnergy(totalEnergyWh)}
              </div>
            </div>
          </div>
        </Card>

        <Card padding="lg" className="border-emerald-500/25">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-md bg-emerald-500/15 text-emerald-400">
              <CheckCircle2 size={18} />
            </div>
            <div className="min-w-0">
              <div className="text-[11px] font-medium text-emerald-400/80 uppercase tracking-wider">
                Cloud savings
              </div>
              <div className="text-xl font-semibold text-emerald-400 tabular">
                {loading ? <Skeleton className="h-7 w-20" /> : `$${savingsUsd.toFixed(2)}`}
              </div>
              <div className="text-[10px] text-[var(--tt-fg-faint)] truncate" title={refModel}>
                vs {refModel}
              </div>
            </div>
          </div>
        </Card>

        <Card padding="lg">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-md bg-sky-500/10 text-sky-400">
              <Cloud size={18} />
            </div>
            <div className="min-w-0">
              <div className="text-[11px] font-medium text-[var(--tt-fg-muted)] uppercase tracking-wider">
                CO₂ (local)
              </div>
              <div className="text-xl font-semibold text-[var(--tt-fg)] tabular">
                {loading ? <Skeleton className="h-7 w-20" /> : formatCo2(co2g)}
              </div>
            </div>
          </div>
        </Card>

        <Card padding="lg">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-md bg-amber-500/10 text-amber-400">
              <Gauge size={18} />
            </div>
            <div className="min-w-0">
              <div className="text-[11px] font-medium text-[var(--tt-fg-muted)] uppercase tracking-wider">
                Avg throughput
              </div>
              <div className="text-xl font-semibold text-[var(--tt-fg)] tabular">
                {loading ? (
                  <Skeleton className="h-7 w-20" />
                ) : (
                  formatTokPerSec(avgTps ?? null)
                )}
              </div>
              <div className="text-[10px] text-[var(--tt-fg-faint)]">
                {formatWhPer1M(analytics?.local?.wh_per_1m_output ?? analytics?.total?.wh_per_1m_output)}
                {" "}/ 1M out
              </div>
            </div>
          </div>
        </Card>
      </div>

      <Card padding="none">
        <div className="px-5 py-4 border-b border-[var(--tt-border)] flex items-center justify-between gap-3">
          <CardTitle>
            <Cpu size={14} className="text-[var(--tt-brand)]" /> Local model efficiency
          </CardTitle>
          <div className="text-[10px] text-[var(--tt-fg-faint)] uppercase tracking-wider">
            Provider · tok/s · Wh/1M · savings
          </div>
        </div>
        <div className="overflow-x-auto max-h-[360px]">
          <Table>
            <THead>
              <TR>
                <TH className="pl-5">Model</TH>
                <TH className="text-right">Sessions</TH>
                <TH className="text-right">Tokens</TH>
                <TH className="text-right">Tok/s</TH>
                <TH className="text-right">Energy</TH>
                <TH className="text-right">Wh/1M</TH>
                <TH className="text-right pr-5">Savings</TH>
              </TR>
            </THead>
            <TBody>
              {loading ? (
                <TR>
                  <TD className="pl-5" colSpan={7}>
                    <Skeleton className="h-4 w-full" />
                  </TD>
                </TR>
              ) : modelRows.length > 0 ? (
                modelRows.map((row) => (
                  <TR key={row.name}>
                    <TD className="pl-5 font-mono text-[12px] text-[var(--tt-fg)] truncate max-w-[220px]" title={row.name}>
                      {row.name}
                      {row.quant ? (
                        <span className="ml-1.5 text-[10px] text-[var(--tt-fg-faint)]">{row.quant}</span>
                      ) : null}
                    </TD>
                    <TD className="text-right tabular text-[var(--tt-fg-muted)]">{row.session_count}</TD>
                    <TD className="text-right tabular text-[var(--tt-fg-muted)]">
                      {row.total_tokens.toLocaleString()}
                    </TD>
                    <TD className="text-right tabular text-[var(--tt-fg)]">
                      {formatTokPerSec(
                        row.avg_tok_per_sec ?? null,
                        (row.tok_per_sec_samples ?? 0) > 0 ? "measured" : "estimated",
                      )}
                    </TD>
                    <TD className="text-right tabular text-[var(--tt-fg-muted)]">
                      {formatEnergy(row.energy_wh)}
                    </TD>
                    <TD className="text-right tabular text-[var(--tt-fg-muted)]">
                      {formatWhPer1M(row.wh_per_1m_output)}
                    </TD>
                    <TD className="text-right pr-5 tabular font-semibold text-emerald-400">
                      ${(row.savings_usd || 0).toFixed(2)}
                    </TD>
                  </TR>
                ))
              ) : (
                <TR>
                  <TD colSpan={7} className="text-center py-6 text-[var(--tt-fg-muted)] text-[12px]">
                    No local models detected yet. Run an agent against Ollama, LM Studio, or
                    llama.cpp — or set an agent&apos;s billing mode to local in Settings.
                  </TD>
                </TR>
              )}
            </TBody>
          </Table>
        </div>
      </Card>
    </Section>
  );
}
