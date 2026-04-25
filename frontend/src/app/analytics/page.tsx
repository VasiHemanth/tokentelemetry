"use client";

import { useEffect, useState, useMemo } from "react";
import { Activity, BarChart3, PieChart, TrendingUp, Zap, Info, DollarSign, MousePointer2, Cpu } from "lucide-react";
import { 
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, 
  Cell, PieChart as RePieChart, Pie, AreaChart, Area, Legend
} from "recharts";

interface AnalyticsData {
  by_agent: Record<string, {
    input: number;
    output: number;
    cached: number;
    total: number;
    cost: number;
    session_count: number;
  }>;
  by_day: {
    date: string;
    total: number;
    input: number;
    output: number;
    cached: number;
    cost: number;
  }[];
  by_model?: Record<string, {
    input: number;
    output: number;
    cached: number;
    total: number;
    cost: number;
    session_count: number;
    agent: string;
  }>;
  total: {
    input: number;
    output: number;
    cached: number;
    total: number;
    cost: number;
  };
  pricing_updated?: string;
}

const AGENT_COLORS: Record<string, string> = {
  claude: "#f97316",       // Orange
  codex: "#a855f7",        // Purple
  gemini: "#06b6d4",       // Cyan
  antigravity: "#10b981",  // Emerald
  qwen: "#3b82f6",         // Blue
  vibe: "#f472b6",         // Pink
  copilot: "#6366f1",      // Indigo
  cursor: "#3b82f6",       // Blue
  opencode: "#f59e0b"      // Amber
};

