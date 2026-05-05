"use client";

import { useEffect, useState } from "react";
import { Activity, Clock, Database, Terminal, Sparkles, TrendingUp, Cpu, Zap, GitBranch, Orbit, ArrowRight, MousePointer2, Code2, Layers, Target, RotateCcw } from "lucide-react";
import { format } from "date-fns";
import Link from "next/link";

interface Session {
  id: string;
  agent: string;
  project: string;
  timestamp: string;
  display?: string;
  text?: string;
  tokens?: {
    input: number;
    output: number;
    cached: number;
    total: number;
  };
  cost?: number;
}

const AGENT_CONFIG: Record<string, { label: string, color: string, icon: any }> = {
  claude: { label: "Claude", color: "orange", icon: Terminal },
  codex: { label: "Codex", color: "purple", icon: Database },
  gemini: { label: "Gemini", color: "cyan", icon: Sparkles },
  antigravity: { label: "Antigravity", color: "emerald", icon: Orbit },
  qwen: { label: "Qwen", color: "blue", icon: Cpu },
  vibe: { label: "Vibe", color: "pink", icon: Zap },
  cursor: { label: "Cursor", color: "blue", icon: MousePointer2 },
  // ollama: { label: "Ollama", color: "blue", icon: Zap },
  copilot: { label: "Copilot", color: "indigo", icon: GitBranch },
  opencode: { label: "OpenCode", color: "amber", icon: Code2 }
};

const AGENT_HEX: Record<string, string> = {
  claude: "#f97316", codex: "#a855f7", gemini: "#06b6d4",
  antigravity: "#10b981", qwen: "#3b82f6", vibe: "#f472b6", cursor: "#3b82f6", copilot: "#6366f1", opencode: "#f59e0b"
};

interface QualityTotals {
  edit_turns: number;
  retry_turns: number;
  one_shot_rate: number | null;
  retry_rate: number | null;
  measured_sessions: number;
}
interface AnalyticsTotals {
  cache_hit_pct: number | null;
  quality: QualityTotals;
}

