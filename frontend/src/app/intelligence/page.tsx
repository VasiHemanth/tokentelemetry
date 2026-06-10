"use client";

import { useState, useEffect } from "react";
import {
  Brain, Zap, AlertTriangle, TrendingUp, TrendingDown, Minus,
  GitBranch, GitCommit, Plus, Flame, DollarSign, Sparkles,
  BarChart3, Activity, CheckCircle, XCircle, AlertCircle,
  ArrowUpRight, Clock, Target, Wrench,
} from "lucide-react";
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid,
  Tooltip as ReTooltip, ResponsiveContainer, ReferenceLine, Cell,
} from "recharts";

import { useResource } from "@/lib/api";
import {
  PageHeader, Section, Card, CardTitle, Badge, Button, EmptyState,
} from "@/components/ui";

// ── Types ────────────────────────────────────────────────────────────────────

interface Recommendation {
  id: string;
  category: string;
  priority: "high" | "medium" | "low";
  title: string;
  detail: string;
  impact: string | null;
}
interface RecommendationsResponse {
  recommendations: Recommendation[];
  total: number;
  high_count: number;
  medium_count: number;
  low_count: number;
}

interface HealthComponents { efficiency: number; smell_free: number; recent_trend: number; cost_value: number; }
interface ProjectHealth {
  project: string;
  session_count: number;
  health_score: number;
  grade: string;
  avg_efficiency: number;
  smell_rate: number;
  recent_efficiency: number | null;
  trend: "up" | "flat" | "down" | null;
  cost_per_eff_pt: number | null;
  components: HealthComponents;
}
interface ProjectHealthResponse {
  projects: ProjectHealth[];
  total_projects: number;
  healthy_projects: number;
  at_risk_projects: number;
}

interface Anomaly {
  session_id: string;
  agent: string;
  model: string | null;
  project: string;
  timestamp: string;
  type: "cost_spike" | "efficiency_crash" | "token_overflow" | "waste";
  severity: "warning" | "critical";
  value: number;
  baseline: number;
  z_score: number | null;
  detail: string;
}
interface AnomalyResponse {
  anomalies: Anomaly[];
  total_anomalies: number;
  affected_sessions: number;
  sessions_checked: number;
  baseline: { mean_cost: number; mean_efficiency: number; mean_tokens: number; median_cost: number };
}

interface TrendDay { date: string; avg_efficiency: number; session_count: number; total_tokens: number; best: number; worst: number; rolling_7d: number | null; }
interface TrendsResponse {
  days: TrendDay[];
  trend: string;
  trend_delta: number;
  week_over_week: number;
  overall_avg: number | null;
  current_streak: number;
  best_day: { date: string; avg_efficiency: number } | null;
  worst_day: { date: string; avg_efficiency: number } | null;
  days_with_data: number;
  total_sessions: number;
}

interface ModelRow {
  model: string; agent: string; session_count: number;
  avg_efficiency: number; median_efficiency: number; p75_efficiency: number;
  best_efficiency: number; total_tokens: number; avg_tokens: number;
  task_breakdown: Record<string, { count: number; avg_efficiency: number }>;
}
interface ModelComparisonResponse {
  task_type_filter: string | null; models_compared: number; sessions_used: number; sessions_skipped: number;
  models: ModelRow[]; task_types_available: string[];
}

interface CostModelRow {
  model: string; agent: string; session_count: number;
  avg_cost: number; total_cost: number; avg_efficiency: number;
  cost_per_eff_pt: number | null; avg_cache_hit_pct: number | null;
}
interface CostCacheTier { tier: string; avg_efficiency: number; avg_cost: number; session_count: number; }
interface CostWasteful { session_id: string; model: string; cost: number; efficiency: number; task_type: string; waste_score: number; }
interface CostTaskRow { task_type: string; session_count: number; avg_cost: number; avg_efficiency: number; cost_per_eff_pt: number | null; }
interface CostIntelResponse {
  by_model: CostModelRow[]; by_task_type: CostTaskRow[]; cache_tiers: CostCacheTier[]; wasteful: CostWasteful[];
  best_value_model: string | null; total_cost: number; avg_cost_per_session: number;
  avg_cache_hit_pct: number | null; sessions_analysed: number; sessions_skipped: number;
}

interface TimeHourRow { hour: number; label: string; avg_efficiency: number; session_count: number; total_tokens: number; }
interface TimeDowRow { dow: number; label: string; avg_efficiency: number; session_count: number; }
interface TimeIntelResponse {
  by_hour: TimeHourRow[]; by_dow: TimeDowRow[];
  peak_hour: TimeHourRow | null; worst_hour: TimeHourRow | null;
  peak_dow: TimeDowRow | null; worst_dow: TimeDowRow | null; peak_period: string;
  sessions_analysed: number; sessions_skipped: number;
}

interface ToolSizeBucket { bucket: string; avg_efficiency: number; session_count: number; label: string; }
interface ToolRow { tool: string; session_count: number; avg_efficiency: number; category: string; }
interface ToolFootprintResponse {
  by_size: ToolSizeBucket[]; top_tools: ToolRow[];
  optimal_range: string | null; sessions_analysed: number; sessions_skipped: number;
}