export default function AnalyticsPage() {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("http://localhost:8000/analytics")
      .then((res) => res.json())
      .then((data) => {
        setData(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Failed to fetch analytics:", err);
        setLoading(false);
      });
  }, []);

  const modelData = useMemo(() => {
    if (!data?.by_model) return [];
    return Object.entries(data.by_model)
      .map(([name, s]) => ({ name, ...s, color: AGENT_COLORS[s.agent] || "#3b82f6" }))
      .sort((a, b) => b.total - a.total);
  }, [data]);

  const agentData = useMemo(() => {
    if (!data) return [];
    return Object.entries(data.by_agent).map(([name, stats]) => ({
      name: name.charAt(0).toUpperCase() + name.slice(1),
      value: stats.total,
      color: AGENT_COLORS[name] || "#3b82f6"
    }));
  }, [data]);

  if (loading) {
    return (
      <div className="p-12 text-center text-slate-500">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-4"></div>
        Calculating token metrics...
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-10 pb-20">
      <header>
        <h1 className="text-3xl font-bold text-white flex items-center gap-3">
          <BarChart3 className="text-blue-500" size={32} />
          Token Analytics
        </h1>
        <p className="text-slate-400 mt-2">In-depth analysis of agent consumption and efficiency.</p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
         <MetricCard title="Total Tokens" value={data.total.total.toLocaleString()} subValue="Overall across all agents" icon={<TrendingUp className="text-blue-400" />} />
         <MetricCard title="Input Tokens" value={data.total.input.toLocaleString()} subValue={`${((data.total.input / Math.max(1, data.total.total)) * 100).toFixed(1)}% of total`} icon={<MousePointer2 className="text-emerald-400" />} />
         <MetricCard title="Est. Lifetime Cost" value={`$${data.total.cost.toFixed(2)}`} subValue={data.pricing_updated ? `Rates updated ${data.pricing_updated}` : "Based on actual model rates"} icon={<DollarSign className="text-amber-400" />} />
         <MetricCard title="Cache Efficiency" value={`${((data.total.cached / Math.max(1, (data.total.input + data.total.cached))) * 100).toFixed(1)}%`} subValue="Tokens saved via caching" icon={<Zap className="text-cyan-400" />} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
         <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
            <h2 className="text-lg font-bold text-white mb-6">Token Consumption (Daily)</h2>
            <div className="h-72 w-full">
               <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={data.by_day}>
                     <defs>
                        <linearGradient id="colorTotal" x1="0" y1="0" x2="0" y2="1">
                           <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                           <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                        </linearGradient>
                     </defs>
                     <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                     <XAxis dataKey="date" stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} />
                     <YAxis stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} tickFormatter={(value) => `${(value / 1000).toFixed(0)}k`} />
                     <Tooltip 
                        contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px' }}
                        itemStyle={{ fontSize: '12px' }}
                     />
                     <Area type="monotone" dataKey="total" stroke="#3b82f6" fillOpacity={1} fill="url(#colorTotal)" strokeWidth={2} />
                  </AreaChart>
               </ResponsiveContainer>
            </div>
         </div>

         <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
            <h2 className="text-lg font-bold text-white mb-6">Distribution by Agent</h2>
            <div className="flex h-72 items-center">
               <div className="w-1/2 h-full">
                  <ResponsiveContainer width="100%" height="100%">
                     <RePieChart>
                        <Pie
                           data={agentData}
                           innerRadius={60}
                           outerRadius={80}
                           paddingAngle={5}
                           dataKey="value"
                        >
                           {agentData.map((entry, index) => (
                              <Cell key={`cell-${index}`} fill={entry.color} />
                           ))}
                        </Pie>
                        <Tooltip />
                     </RePieChart>
                  </ResponsiveContainer>
               </div>
               <div className="w-1/2 space-y-4">
                  {agentData.map(agent => (
                     <div key={agent.name} className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                           <div className="w-3 h-3 rounded-full" style={{ backgroundColor: agent.color }}></div>
                           <span className="text-sm text-slate-300">{agent.name}</span>
                        </div>
                        <span className="text-sm font-mono text-slate-500">{((agent.value / Math.max(1, data.total.total)) * 100).toFixed(1)}%</span>
                     </div>
                  ))}
               </div>
            </div>
         </div>
      </div>

      <section className="bg-slate-900 rounded-2xl shadow-xl border border-slate-800 overflow-hidden">
        <div className="p-6 border-b border-slate-800 bg-slate-900/50">
          <h2 className="text-xl font-semibold text-white">Agent-Specific Metrics</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="text-slate-500 text-xs border-b border-slate-800 bg-slate-900/30 uppercase tracking-wider">
                <th className="px-6 py-4 font-semibold">Agent</th>
                <th className="px-6 py-4 font-semibold text-right">Sessions</th>
                <th className="px-6 py-4 font-semibold text-right">Input</th>
                <th className="px-6 py-4 font-semibold text-right">Output</th>
                <th className="px-6 py-4 font-semibold text-right">Cached</th>
                <th className="px-6 py-4 font-semibold text-right">Total Tokens</th>
                <th className="px-6 py-4 font-semibold text-right text-amber-500">Cost</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {Object.entries(data.by_agent).map(([name, stats]) => (
                <tr key={name} className="hover:bg-slate-800/50 transition-colors group">
                  <td className="px-6 py-4">
                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-tight ${
                      name === 'claude' ? 'bg-orange-500/10 text-orange-400 border border-orange-500/20' : 
                      name === 'codex' ? 'bg-purple-500/10 text-purple-400 border border-purple-500/20' :
                      name === 'gemini' ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/20' :
                      name === 'antigravity' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                      name === 'qwen' ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20' :
                      name === 'vibe' ? 'bg-pink-500/10 text-pink-400 border border-pink-500/20' :
                      'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20'
                    }`}>
                      {name}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-slate-300 text-right font-mono">{stats.session_count}</td>
                  <td className="px-6 py-4 text-sm text-slate-400 text-right font-mono">{stats.input.toLocaleString()}</td>
                  <td className="px-6 py-4 text-sm text-slate-400 text-right font-mono">{stats.output.toLocaleString()}</td>
                  <td className="px-6 py-4 text-sm text-cyan-400/70 text-right font-mono">{stats.cached.toLocaleString()}</td>
                  <td className="px-6 py-4 text-sm text-white text-right font-bold font-mono group-hover:text-blue-400 transition-colors">{stats.total.toLocaleString()}</td>
                  <td className="px-6 py-4 text-sm text-amber-400 text-right font-bold font-mono group-hover:text-amber-300 transition-colors">${stats.cost.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {modelData.length > 0 && (
        <section className="space-y-6">
          <div className="flex items-center gap-3">
            <Cpu className="text-emerald-400" size={22} />
            <h2 className="text-xl font-bold text-white">Model-wise Analytics</h2>
            <span className="text-[10px] font-mono text-slate-500 bg-slate-900 px-2 py-0.5 rounded border border-slate-800">{modelData.length} models</span>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl overflow-hidden">
              <h3 className="text-sm font-bold text-white mb-4">Tokens per Model</h3>
              <div className="h-[500px] w-full min-h-[500px]">
                <ResponsiveContainer width="99%" height="100%">
                  <BarChart 
                    data={modelData} 
                    layout="vertical" 
                    margin={{ left: 10, right: 40, top: 10, bottom: 10 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                    <XAxis 
                      type="number" 
                      stroke="#64748b" 
                      fontSize={10} 
                      tickLine={false} 
                      axisLine={false} 
                      tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} 
                    />
                    <YAxis 
                      type="category" 
                      dataKey="name" 
                      stroke="#94a3b8" 
                      fontSize={10} 
                      tickLine={false} 
                      axisLine={false} 
                      width={220}
                      interval={0}
                      tick={{ fill: '#94a3b8', fontSize: 10, width: 220 }}
                    />
                    <Tooltip 
                      contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px' }} 
                      itemStyle={{ fontSize: '12px' }}
                      cursor={{ fill: 'rgba(255,255,255,0.05)' }}
                    />
                    <Bar dataKey="total" radius={[0, 4, 4, 0]} barSize={20}>
                      {modelData.map((m, i) => <Cell key={i} fill={m.color} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
              <h3 className="text-sm font-bold text-white mb-4">Model Share</h3>
              <div className="flex h-72 items-center">
                <div className="w-1/2 h-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <RePieChart>
                      <Pie 
                        data={modelData} 
                        innerRadius={55} 
                        outerRadius={85} 
                        paddingAngle={3} 
                        dataKey="total"
                        nameKey="name"
                      >
                        {modelData.map((m, i) => <Cell key={i} fill={m.color} />)}
                      </Pie>
                      <Tooltip contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px' }} />
                    </RePieChart>
                  </ResponsiveContainer>
                </div>
                <div className="w-1/2 space-y-2 max-h-full overflow-y-auto pr-2">
                  {modelData.map((m) => (
                    <div key={m.name} className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: m.color }}></div>
                        <span className="text-[11px] font-mono text-slate-300 truncate" title={m.name}>{m.name}</span>
                      </div>
                      <span className="text-[10px] font-mono text-slate-500 tabular-nums">{((m.total / Math.max(1, data.total.total)) * 100).toFixed(1)}%</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="bg-slate-900 rounded-2xl shadow-xl border border-slate-800 overflow-hidden">
            <div className="p-6 border-b border-slate-800 bg-slate-900/50">
              <h3 className="text-lg font-semibold text-white">Per-Model Breakdown</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="text-slate-500 text-xs border-b border-slate-800 bg-slate-900/30 uppercase tracking-wider">
                    <th className="px-6 py-4 font-semibold">Model</th>
                    <th className="px-6 py-4 font-semibold">Agent</th>
                    <th className="px-6 py-4 font-semibold text-right">Sessions</th>
                    <th className="px-6 py-4 font-semibold text-right">Input</th>
                    <th className="px-6 py-4 font-semibold text-right">Output</th>
                    <th className="px-6 py-4 font-semibold text-right">Cached</th>
                    <th className="px-6 py-4 font-semibold text-right">Total</th>
                    <th className="px-6 py-4 font-semibold text-right text-amber-500">Cost</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {modelData.map((m) => (
                    <tr key={m.name} className="hover:bg-slate-800/50 transition-colors group">
                      <td className="px-6 py-4">
                        <span className="flex items-center gap-2 text-[11px] font-mono text-emerald-400">
                          <Cpu size={12} /> {m.name}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <span className="text-[10px] font-bold uppercase" style={{ color: m.color }}>{m.agent}</span>
                      </td>
                      <td className="px-6 py-4 text-sm text-slate-300 text-right font-mono">{m.session_count}</td>
                      <td className="px-6 py-4 text-sm text-slate-400 text-right font-mono">{m.input.toLocaleString()}</td>
                      <td className="px-6 py-4 text-sm text-slate-400 text-right font-mono">{m.output.toLocaleString()}</td>
                      <td className="px-6 py-4 text-sm text-cyan-400/70 text-right font-mono">{m.cached.toLocaleString()}</td>
                      <td className="px-6 py-4 text-sm text-white text-right font-bold font-mono group-hover:text-blue-400 transition-colors">{m.total.toLocaleString()}</td>
                      <td className="px-6 py-4 text-sm text-amber-400 text-right font-bold font-mono group-hover:text-amber-300 transition-colors">${m.cost.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

function MetricCard({ title, value, subValue, icon }: { title: string; value: string; subValue: string; icon: React.ReactNode }) {
  return (
    <div className="bg-slate-900 p-6 rounded-2xl border border-slate-800 shadow-lg relative overflow-hidden group hover:border-slate-700 transition-colors">
      <div className="flex justify-between items-start mb-4">
         <div className="p-2 bg-slate-950 rounded-lg border border-slate-800 group-hover:scale-110 transition-transform">{icon}</div>
      </div>
      <div>
         <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1">{title}</p>
         <p className="text-2xl font-bold text-white tracking-tight">{value}</p>
         <p className="text-[10px] text-slate-500 mt-1">{subValue}</p>
      </div>
    </div>
  );
}