export default function Home() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [availableAgents, setAvailableAgents] = useState<string[]>([]);
  const [byModel, setByModel] = useState<Record<string, { total: number; session_count: number; agent: string }>>({});
  const [pricingUpdated, setPricingUpdated] = useState<string>("");
  const [analyticsTotals, setAnalyticsTotals] = useState<AnalyticsTotals | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = () => Promise.all([
      fetch("http://127.0.0.1:8000/sessions").then(res => res.json()),
      fetch("http://127.0.0.1:8000/agents").then(res => res.json()),
      fetch("http://127.0.0.1:8000/analytics").then(res => res.json()).catch(() => ({}))
    ]).then(([sessionsData, agentsData, analyticsData]) => {
      const ts = (s: Session) => {
        const t = s.timestamp ? new Date(s.timestamp).getTime() : NaN;
        return Number.isFinite(t) ? t : -Infinity;
      };
      setSessions(sessionsData.sort((a: Session, b: Session) => ts(b) - ts(a)));
      setAvailableAgents(agentsData);
      setByModel(analyticsData?.by_model || {});
      setPricingUpdated(analyticsData?.pricing_updated || "");
      setAnalyticsTotals(analyticsData?.total || null);
      setLoading(false);
    }).catch(err => {
      console.error("Failed to fetch dashboard data:", err);
      setLoading(false);
    });
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, []);

  const measuredSessions = analyticsTotals?.quality?.measured_sessions ?? 0;
  const editTurns = analyticsTotals?.quality?.edit_turns ?? 0;

  const modelRows = Object.entries(byModel)
    .map(([name, s]) => ({ name, ...s }))
    .sort((a, b) => b.session_count - a.session_count);
  const totalModelSessions = modelRows.reduce((a, r) => a + r.session_count, 0) || 1;

  const totalTokens = sessions.reduce((acc, s) => acc + (s.tokens?.total || 0), 0);
  const totalCost = sessions.reduce((acc, s) => acc + (s.cost || 0), 0);

  return (
    <div className="p-8 max-w-[1600px] mx-auto space-y-10 pb-20">
      <header className="flex justify-between items-end border-b border-slate-800 pb-6 text-slate-100">
        <div>
          <h1 className="text-4xl font-black text-white tracking-tighter flex items-center gap-3">
            <Activity className="text-blue-500" size={36} strokeWidth={3} />
            DASHBOARD
          </h1>
          <p className="text-slate-500 mt-1 font-medium">Monitoring {sessions.length} active traces across {availableAgents.length} detected tools.</p>
        </div>
        <div className="flex gap-2">
           <div className="px-3 py-1.5 bg-slate-900 border border-slate-800 rounded-lg text-[10px] font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
              Live System
           </div>
        </div>
      </header>

      {/* Primary Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard title="Total Sessions" value={sessions.length} icon={<Clock className="text-blue-400" />} color="blue" />
        <StatCard title="Total Tokens" value={totalTokens > 1000000 ? `${(totalTokens / 1000000).toFixed(1)}M` : totalTokens.toLocaleString()} icon={<TrendingUp className="text-emerald-400" />} color="emerald" />
        <StatCard title="Active Projects" value={new Set(sessions.map(s => s.project)).size} icon={<Activity className="text-blue-400" />} color="blue" />
        <StatCard title="Cost Estimate" value={totalCost < 0.01 && totalCost > 0 ? "<$0.01" : `$${totalCost.toFixed(2)}`} subValue={pricingUpdated ? `Rates updated ${pricingUpdated}` : undefined} icon={<Zap className="text-amber-400" />} color="amber" />
      </div>

      {/* Quality Signals */}
      <section>
        <div className="flex items-baseline justify-between mb-4 ml-1">
          <h3 className="text-xs font-bold text-slate-500 uppercase tracking-[0.2em]">Quality Signals</h3>
          <span className="text-[10px] font-mono text-slate-600">
            Currently measured for Claude · more agents soon
          </span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <QualityCard
            title="Cache Hit %"
            scope="ALL AGENTS"
            value={analyticsTotals?.cache_hit_pct ?? null}
            tone="cyan"
            icon={<Layers size={16} />}
            barFraction={analyticsTotals?.cache_hit_pct ?? null}
            footer="cached / (input + cached) tokens"
            emptyHint="No token data yet"
          />
          <QualityCard
            title="One-Shot Rate"
            scope="CLAUDE"
            value={analyticsTotals?.quality?.one_shot_rate ?? null}
            tone="emerald"
            icon={<Target size={16} />}
            barFraction={analyticsTotals?.quality?.one_shot_rate ?? null}
            footer="Edits succeeding without retry"
            emptyHint="No Claude edit turns yet"
          />
          <QualityCard
            title="Retry Rate"
            scope="CLAUDE"
            value={analyticsTotals?.quality?.retry_rate ?? null}
            tone="amber"
            icon={<RotateCcw size={16} />}
            barFraction={analyticsTotals?.quality?.retry_rate ?? null}
            footer="Failed edits retried by the model"
            emptyHint="No Claude edit turns yet"
          />
        </div>
      </section>

      {/* Dynamic Agent Roster */}
      {availableAgents.length > 0 && (
        <section>
          <h3 className="text-xs font-bold text-slate-500 uppercase tracking-[0.2em] mb-4 ml-1">Connected Agents</h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-7 gap-3">
            {availableAgents.map(agentKey => {
              const config = AGENT_CONFIG[agentKey];
              if (!config) return null;
              const count = sessions.filter(s => s.agent === agentKey).length;
              const Icon = config.icon;
              return (
                <AgentStat
                  key={agentKey}
                  label={config.label}
                  count={count}
                  color={config.color}
                  icon={<Icon size={14} />}
                />
              );
            })}
          </div>
        </section>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-8 items-start">
         <section className="xl:col-span-2 bg-slate-900 rounded-2xl shadow-2xl border border-slate-800 overflow-hidden">
            <div className="p-6 border-b border-slate-800 bg-slate-900/50 flex justify-between items-center text-white">
               <h2 className="text-lg font-bold flex items-center gap-2">
                  <Activity size={18} className="text-blue-500" />
                  Recent Activity
               </h2>
               <span className="text-[10px] font-mono text-slate-500 bg-slate-950 px-2 py-1 rounded border border-slate-800 text-slate-100">
                  AUTO-SYNC ENABLED
               </span>
            </div>
            
            {loading ? (
               <div className="p-24 text-center text-slate-500 flex flex-col items-center gap-4">
                  <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-500 mx-auto"></div>
                  <span className="font-mono text-xs uppercase tracking-widest text-slate-100">Parsing Log Streams...</span>
               </div>
            ) : sessions.length === 0 ? (
               <div className="p-24 text-center text-slate-400 flex flex-col items-center gap-4">
                  <Terminal size={48} className="text-slate-600 mb-2" />
                  <h3 className="text-xl font-bold text-slate-300">No Agent Data Found</h3>
                  <p className="text-sm max-w-md mx-auto text-slate-500">TokenTelemetry scans your local directories for agent activity. Start using your coding agents (Claude Code, Cursor, Copilot, etc.) to see telemetry data appear here.</p>
               </div>
            ) : (
               <div className="overflow-x-auto">
                  <table className="w-full text-left">
                  <thead>
                     <tr className="text-slate-500 text-[10px] border-b border-slate-800 bg-slate-900/30 uppercase tracking-[0.15em] font-black">
                        <th className="px-6 py-4">Agent</th>
                        <th className="px-6 py-4">Project</th>
                        <th className="px-6 py-4 text-slate-100">Context</th>
                        <th className="px-6 py-4 text-right">Time</th>
                     </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/50">
                     {sessions.slice(0, 50).map((session, idx) => (
                        <tr key={`${session.agent}-${session.id}-${idx}`} className="hover:bg-slate-800/30 transition-colors cursor-pointer group">
                        <td className="px-6 py-4">
                           <Link href={`/sessions/${session.id}?agent=${session.agent}`} className="block">
                              <span className={`inline-flex items-center px-2 py-0.5 rounded text-[9px] font-black uppercase tracking-tighter border shadow-sm ${
                                 session.agent === 'claude' ? 'bg-orange-500/10 text-orange-400 border-orange-500/20' : 
                                 session.agent === 'codex' ? 'bg-purple-500/10 text-purple-400 border-purple-500/20' :
                                 session.agent === 'gemini' ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20' :
                                 session.agent === 'antigravity' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                                 session.agent === 'qwen' ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' :
                                 session.agent === 'vibe' ? 'bg-pink-500/10 text-pink-400 border-pink-500/20' :
                                 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20'
                              }`}>
                                 {session.agent}
                              </span>
                           </Link>
                        </td>
                        <td className="px-6 py-4 text-xs font-mono text-slate-400 truncate max-w-[140px]" title={session.project}>
                           <Link href={`/sessions/${session.id}?agent=${session.agent}`} className="block">
                              {session.project.split('/').pop()}
                           </Link>
                        </td>
                        <td className="px-6 py-4 text-sm text-slate-300 font-medium truncate max-w-sm">
                           <Link href={`/sessions/${session.id}?agent=${session.agent}`} className="block">
                              {session.display || session.text || <span className="italic text-slate-600 font-normal">No message content</span>}
                           </Link>
                        </td>
                        <td className="px-6 py-4 text-[10px] text-slate-500 group-hover:text-blue-400 transition-colors text-right font-mono tabular-nums leading-tight">
                           <Link href={`/sessions/${session.id}?agent=${session.agent}`} className="block">
                              {format(new Date(session.timestamp), 'HH:mm:ss')}
                              <div className="text-[8px] opacity-50 uppercase">{format(new Date(session.timestamp), 'MMM d')}</div>
                           </Link>
                        </td>
                        </tr>
                     ))}
                  </tbody>
                  </table>
               </div>
            )}
         </section>

         {/* Sidebar Widgets */}
         <div className="space-y-6">
            <div className="bg-gradient-to-br from-blue-600 to-indigo-700 p-6 rounded-2xl shadow-xl border border-blue-500/30 text-white group hover:scale-[1.02] transition-transform cursor-pointer relative overflow-hidden">
               <div className="absolute top-0 right-0 p-8 opacity-10 group-hover:scale-110 transition-transform">
                  <Activity size={120} strokeWidth={4} />
               </div>
               <h3 className="text-lg font-black tracking-tight mb-2 flex items-center gap-2">
                  EXPLORE PROJECTS
                  <ArrowRight size={18} />
               </h3>
               <p className="text-blue-100 text-sm mb-6 leading-relaxed font-medium">View detailed activity traces and tool logs for all your workspaces.</p>
               <Link href="/projects" className="bg-white/10 hover:bg-white/20 border border-white/20 py-2 px-4 rounded-lg text-xs font-bold uppercase tracking-widest transition-colors inline-block backdrop-blur-sm text-slate-100">
                  Open Projects Gallery
               </Link>
            </div>

            <div className="bg-slate-900 p-6 rounded-2xl border border-slate-800 shadow-xl">
               <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-6">Agent Distribution</h3>
               <div className="space-y-5">
                  {availableAgents.map((agent: any) => {
                     const count = sessions.filter(s => s.agent === agent).length;
                     if (count === 0) return null;
                     const percent = (count / sessions.length) * 100;
                     const colors: any = {
                        claude: "bg-orange-500", codex: "bg-purple-500", gemini: "bg-cyan-500",
                        antigravity: "bg-emerald-500", qwen: "bg-blue-500", vibe: "bg-pink-500", copilot: "bg-indigo-500", opencode: "bg-amber-500"
                     };
                     return (
                        <div key={agent} className="space-y-2">
                           <div className="flex justify-between text-[10px] font-bold uppercase">
                              <span className="text-slate-400">{agent}</span>
                              <span className="text-slate-500">{count} Sess</span>
                           </div>
                           <div className="h-1.5 bg-slate-950 rounded-full overflow-hidden border border-slate-800/50">
                              <div className={`h-full ${colors[agent] || 'bg-slate-700'}`} style={{ width: `${percent}%` }}></div>
                           </div>
                        </div>
                     );
                  })}
               </div>
               <Link href="/analytics" className="w-full text-center block mt-8 text-[10px] font-black uppercase text-blue-400 hover:text-blue-300 transition-colors tracking-widest border-t border-slate-800 pt-4">
                  VIEW FULL ANALYTICS
               </Link>
            </div>

            {modelRows.length > 0 && (
            <div className="bg-slate-900 p-6 rounded-2xl border border-slate-800 shadow-xl">
               <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-1 flex items-center gap-2">
                  <Cpu size={12} className="text-emerald-400" /> Model Distribution
               </h3>
               <p className="text-[9px] font-mono text-slate-600 mb-5">{modelRows.length} distinct models observed</p>
               <div className="space-y-4 max-h-96 overflow-y-auto pr-1">
                  {modelRows.map((m) => {
                     const percent = (m.session_count / totalModelSessions) * 100;
                     const hex = AGENT_HEX[m.agent] || "#64748b";
                     return (
                        <div key={m.name} className="space-y-1.5">
                           <div className="flex justify-between items-center text-[10px] gap-2">
                              <span className="font-mono text-slate-300 truncate" title={m.name}>{m.name}</span>
                              <span className="font-mono text-slate-500 tabular-nums whitespace-nowrap">{m.session_count}</span>
                           </div>
                           <div className="h-1.5 bg-slate-950 rounded-full overflow-hidden border border-slate-800/50">
                              <div className="h-full transition-all" style={{ width: `${percent}%`, backgroundColor: hex }}></div>
                           </div>
                           <div className="flex justify-between text-[8px] font-mono text-slate-600">
                              <span className="uppercase" style={{ color: hex }}>{m.agent}</span>
                              <span>{(m.total / 1000).toFixed(0)}k tok</span>
                           </div>
                        </div>
                     );
                  })}
               </div>
            </div>
            )}
         </div>
      </div>
    </div>
  );
}

function StatCard({ title, value, icon, color, subValue }: { title: string; value: string | number; icon: React.ReactNode; color: string; subValue?: string }) {
  const colorMap: Record<string, string> = {
    blue: "border-blue-500/20 bg-blue-500/5",
    emerald: "border-emerald-500/20 bg-emerald-500/5",
    cyan: "border-cyan-500/20 bg-cyan-500/5",
    amber: "border-amber-500/20 bg-amber-500/5"
  };

  return (
    <div className={`p-6 rounded-2xl border shadow-xl flex items-center justify-between transition-all hover:border-slate-600 ${colorMap[color] || 'border-slate-800 bg-slate-900'}`}>
      <div>
        <p className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em] mb-2">{title}</p>
        <p className="text-3xl font-black text-white tracking-tighter">{value}</p>
        {subValue && <p className="text-[9px] font-mono text-slate-500 mt-1.5 italic">{subValue}</p>}
      </div>
      <div className="p-3 bg-slate-950/50 rounded-xl border border-slate-800 shadow-inner">{icon}</div>
    </div>
  );
}