interface DnaCorrelation { feature: string; label: string; r: number; direction: string; insight: string; }
interface PromptDnaResponse {
  sessions_analysed: number;
  correlations: DnaCorrelation[];
  by_task_type: Record<string, { avg_efficiency: number; count: number }>;
  top_positive: DnaCorrelation[];
  top_negative: DnaCorrelation[];
}

interface GitProjectSummary {
  project: string; branch: string | null; session_count: number;
  total_files_changed: number; total_lines_added: number; total_lines_deleted: number;
  net_lines: number; latest_commit_sha: string | null; latest_commit_msg: string | null;
  latest_commit_time: string | null; avg_files_per_session: number;
}
interface GitSummaryResponse {
  projects: GitProjectSummary[]; total_lines_added: number; total_lines_deleted: number;
  total_files_changed: number; git_sessions: number; non_git_sessions: number;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const effColor  = (v: number) => v >= 70 ? "#4ade80" : v >= 40 ? "#facc15" : "#f87171";
const barFill   = effColor;
const fmtCost   = (v: number) => v >= 1 ? `$${v.toFixed(2)}` : `$${v.toFixed(4)}`;
const fmtCpp    = (v: number | null) => v === null ? "—" : v < 0.01 ? `$${v.toFixed(5)}/pt` : `$${v.toFixed(3)}/pt`;
const shortProj = (p: string) => p.split(/[/\\]/).pop() || p;

const PRIORITY_COLOR: Record<string, string> = {
  high: "#f87171", medium: "#facc15", low: "#4ade80",
};
const CAT_ICON: Record<string, React.ReactNode> = {
  cost:    <DollarSign size={13} />,
  quality: <Target size={13} />,
  timing:  <Clock size={13} />,
  prompt:  <Sparkles size={13} />,
  tools:   <Wrench size={13} />,
  health:  <Activity size={13} />,
};
const ANOMALY_ICON: Record<string, React.ReactNode> = {
  cost_spike:       <DollarSign size={13} className="text-red-400" />,
  efficiency_crash: <TrendingDown size={13} className="text-red-400" />,
  token_overflow:   <Zap size={13} className="text-yellow-400" />,
  waste:            <AlertTriangle size={13} className="text-red-400" />,
};
const GRADE_COLOR: Record<string, string> = {
  A: "#4ade80", B: "#60a5fa", C: "#facc15", D: "#fb923c", F: "#f87171",
};

// ── Page ──────────────────────────────────────────────────────────────────────

export default function IntelligencePage() {
  const recRes    = useResource<RecommendationsResponse>("/insights/recommendations", { pollMs: 120_000 });
  const healthRes = useResource<ProjectHealthResponse>("/insights/project-health", { pollMs: 120_000 });
  const anomalyRes = useResource<AnomalyResponse>("/insights/anomalies", { pollMs: 60_000 });
  const dnaRes    = useResource<PromptDnaResponse>("/insights/prompt-dna", { pollMs: 120_000 });
  const gitRes    = useResource<GitSummaryResponse>("/insights/git-summary", { pollMs: 60_000 });
  const timeRes   = useResource<TimeIntelResponse>("/insights/time", { pollMs: 120_000 });
  const toolRes   = useResource<ToolFootprintResponse>("/insights/tool-footprint", { pollMs: 120_000 });
  const costRes   = useResource<CostIntelResponse>("/insights/cost", { pollMs: 120_000 });

  const [trendsDays, setTrendsDays] = useState<30 | 60>(30);
  const trendsRes = useResource<TrendsResponse>(`/insights/trends?days=${trendsDays}`, { pollMs: 120_000 });

  const [modelTaskFilter, setModelTaskFilter] = useState<string>("all");
  const [modelComparison, setModelComparison] = useState<ModelComparisonResponse | null>(null);
  useEffect(() => {
    const url = modelTaskFilter === "all"
      ? "/insights/model-comparison"
      : `/insights/model-comparison?task_type=${modelTaskFilter}`;
    fetch(`http://localhost:8000${url}`)
      .then(r => r.json())
      .then(d => setModelComparison(d))
      .catch(() => {});
  }, [modelTaskFilter]);

  const periodEmoji: Record<string, string> = { morning: "🌅", afternoon: "☀️", evening: "🌆", night: "🌙" };

  const sizeColor: Record<string, string> = { lean: "#4ade80", standard: "#60a5fa", heavy: "#facc15", bloated: "#f87171" };
  const catColor: Record<string, string>  = { core: "#4ade80", agent: "#a78bfa", browser: "#60a5fa", mcp: "#fb923c", meta: "#94a3b8" };

  const shortTool = (t: string) => {
    if (t.startsWith("mcp__")) {
      const parts = t.split("__");
      return parts[parts.length - 1].replace(/_/g, " ");
    }
    return t;
  };

  const formatDate = (d: string) => {
    const dt = new Date(d + "T12:00:00Z");
    return dt.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  };

  return (
    <div className="px-8 py-8 max-w-[1600px] mx-auto space-y-10 pb-20">
      <PageHeader
        eyebrow="Intelligence Layer"
        title="Intelligence"
        description="Cross-session analytics, recommendations, and health signals across all your AI coding agents."
        icon={<Brain size={20} strokeWidth={2.25} />}
        actions={
          <Badge variant="success" size="sm" className="h-9 px-2.5">
            <span className="relative flex w-1.5 h-1.5">
              <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
              <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-400" />
            </span>
            Live
          </Badge>
        }
      />

      {/* ── Recommendations ──────────────────────────────────────── */}
      {(recRes.data?.total ?? 0) > 0 && (
        <Section
          title="Recommendations"
          description={`${recRes.data!.total} actionable insights · ${recRes.data!.high_count} high priority`}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {recRes.data!.recommendations.map((rec) => (
              <Card key={rec.id} className="space-y-2.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span style={{ color: PRIORITY_COLOR[rec.priority] ?? "#94a3b8" }}>
                      {CAT_ICON[rec.category] ?? <Activity size={13} />}
                    </span>
                    <span
                      className="text-[10px] px-1.5 py-0.5 rounded-full capitalize font-semibold"
                      style={{
                        background: (PRIORITY_COLOR[rec.priority] ?? "#94a3b8") + "22",
                        color: PRIORITY_COLOR[rec.priority] ?? "#94a3b8",
                      }}
                    >
                      {rec.priority}
                    </span>
                    <span className="text-[10px] text-[var(--tt-fg-faint)] capitalize">{rec.category}</span>
                  </div>
                  {rec.impact && (
                    <span className="text-[10px] text-emerald-400 font-semibold shrink-0">{rec.impact}</span>
                  )}
                </div>
                <div className="text-[13px] font-semibold text-[var(--tt-fg)] leading-snug">{rec.title}</div>
                <div className="text-[11px] text-[var(--tt-fg-muted)] leading-relaxed">{rec.detail}</div>
              </Card>
            ))}
          </div>
        </Section>
      )}

      {/* ── Project Health ────────────────────────────────────────── */}
      {(healthRes.data?.total_projects ?? 0) >= 2 && (
        <Section
          title="Project health"
          description={`${healthRes.data!.total_projects} projects · ${healthRes.data!.healthy_projects} healthy · ${healthRes.data!.at_risk_projects} at risk`}
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {healthRes.data!.projects.map((p) => {
              const gc = GRADE_COLOR[p.grade] ?? "#94a3b8";
              return (
                <Card key={p.project} className="space-y-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="font-mono text-[11px] font-semibold text-[var(--tt-fg)] truncate" title={p.project}>
                        {shortProj(p.project)}
                      </div>
                      <div className="text-[10px] text-[var(--tt-fg-faint)] mt-0.5">{p.session_count} sessions</div>
                    </div>
                    <div
                      className="shrink-0 w-10 h-10 rounded-xl flex flex-col items-center justify-center font-bold text-lg leading-none"
                      style={{ background: gc + "22", color: gc, border: `1.5px solid ${gc}44` }}
                    >
                      <span>{p.grade}</span>
                      <span className="text-[9px] font-normal opacity-70">{p.health_score.toFixed(0)}</span>
                    </div>
                  </div>

                  {/* Score bar */}
                  <div className="h-1.5 bg-[var(--tt-surface-raised)] rounded overflow-hidden">
                    <div
                      className="h-full rounded transition-all"
                      style={{ width: `${p.health_score}%`, background: gc, opacity: 0.8 }}
                    />
                  </div>

                  {/* Components */}
                  <div className="grid grid-cols-2 gap-x-3 gap-y-1">
                    {([
                      ["Efficiency", p.components.efficiency],
                      ["Smell-free", p.components.smell_free],
                      ["Trend",      p.components.recent_trend],
                      ["Cost value", p.components.cost_value],
                    ] as [string, number][]).map(([label, val]) => (
                      <div key={label} className="flex items-center justify-between text-[10px]">
                        <span className="text-[var(--tt-fg-faint)]">{label}</span>
                        <span className="font-mono tabular" style={{ color: effColor(val) }}>{val.toFixed(0)}</span>
                      </div>
                    ))}
                  </div>

                  {/* Trend badge */}
                  {p.trend && (
                    <div className="flex items-center gap-1.5 text-[10px]">
                      {p.trend === "up"   && <TrendingUp  size={10} className="text-emerald-400" />}
                      {p.trend === "down" && <TrendingDown size={10} className="text-red-400" />}
                      {p.trend === "flat" && <Minus size={10} className="text-[var(--tt-fg-faint)]" />}
                      <span className="text-[var(--tt-fg-muted)]">
                        {p.recent_efficiency !== null ? `${p.recent_efficiency} recent` : "no recent data"}
                      </span>
                    </div>
                  )}
                </Card>
              );
            })}
          </div>
        </Section>
      )}

      {/* ── Anomaly Detection ─────────────────────────────────────── */}
      {(anomalyRes.data?.total_anomalies ?? 0) > 0 && (
        <Section
          title="Anomaly detection"
          description={`${anomalyRes.data!.total_anomalies} signals across ${anomalyRes.data!.affected_sessions ?? anomalyRes.data!.total_anomalies} sessions · ${anomalyRes.data!.sessions_checked} checked`}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {anomalyRes.data!.anomalies.map((a, i) => (
              <Card key={`${a.session_id}-${a.type}-${i}`} className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    {ANOMALY_ICON[a.type] ?? <AlertCircle size={13} className="text-yellow-400" />}
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded-full font-semibold capitalize ${
                        a.severity === "critical"
                          ? "bg-red-500/20 text-red-400"
                          : "bg-yellow-500/20 text-yellow-400"
                      }`}
                    >
                      {a.severity}
                    </span>
                    <span className="text-[10px] text-[var(--tt-fg-faint)] capitalize">
                      {a.type.replace(/_/g, " ")}
                    </span>
                  </div>
                  {a.z_score !== null && (
                    <span className="text-[10px] font-mono text-[var(--tt-fg-faint)]">{a.z_score.toFixed(1)}σ</span>
                  )}
                </div>
                <div className="text-[12px] text-[var(--tt-fg)] leading-snug">{a.detail}</div>
                <div className="flex items-center gap-3 text-[10px] text-[var(--tt-fg-faint)]">
                  <span className="font-mono">{a.session_id.slice(0, 8)}</span>
                  {a.model && <span className="truncate">{a.model}</span>}
                  <span className="ml-auto truncate">{shortProj(a.project)}</span>
                </div>
              </Card>
            ))}
          </div>
        </Section>
      )}

      {/* ── Session Trends ────────────────────────────────────────── */}
      {(trendsRes.data?.days_with_data ?? 0) >= 2 && (() => {
        const td = trendsRes.data!;
        const trendColor = td.trend === "improving" ? "#4ade80" : td.trend === "declining" ? "#f87171" : td.trend === "new" ? "#60a5fa" : "#facc15";
        const trendIcon  = td.trend === "improving" ? "↑" : td.trend === "declining" ? "↓" : td.trend === "new" ? "✦" : "→";
        return (
          <Section
            title="Session trends"
            description={`Efficiency over the last ${trendsDays} days · ${td.days_with_data} active days · ${td.total_sessions} sessions`}
          >
            <Card className="space-y-4">
              <div className="flex flex-wrap items-center gap-3">
                <div
                  className="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold"
                  style={{ background: trendColor + "22", color: trendColor, border: `1px solid ${trendColor}44` }}
                >
                  <span className="text-sm leading-none">{trendIcon}</span>
                  <span className="capitalize">{td.trend}</span>
                  {Math.abs(td.trend_delta) >= 1 && (
                    <span className="opacity-80 font-mono">{td.trend_delta > 0 ? "+" : ""}{td.trend_delta.toFixed(1)} pts WoW</span>
                  )}
                </div>
                {td.overall_avg !== null && (
                  <div className="text-xs text-[var(--tt-fg-muted)] px-2 py-1 rounded bg-[var(--tt-surface-raised)]">
                    Avg <span className="font-semibold text-[var(--tt-fg)]">{td.overall_avg.toFixed(1)}</span>
                  </div>
                )}
                {td.current_streak >= 2 && (
                  <div className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-[var(--tt-surface-raised)] text-amber-400">
                    <Flame size={11} /><span className="font-semibold">{td.current_streak}d</span>
                    <span className="text-[var(--tt-fg-faint)]">streak</span>
                  </div>
                )}
                {td.best_day && (
                  <div className="text-xs text-[var(--tt-fg-muted)] px-2 py-1 rounded bg-[var(--tt-surface-raised)]">
                    Best <span className="font-semibold text-emerald-400">{td.best_day.avg_efficiency.toFixed(1)}</span>
                    <span className="ml-1 text-[var(--tt-fg-faint)]">on {formatDate(td.best_day.date)}</span>
                  </div>
                )}
                <div className="ml-auto flex items-center gap-1 text-xs">
                  {([30, 60] as const).map((n) => (
                    <button key={n} onClick={() => setTrendsDays(n)} className="px-2.5 py-1 rounded transition-colors"
                      style={{
                        background: trendsDays === n ? "var(--tt-brand)" : "var(--tt-surface-raised)",
                        color: trendsDays === n ? "var(--tt-bg)" : "var(--tt-fg-muted)",
                        fontWeight: trendsDays === n ? 600 : 400,
                      }}>{n}d</button>
                  ))}
                </div>
              </div>
              <div style={{ height: 200 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={td.days} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--tt-border)" vertical={false} />
                    <XAxis dataKey="date" tickFormatter={formatDate} tick={{ fill: "var(--tt-fg-faint)", fontSize: 10 }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                    <YAxis domain={[0, 100]} tick={{ fill: "var(--tt-fg-faint)", fontSize: 10 }} tickLine={false} axisLine={false} tickCount={5} />
                    <ReTooltip contentStyle={{ background: "var(--tt-surface)", border: "1px solid var(--tt-border)", borderRadius: 8, fontSize: 12, color: "var(--tt-fg)" }}
                      labelFormatter={(l) => formatDate(String(l))}
                      formatter={(value, name) => {
                        const v = typeof value === "number" ? value.toFixed(1) : String(value);
                        return [v, name === "avg_efficiency" ? "Avg efficiency" : "7d rolling avg"];
                      }} />
                    <ReferenceLine y={60} stroke="var(--tt-fg-faint)" strokeDasharray="4 4" strokeOpacity={0.5} />
                    <Bar dataKey="avg_efficiency" radius={[3, 3, 0, 0]} maxBarSize={32}>
                      {td.days.map((day) => <Cell key={day.date} fill={barFill(day.avg_efficiency)} fillOpacity={0.85} />)}
                    </Bar>
                    <Line type="monotone" dataKey="rolling_7d" stroke="var(--tt-brand)" strokeWidth={2} dot={false} connectNulls />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
              <div className="flex items-center gap-4 text-[10px] text-[var(--tt-fg-faint)]">
                {[["#4ade80","Good (≥70)"],["#facc15","Fair (40–69)"],["#f87171","Poor (<40)"]].map(([c,l])=>(
                  <div key={l} className="flex items-center gap-1.5"><div className="w-3 h-3 rounded-sm opacity-85" style={{background:c}}/>{l}</div>
                ))}
                <div className="flex items-center gap-1.5 ml-2">
                  <div className="w-6 h-0.5 rounded" style={{background:"var(--tt-brand)"}}/> 7d rolling avg
                </div>
              </div>
            </Card>
          </Section>
        );
      })()}

      {/* ── Model Comparison ──────────────────────────────────────── */}
      {modelComparison && modelComparison.models_compared > 0 && (
        <Section
          title="Model comparison"
          description={`${modelComparison.models_compared} models · ${modelComparison.sessions_used} sessions`}
        >
          <Card className="space-y-4">
            {/* Task filter pills */}
            <div className="flex flex-wrap gap-1.5">
              {["all", ...(modelComparison.task_types_available ?? [])].map((tt) => (
                <button key={tt} onClick={() => setModelTaskFilter(tt)}
                  className="px-2.5 py-1 rounded-full text-[11px] font-medium capitalize transition-colors"
                  style={{
                    background: modelTaskFilter === tt ? "var(--tt-brand)" : "var(--tt-surface-raised)",
                    color: modelTaskFilter === tt ? "var(--tt-bg)" : "var(--tt-fg-muted)",
                  }}>{tt === "all" ? "All tasks" : tt}</button>
              ))}
            </div>
            {/* Model rows */}
            <div className="space-y-3">
              {modelComparison.models.map((m, i) => (
                <div key={m.model} className="space-y-1.5">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-[var(--tt-fg-faint)] w-4 tabular shrink-0">#{i + 1}</span>
                    <span className="font-mono text-[12px] text-[var(--tt-fg)] flex-1 truncate">{m.model}</span>
                    <span className="text-[10px] text-[var(--tt-fg-faint)]">×{m.session_count}</span>
                    <span className="font-mono text-[12px] tabular shrink-0" style={{ color: effColor(m.avg_efficiency) }}>{m.avg_efficiency.toFixed(1)}</span>
                  </div>
                  <div className="flex gap-1 h-2">
                    <div className="flex-1 bg-[var(--tt-surface-raised)] rounded overflow-hidden">
                      <div className="h-full rounded" style={{ width: `${m.avg_efficiency}%`, background: effColor(m.avg_efficiency), opacity: 0.7 }} />
                    </div>
                    <div className="flex-1 bg-[var(--tt-surface-raised)] rounded overflow-hidden">
                      <div className="h-full rounded" style={{ width: `${m.p75_efficiency}%`, background: effColor(m.p75_efficiency), opacity: 0.45 }} />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </Section>
      )}

      {/* ── Prompt DNA ────────────────────────────────────────────── */}
      {dnaRes.data && dnaRes.data.sessions_analysed >= 3 && (
        <Section
          title="Prompt DNA"
          description={`${dnaRes.data.sessions_analysed} sessions analysed · prompt structure vs efficiency correlations`}
        >
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card className="space-y-3">
              <div className="text-xs font-semibold text-emerald-400 uppercase tracking-wide">Boosts efficiency</div>
              <div className="space-y-2">
                {dnaRes.data.top_positive.slice(0, 3).map((c) => (
                  <div key={c.feature} className="space-y-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-[var(--tt-fg-muted)]">{c.label}</span>
                      <span className="font-mono text-emerald-400">r={c.r.toFixed(2)}</span>
                    </div>
                    <div className="text-[11px] text-[var(--tt-fg-faint)]">{c.insight}</div>
                  </div>
                ))}
              </div>
            </Card>
            <Card className="space-y-3">
              <div className="text-xs font-semibold text-red-400 uppercase tracking-wide">Hurts efficiency</div>
              <div className="space-y-2">
                {dnaRes.data.top_negative.slice(0, 3).map((c) => (
                  <div key={c.feature} className="space-y-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-[var(--tt-fg-muted)]">{c.label}</span>
                      <span className="font-mono text-red-400">r={c.r.toFixed(2)}</span>
                    </div>
                    <div className="text-[11px] text-[var(--tt-fg-faint)]">{c.insight}</div>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </Section>
      )}

      {/* ── Cost Intelligence ─────────────────────────────────────── */}
      {(costRes.data?.sessions_analysed ?? 0) >= 2 && (() => {
        const ci = costRes.data!;
        const maxCpp = Math.max(...ci.by_model.filter(r => r.cost_per_eff_pt !== null).map(r => r.cost_per_eff_pt as number), 0.001);
        return (
          <Section
            title="Cost intelligence"
            description={`${fmtCost(ci.total_cost)} total · ${ci.sessions_analysed} sessions · ${ci.avg_cache_hit_pct?.toFixed(0) ?? "—"}% avg cache hit`}
          >
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <Card className="space-y-3">
                <div className="text-xs font-semibold text-[var(--tt-fg-dim)] uppercase tracking-wide">
                  Cost per efficiency point <span className="normal-case font-normal text-[var(--tt-fg-faint)]">(lower = better)</span>
                </div>
                <div className="space-y-2.5">
                  {ci.by_model.map((m) => (
                    <div key={m.model} className="space-y-1">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1.5 min-w-0">
                          <span className="font-mono text-[11px] text-[var(--tt-fg)] truncate">{m.model}</span>
                          <span className="text-[10px] text-[var(--tt-fg-faint)]">×{m.session_count}</span>
                        </div>
                        <div className="flex items-center gap-3 shrink-0 ml-2">
                          <span className="text-[10px]" style={{ color: effColor(m.avg_efficiency) }}>{m.avg_efficiency.toFixed(1)} eff</span>
                          <span className="text-[11px] font-mono tabular">{fmtCpp(m.cost_per_eff_pt)}</span>
                        </div>
                      </div>
                      {m.cost_per_eff_pt !== null && (
                        <div className="h-1.5 bg-[var(--tt-surface-raised)] rounded overflow-hidden">
                          <div className="h-full rounded" style={{
                            width: `${Math.min((m.cost_per_eff_pt / maxCpp) * 100, 100)}%`,
                            background: m.cost_per_eff_pt / maxCpp < 0.3 ? "#4ade80" : m.cost_per_eff_pt / maxCpp < 0.7 ? "#facc15" : "#f87171",
                            opacity: 0.8,
                          }} />
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </Card>
              <div className="space-y-4">
                {ci.cache_tiers.length >= 2 && (
                  <Card className="space-y-3">
                    <div className="text-xs font-semibold text-[var(--tt-fg-dim)] uppercase tracking-wide">Cache hit rate vs efficiency</div>
                    <div className="space-y-1.5">
                      {ci.cache_tiers.map((t) => (
                        <div key={t.tier} className="flex items-center gap-2">
                          <div className="w-16 text-[10px] text-[var(--tt-fg-faint)] tabular shrink-0">{t.tier}</div>
                          <div className="flex-1 h-4 bg-[var(--tt-surface-raised)] rounded overflow-hidden">
                            <div className="h-full rounded" style={{ width: `${t.avg_efficiency}%`, background: effColor(t.avg_efficiency), opacity: 0.75 }} />
                          </div>
                          <span className="text-[11px] font-mono w-8 text-right tabular" style={{ color: effColor(t.avg_efficiency) }}>{t.avg_efficiency.toFixed(0)}</span>
                          <span className="text-[10px] text-[var(--tt-fg-faint)] w-14 text-right tabular shrink-0">{fmtCost(t.avg_cost)}</span>
                          <span className="text-[10px] text-[var(--tt-fg-faint)] shrink-0">×{t.session_count}</span>
                        </div>
                      ))}
                    </div>
                  </Card>
                )}
                {ci.wasteful.length > 0 && (
                  <Card className="space-y-3">
                    <div className="text-xs font-semibold text-[var(--tt-fg-dim)] uppercase tracking-wide flex items-center gap-1.5">
                      <AlertTriangle size={11} className="text-red-400" /> Expensive flops
                    </div>
                    <div className="space-y-2">
                      {ci.wasteful.map((w) => (
                        <div key={w.session_id} className="flex items-center gap-2 py-1 border-b border-[var(--tt-border)] last:border-0">
                          <span className="font-mono text-[10px] text-[var(--tt-fg-faint)] shrink-0">{w.session_id.slice(0, 8)}</span>
                          <span className="font-mono text-[10px] text-[var(--tt-fg)] truncate flex-1">{w.model}</span>
                          <span className="text-[11px] font-mono text-red-400 tabular shrink-0">{fmtCost(w.cost)}</span>
                          <span className="text-[10px] tabular shrink-0" style={{ color: effColor(w.efficiency) }}>{w.efficiency.toFixed(1)}</span>
                        </div>
                      ))}
                    </div>
                  </Card>
                )}
              </div>
            </div>
          </Section>
        );
      })()}

      {/* ── Time Intelligence ─────────────────────────────────────── */}
      {(timeRes.data?.sessions_analysed ?? 0) >= 3 && (() => {
        const ti = timeRes.data!;
        return (
          <Section title="Time intelligence" description={`When you code best · ${ti.sessions_analysed} sessions`}>
            <div className="flex flex-wrap gap-3 mb-4">
              {ti.peak_hour && (
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[var(--tt-surface-raised)] text-xs">
                  <span className="text-emerald-400 font-semibold">Peak hour</span>
                  <span className="font-mono text-[var(--tt-fg)]">{ti.peak_hour.label}</span>
                  <span className="text-[var(--tt-fg-faint)]">{ti.peak_hour.avg_efficiency.toFixed(1)} avg</span>
                </div>
              )}
              {ti.peak_dow && (
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[var(--tt-surface-raised)] text-xs">
                  <span className="text-emerald-400 font-semibold">Peak day</span>
                  <span className="font-mono text-[var(--tt-fg)]">{ti.peak_dow.label}</span>
                  <span className="text-[var(--tt-fg-faint)]">{ti.peak_dow.avg_efficiency.toFixed(1)} avg</span>
                </div>
              )}
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[var(--tt-surface-raised)] text-xs">
                <span className="text-[var(--tt-fg-muted)]">Best period</span>
                <span className="font-semibold capitalize">{periodEmoji[ti.peak_period] ?? ""} {ti.peak_period}</span>
              </div>
              {ti.worst_hour && (
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[var(--tt-surface-raised)] text-xs">
                  <span className="text-red-400 font-semibold">Avoid</span>
                  <span className="font-mono text-[var(--tt-fg)]">{ti.worst_hour.label}</span>
                  <span className="text-[var(--tt-fg-faint)]">{ti.worst_hour.avg_efficiency.toFixed(1)} avg</span>
                </div>
              )}
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <Card className="space-y-2">
                <div className="text-xs font-semibold text-[var(--tt-fg-dim)] uppercase tracking-wide">By hour of day</div>
                <div style={{ height: 180 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={ti.by_hour} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--tt-border)" vertical={false} />
                      <XAxis dataKey="label" tick={{ fill: "var(--tt-fg-faint)", fontSize: 9 }} tickLine={false} axisLine={false} interval={0} angle={-45} textAnchor="end" height={36} />
                      <YAxis domain={[0, 100]} tick={{ fill: "var(--tt-fg-faint)", fontSize: 9 }} tickLine={false} axisLine={false} tickCount={4} />
                      <ReTooltip contentStyle={{ background: "var(--tt-surface)", border: "1px solid var(--tt-border)", borderRadius: 8, fontSize: 11, color: "var(--tt-fg)" }}
                        formatter={(v, n) => [typeof v === "number" ? v.toFixed(1) : v, n === "avg_efficiency" ? "Avg efficiency" : String(n)]} />
                      <ReferenceLine y={60} stroke="var(--tt-fg-faint)" strokeDasharray="4 4" strokeOpacity={0.4} />
                      <Bar dataKey="avg_efficiency" radius={[3, 3, 0, 0]} maxBarSize={28}>
                        {ti.by_hour.map((row) => <Cell key={row.hour} fill={barFill(row.avg_efficiency)} fillOpacity={0.85} />)}
                      </Bar>
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </Card>
              <Card className="space-y-2">
                <div className="text-xs font-semibold text-[var(--tt-fg-dim)] uppercase tracking-wide">By day of week</div>
                <div style={{ height: 180 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={ti.by_dow} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--tt-border)" vertical={false} />
                      <XAxis dataKey="label" tick={{ fill: "var(--tt-fg-faint)", fontSize: 10 }} tickLine={false} axisLine={false} />
                      <YAxis domain={[0, 100]} tick={{ fill: "var(--tt-fg-faint)", fontSize: 9 }} tickLine={false} axisLine={false} tickCount={4} />
                      <ReTooltip contentStyle={{ background: "var(--tt-surface)", border: "1px solid var(--tt-border)", borderRadius: 8, fontSize: 11, color: "var(--tt-fg)" }}
                        formatter={(v, n) => [typeof v === "number" ? v.toFixed(1) : v, n === "avg_efficiency" ? "Avg efficiency" : String(n)]} />
                      <ReferenceLine y={60} stroke="var(--tt-fg-faint)" strokeDasharray="4 4" strokeOpacity={0.4} />
                      <Bar dataKey="avg_efficiency" radius={[3, 3, 0, 0]} maxBarSize={40}>
                        {ti.by_dow.map((row) => <Cell key={row.dow} fill={barFill(row.avg_efficiency)} fillOpacity={0.85} />)}
                      </Bar>
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </Card>
            </div>
          </Section>
        );
      })()}

      {/* ── Tool Footprint ────────────────────────────────────────── */}
      {(toolRes.data?.sessions_analysed ?? 0) >= 3 && (() => {
        const tf = toolRes.data!;
        return (
          <Section title="Tool footprint" description={`Toolset size and composition vs efficiency · ${tf.sessions_analysed} sessions`}>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <Card className="space-y-3">
                <div className="text-xs font-semibold text-[var(--tt-fg-dim)] uppercase tracking-wide">
                  Efficiency by toolset size
                  {tf.optimal_range && <span className="ml-2 normal-case font-normal text-[var(--tt-fg-faint)]">· optimal: <span className="font-semibold text-[var(--tt-fg)]">{tf.optimal_range} tools</span></span>}
                </div>
                <div className="space-y-2">
                  {tf.by_size.map((b) => (
                    <div key={b.bucket} className="flex items-center gap-2">
                      <div className="w-16 text-[11px] text-[var(--tt-fg-muted)] tabular shrink-0">{b.bucket}</div>
                      <div className="flex-1 h-5 bg-[var(--tt-surface-raised)] rounded overflow-hidden">
                        <div className="h-full rounded" style={{ width: `${b.avg_efficiency}%`, background: sizeColor[b.label] ?? "#60a5fa", opacity: 0.8 }} />
                      </div>
                      <div className="w-10 text-right text-[11px] font-mono tabular shrink-0">{b.avg_efficiency.toFixed(1)}</div>
                      <div className="w-8 text-right text-[10px] text-[var(--tt-fg-faint)] tabular shrink-0">{b.session_count}s</div>
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full capitalize shrink-0"
                        style={{ background: (sizeColor[b.label] ?? "#60a5fa") + "22", color: sizeColor[b.label] ?? "#60a5fa" }}>{b.label}</span>
                    </div>
                  ))}
                </div>
              </Card>
              <Card className="space-y-3">
                <div className="text-xs font-semibold text-[var(--tt-fg-dim)] uppercase tracking-wide">Top tools by frequency</div>
                <div className="space-y-1 overflow-y-auto" style={{ maxHeight: 220 }}>
                  {tf.top_tools.map((t, i) => (
                    <div key={t.tool} className="flex items-center gap-2 py-1 border-b border-[var(--tt-border)] last:border-0">
                      <span className="text-[10px] text-[var(--tt-fg-faint)] w-4 tabular shrink-0">{i + 1}</span>
                      <span className="text-[10px] px-1 py-0.5 rounded shrink-0 capitalize"
                        style={{ background: (catColor[t.category] ?? "#94a3b8") + "22", color: catColor[t.category] ?? "#94a3b8" }}>{t.category}</span>
                      <span className="text-[11px] truncate flex-1 font-mono" title={t.tool}>{shortTool(t.tool)}</span>
                      <span className="text-[10px] text-[var(--tt-fg-faint)] tabular shrink-0">{t.session_count}s</span>
                      <span className="text-[10px] font-mono tabular shrink-0 w-10 text-right"
                        style={{ color: effColor(t.avg_efficiency) }}>{t.avg_efficiency.toFixed(1)}</span>
                    </div>
                  ))}
                </div>
              </Card>
            </div>
          </Section>
        );
      })()}

      {/* ── Repository Activity ───────────────────────────────────── */}
      {(gitRes.data?.git_sessions ?? 0) > 0 && (
        <Section
          title="Repository activity"
          description={`${gitRes.data!.git_sessions} git-tracked sessions · +${gitRes.data!.total_lines_added.toLocaleString()} / −${gitRes.data!.total_lines_deleted.toLocaleString()} lines across ${gitRes.data!.projects.length} repos`}
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {gitRes.data!.projects.filter(p => p.session_count > 0).map((p) => {
              const projName = p.project.split(/[/\\]/).pop() || p.project;
              const hasStats = p.total_lines_added > 0 || p.total_lines_deleted > 0;
              const netColor = p.net_lines > 0 ? "#4ade80" : p.net_lines < 0 ? "#f87171" : "var(--tt-fg-faint)";
              return (
                <Card key={p.project} className="space-y-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="font-mono text-[12px] font-semibold text-[var(--tt-fg)] truncate" title={p.project}>{projName}</div>
                      {p.branch && (
                        <div className="flex items-center gap-1 mt-0.5 text-[10px] text-[var(--tt-fg-faint)]">
                          <GitBranch size={9} /><span className="truncate">{p.branch}</span>
                        </div>
                      )}
                    </div>
                    <span className="text-[10px] tabular text-[var(--tt-fg-dim)] whitespace-nowrap shrink-0">{p.session_count} sess</span>
                  </div>
                  {p.latest_commit_sha && (
                    <div className="flex items-start gap-1.5">
                      <GitCommit size={10} className="text-[var(--tt-fg-faint)] mt-0.5 shrink-0" />
                      <div className="min-w-0">
                        <span className="font-mono text-[10px] text-[var(--tt-brand)]">{p.latest_commit_sha}</span>
                        {p.latest_commit_time && <span className="ml-1.5 text-[10px] text-[var(--tt-fg-faint)]">{new Date(p.latest_commit_time).toLocaleDateString("en-US", { month: "short", day: "numeric" })}</span>}
                        <span className="mt-0.5 text-[10px] text-[var(--tt-fg-muted)] truncate block" title={p.latest_commit_msg ?? ""}>{p.latest_commit_msg}</span>
                      </div>
                    </div>
                  )}
                  {hasStats && (
                    <div className="flex items-center gap-3 pt-1 border-t border-[var(--tt-border)]">
                      <div className="flex items-center gap-1 text-[10px] text-emerald-400"><Plus size={9}/><span className="tabular">{p.total_lines_added.toLocaleString()}</span></div>
                      <div className="flex items-center gap-1 text-[10px] text-red-400"><Minus size={9}/><span className="tabular">{p.total_lines_deleted.toLocaleString()}</span></div>
                      <div className="flex items-center gap-1 text-[10px]" style={{ color: netColor }}>
                        <span className="tabular font-medium">{p.net_lines > 0 ? "+" : ""}{p.net_lines.toLocaleString()} net</span>
                      </div>
                      <div className="ml-auto text-[10px] text-[var(--tt-fg-faint)] tabular">{p.total_files_changed} files</div>
                    </div>
                  )}
                </Card>
              );
            })}
          </div>
        </Section>
      )}
    </div>
  );
}