type QualityTone = "cyan" | "emerald" | "amber";

function QualityCard({
  title,
  scope,
  value,
  tone,
  icon,
  barFraction,
  footer,
  emptyHint,
}: {
  title: string;
  scope: string;
  value: number | null;
  tone: QualityTone;
  icon: React.ReactNode;
  barFraction: number | null;
  footer: string;
  emptyHint: string;
}) {
  const toneMap: Record<QualityTone, { border: string; bg: string; text: string; bar: string }> = {
    cyan: { border: "border-cyan-500/20", bg: "bg-cyan-500/5", text: "text-cyan-300", bar: "bg-cyan-400" },
    emerald: { border: "border-emerald-500/20", bg: "bg-emerald-500/5", text: "text-emerald-300", bar: "bg-emerald-400" },
    amber: { border: "border-amber-500/20", bg: "bg-amber-500/5", text: "text-amber-300", bar: "bg-amber-400" },
  };
  const t = toneMap[tone];
  const isClaude = scope.toUpperCase() === "CLAUDE";
  const chipClass = isClaude
    ? "border-orange-500/30 text-orange-300 bg-orange-500/10"
    : "border-slate-700 text-slate-400 bg-slate-900";
  const hasValue = value != null;
  const display = hasValue ? `${(value! * 100).toFixed(value! >= 0.995 ? 0 : 1)}%` : "—";
  const fillPct = Math.max(0, Math.min(1, barFraction ?? 0)) * 100;

  return (
    <div className={`p-6 rounded-2xl border shadow-xl flex flex-col gap-4 transition-all hover:border-slate-600 ${t.border} ${t.bg}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className={`p-2 rounded-lg bg-slate-950/60 border border-slate-800 ${t.text}`}>{icon}</div>
          <p className="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em]">{title}</p>
        </div>
        <span className={`px-2 py-0.5 rounded-full border text-[8px] font-black uppercase tracking-widest ${chipClass}`}>
          {scope}
        </span>
      </div>
      <div className="flex items-baseline gap-3">
        <p className={`text-4xl font-black tracking-tighter tabular-nums ${hasValue ? "text-white" : "text-slate-600"}`}>
          {display}
        </p>
        {!hasValue && (
          <span className="text-[9px] font-mono uppercase tracking-widest text-slate-600">awaiting data</span>
        )}
      </div>
      <div className="h-1.5 bg-slate-950 rounded-full overflow-hidden border border-slate-800/50">
        <div
          className={`h-full transition-all ${hasValue ? t.bar : "bg-slate-800"}`}
          style={{ width: `${hasValue ? fillPct : 0}%` }}
        />
      </div>
      <p className="text-[9px] font-mono text-slate-500 italic">
        {hasValue ? footer : emptyHint}
      </p>
    </div>
  );
}

function AgentStat({ label, count, color, icon }: { label: string; count: number; color: string; icon: React.ReactNode }) {
   const colorMap: Record<string, string> = {
      orange: "text-orange-400 bg-orange-400/5 border-orange-400/10",
      purple: "text-purple-400 bg-purple-400/5 border-purple-400/10",
      cyan: "text-cyan-400 bg-cyan-400/5 border-cyan-400/10",
      emerald: "text-emerald-400 bg-emerald-400/5 border-emerald-400/10",
      blue: "text-blue-400 bg-blue-400/5 border-blue-400/10",
      pink: "text-pink-400 bg-pink-400/5 border-pink-400/10",
      indigo: "text-indigo-400 bg-indigo-400/5 border-indigo-400/10"
   };

   return (
      <div className={`flex flex-col items-center justify-center p-3 rounded-xl border text-center transition-all hover:bg-slate-800/20 ${colorMap[color]}`}>
         <div className={`p-2 rounded-lg bg-slate-950/50 mb-2 border border-slate-800/50 text-slate-100`}>{icon}</div>
         <span className="text-[9px] font-black uppercase tracking-wider mb-1">{label}</span>
         <span className="font-mono text-sm font-bold text-white leading-none">{count}</span>
      </div>
   );
}
