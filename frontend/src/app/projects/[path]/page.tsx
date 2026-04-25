"use client";

import { useEffect, useState, useMemo, Fragment } from "react";
import { useParams } from "next/navigation";
import { ArrowLeft, Folder, Activity, Database, Terminal, Clock, Cpu, Users, ClipboardList, Sparkles, Zap, GitBranch, Orbit, Search, FileText, Settings2, Wrench, BookOpen, Globe, Package } from "lucide-react";
import Link from "next/link";
import { format } from "date-fns";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface PlanSnippet {
  session_id: string;
  agent: string;
  timestamp: string;
  content: string;
}

interface Session {
  id: string;
  agent: string;
  project: string;
  timestamp: string;
  display?: string;
  text?: string;
  mcp_tools: string[];
  subagents: string[];
  has_plan: boolean;
  tokens?: { input: number; output: number; cached: number; total: number };
}

const AGENT_HEX: Record<string, string> = {
  claude: "#f97316", codex: "#a855f7", gemini: "#06b6d4",
  antigravity: "#10b981", qwen: "#3b82f6", vibe: "#ec4899",
  cursor: "#60a5fa", copilot: "#818cf8", opencode: "#f59e0b"
};

interface Project {
  name: string;
  path: string;
  session_count: number;
  agents: string[];
  mcp_tools: string[];
  subagent_count: number;
  configured_subagent_count?: number;
  plan_count: number;
  plans: PlanSnippet[];
  tokens?: { input: number; output: number; cached: number; total: number };
}

function formatTokens(n: number): string {
  if (!n) return "0";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(n >= 10_000 ? 0 : 1) + "K";
  return String(n);
}

export default function ProjectSessionsPage() {
  const params = useParams();
  const rawPath = params?.path as string;
  const decodedPath = rawPath ? decodeURIComponent(rawPath) : "";
  
  const [sessions, setSessions] = useState<Session[]>([]);
  const [projectData, setProjectData] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"activity" | "insights" | "plans" | "config">("activity");
  const [config, setConfig] = useState<any>(null);
  const [configLoading, setConfigLoading] = useState(false);

  useEffect(() => {
    // Fetch project aggregate data (for plans)
    fetch("http://localhost:8000/projects")
      .then(res => res.json())
      .then(data => {
         const proj = data.find((p: Project) => p.path === decodedPath);
         if (proj) setProjectData(proj);
      });

    // Fetch session list
    fetch("http://localhost:8000/sessions")
      .then((res) => res.json())
      .then((data) => {
        const projectSessions = data.filter((s: Session) => s.project === decodedPath);
        setSessions(projectSessions.sort((a: Session, b: Session) => 
          new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
        ));
        setLoading(false);
      })
      .catch((err) => {
        console.error("Failed to fetch sessions for project:", err);
        setLoading(false);
      });
  }, [decodedPath]);

  const projectName = decodedPath.split('/').pop() || "Unknown Project";

  const insights = useMemo(() => {
    const DAYS = 365;
    const today = new Date(); today.setHours(0,0,0,0);
    const start = new Date(today); start.setDate(start.getDate() - (DAYS - 1));
    const dayKey = (d: Date) => d.toISOString().slice(0,10);

    type DayBucket = { date: string; count: number; tokens: number; byAgent: Record<string, number> };
    const daily: Record<string, DayBucket> = {};
    for (let i = 0; i < DAYS; i++) {
      const d = new Date(start); d.setDate(d.getDate() + i);
      daily[dayKey(d)] = { date: dayKey(d), count: 0, tokens: 0, byAgent: {} };
    }

    const agentStats: Record<string, { count: number; tokens: number; firstSeen: number; lastSeen: number }> = {};
    const toolCounts: Record<string, { sessions: number; byAgent: Record<string, number> }> = {};
    const hourly: number[] = Array(24).fill(0);
    const activeDays = new Set<string>();
    const dowHour: number[][] = Array.from({ length: 7 }, () => Array(24).fill(0));
    const perAgentDaily: Record<string, Record<string, { count: number; tokens: number }>> = {};
    const seedAgentDaily = (a: string) => {
      if (perAgentDaily[a]) return;
      perAgentDaily[a] = {};
      for (let i = 0; i < DAYS; i++) {
        const d = new Date(start); d.setDate(d.getDate() + i);
        perAgentDaily[a][dayKey(d)] = { count: 0, tokens: 0 };
      }
    };

    for (const s of sessions) {
      const ts = new Date(s.timestamp); if (isNaN(ts.getTime())) continue;
      const tsMs = ts.getTime();
      const k = dayKey(new Date(ts.getFullYear(), ts.getMonth(), ts.getDate()));
      const tok = s.tokens?.total || 0;
      if (daily[k]) {
        daily[k].count += 1; daily[k].tokens += tok;
        daily[k].byAgent[s.agent] = (daily[k].byAgent[s.agent] || 0) + 1;
      }
      activeDays.add(k);
      hourly[ts.getHours()] += 1;
      dowHour[ts.getDay()][ts.getHours()] += 1;

      seedAgentDaily(s.agent);
      if (perAgentDaily[s.agent][k]) {
        perAgentDaily[s.agent][k].count += 1;
        perAgentDaily[s.agent][k].tokens += tok;
      }

      const as = agentStats[s.agent] ||= { count: 0, tokens: 0, firstSeen: tsMs, lastSeen: tsMs };
      as.count += 1; as.tokens += tok;
      as.firstSeen = Math.min(as.firstSeen, tsMs); as.lastSeen = Math.max(as.lastSeen, tsMs);

      const seenTools = new Set<string>();
      for (const t of s.mcp_tools || []) {
        if (!t || seenTools.has(t)) continue;
        seenTools.add(t);
        const tc = toolCounts[t] ||= { sessions: 0, byAgent: {} };
        tc.sessions += 1; tc.byAgent[s.agent] = (tc.byAgent[s.agent] || 0) + 1;
      }
    }

    const dailyArr = Object.values(daily);
    const maxDaily = Math.max(1, ...dailyArr.map(d => d.count));
    const maxTokens = Math.max(1, ...dailyArr.map(d => d.tokens));

    // streaks
    let current = 0, longest = 0;
    for (let i = DAYS - 1; i >= 0; i--) {
      const d = new Date(start); d.setDate(d.getDate() + i);
      if (activeDays.has(dayKey(d))) current++;
      else break;
    }
    let run = 0;
    for (const d of dailyArr) { if (d.count > 0) { run++; longest = Math.max(longest, run); } else run = 0; }

    const agents = Object.entries(agentStats).sort((a,b) => b[1].tokens - a[1].tokens);
    const topTokens = Math.max(1, ...agents.map(([,a]) => a.tokens));

    const tools = Object.entries(toolCounts).sort((a,b) => b[1].sessions - a[1].sessions);
    const topToolCount = Math.max(1, ...tools.map(([,t]) => t.sessions));

    const maxHour = Math.max(1, ...hourly);

    const perAgent = agents.map(([a, s]: any) => {
      const arr = Object.values(perAgentDaily[a] || {}) as { count: number; tokens: number }[];
      const max = Math.max(1, ...arr.map(x => x.count));
      const maxTok = Math.max(1, ...arr.map(x => x.tokens));
      return { agent: a, stats: s, arr, max, maxTok };
    });

    const maxDowHour = Math.max(1, ...dowHour.flat());

    return { dailyArr, maxDaily, maxTokens, start, today, agents, topTokens, tools, topToolCount, hourly, maxHour, activeDays, current, longest, perAgent, dowHour, maxDowHour };
  }, [sessions]);

  const [heatMetric, setHeatMetric] = useState<"sessions" | "tokens">("sessions");

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 p-8 font-sans">
      <header className="max-w-[1400px] mx-auto space-y-8">
        <Link href="/projects" className="text-blue-400 flex items-center gap-2 hover:underline mb-4 text-sm font-medium">
          <ArrowLeft size={16} /> Back to Projects
        </Link>
        
        <div className="flex items-center justify-between border-b border-slate-800 pb-8">
          <div className="space-y-2">
            <h1 className="text-4xl font-black text-white tracking-tight flex items-center gap-4">
               <div className="p-3 bg-blue-600/10 rounded-2xl border border-blue-500/20">
                  <Folder className="text-blue-500" size={32} />
               </div>
               {projectName}
            </h1>
            <p className="text-slate-500 text-xs font-mono bg-slate-900 inline-block px-3 py-1 rounded-full border border-slate-800">
               {decodedPath}
            </p>
          </div>
          
          <div className="flex gap-6">
             <Metric icon={<Clock size={16}/>} label="Sessions" value={sessions.length} color="blue" />
             <Metric icon={<Users size={16}/>} label="Subagents" value={(projectData?.configured_subagent_count || 0) + (projectData?.subagent_count || 0)} color="purple" />
             <Metric icon={<ClipboardList size={16}/>} label="Plans" value={projectData?.plans?.length || 0} color="emerald" />
             <Metric icon={<Zap size={16}/>} label="Tokens" value={fmtNum(sessions.reduce((sum, s) => sum + (s.tokens?.total || 0), 0))} color="amber" />
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex gap-1 bg-slate-900 p-1 rounded-xl border border-slate-800 w-fit">
           <button 
              onClick={() => setActiveTab("activity")}
              className={`px-6 py-2 rounded-lg text-xs font-bold uppercase tracking-widest transition-all ${activeTab === 'activity' ? 'bg-blue-600 text-white shadow-lg' : 'text-slate-500 hover:text-slate-300'}`}
           >
              Activity Trace
           </button>
           <button
              onClick={() => setActiveTab("insights")}
              className={`px-6 py-2 rounded-lg text-xs font-bold uppercase tracking-widest transition-all ${activeTab === 'insights' ? 'bg-purple-600 text-white shadow-lg' : 'text-slate-500 hover:text-slate-300'}`}
           >
              Insights
           </button>
           <button
              onClick={() => setActiveTab("plans")}
              className={`px-6 py-2 rounded-lg text-xs font-bold uppercase tracking-widest transition-all ${activeTab === 'plans' ? 'bg-emerald-600 text-white shadow-lg' : 'text-slate-500 hover:text-slate-300'}`}
           >
              Architectural Plans ({projectData?.plans?.length || 0})
           </button>
           <button
              onClick={() => {
                setActiveTab("config");
                if (!config && !configLoading) {
                  setConfigLoading(true);
                  fetch(`http://localhost:8000/config?project=${encodeURIComponent(decodedPath)}`)
                    .then(r => r.json()).then(setConfig).finally(() => setConfigLoading(false));
                }
              }}
              className={`px-6 py-2 rounded-lg text-xs font-bold uppercase tracking-widest transition-all ${activeTab === 'config' ? 'bg-cyan-600 text-white shadow-lg' : 'text-slate-500 hover:text-slate-300'}`}
           >
              Configuration
           </button>
        </div>
      </header>

      <main className="max-w-[1400px] mx-auto mt-10 pb-20">
         {activeTab === "insights" && (
            <ProjectInsights insights={insights} heatMetric={heatMetric} setHeatMetric={setHeatMetric} />
         )}

         {activeTab === "activity" && (
            <section className="bg-slate-900 rounded-3xl shadow-2xl border border-slate-800 overflow-hidden">
               <div className="p-6 border-b border-slate-800 bg-slate-900/50 flex justify-between items-center">
                  <h2 className="text-lg font-bold text-white flex items-center gap-2">
                     <Activity size={18} className="text-blue-500" />
                     Session History
                  </h2>
               </div>
               
               {loading ? (
                  <div className="p-24 text-center text-slate-500 flex flex-col items-center gap-4">
                     <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-500 mx-auto"></div>
                     <span className="font-mono text-xs uppercase tracking-widest">Compiling Workspace Activity...</span>
                  </div>
               ) : sessions.length === 0 ? (
                  <div className="p-32 text-center text-slate-600 italic">
                     No recorded activity in this workspace yet.
                  </div>
               ) : (
                  <div className="overflow-x-auto">
                     <table className="w-full text-left">
                        <thead>
                           <tr className="text-slate-500 text-[10px] border-b border-slate-800 bg-slate-900/30 uppercase tracking-[0.15em] font-black">
                              <th className="px-6 py-4">Agent</th>
                              <th className="px-6 py-4">Session Intent</th>
                              <th className="px-6 py-4">Insights</th>
                              <th className="px-6 py-4 text-right">Timestamp</th>
                           </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/50">
                           {sessions.map((session, idx) => (
                              <tr key={`${session.agent}-${session.id}-${idx}`} className="hover:bg-slate-800/30 transition-colors cursor-pointer group">
                                 <td className="px-6 py-4">
                                    <Link href={`/sessions/${session.id}?agent=${session.agent}`} className="block">
                                       <span className={`inline-flex items-center px-2 py-0.5 rounded text-[9px] font-black uppercase tracking-tighter border ${
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
                                 <td className="px-6 py-4 text-sm text-slate-300 font-medium truncate max-w-xl">
                                    <Link href={`/sessions/${session.id}?agent=${session.agent}`} className="block">
                                       {session.display || session.text || <span className="italic text-slate-600 font-normal">No prompt content</span>}
                                    </Link>
                                 </td>
                                 <td className="px-6 py-4">
                                    <div className="flex gap-2 opacity-40 group-hover:opacity-100 transition-opacity">
                                       {session.has_plan && <span title="Plan Detected"><ClipboardList size={14} className="text-emerald-400" /></span>}
                                       {(session.mcp_tools?.length > 0) && <span title={`${session.mcp_tools.length} Tools Used`}><Cpu size={14} className="text-blue-400" /></span>}
                                    </div>
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
         )}

         {activeTab === "plans" && (
            <section className="space-y-8">
               {(!projectData?.plans || projectData.plans.length === 0) ? (
                  <div className="p-32 text-center bg-slate-900 rounded-3xl border border-slate-800 text-slate-600 italic">
                     No architectural plans have been formally detected in this workspace.
                  </div>
               ) : (
                  <div className="grid grid-cols-1 gap-8">
                     {projectData.plans.map((plan, idx) => (
                        <div key={idx} className="bg-slate-900 rounded-3xl border border-slate-800 overflow-hidden shadow-2xl flex flex-col group hover:border-emerald-500/30 transition-all">
                           <div className="p-5 border-b border-slate-800 bg-slate-900/50 flex justify-between items-center">
                              <div className="flex items-center gap-3">
                                 <span className={`px-2 py-0.5 rounded text-[9px] font-black uppercase border ${
                                    plan.agent === 'claude' ? 'bg-orange-500/10 text-orange-400 border-orange-500/20' : 
                                    plan.agent === 'codex' ? 'bg-purple-500/10 text-purple-400 border-purple-500/20' :
                                    plan.agent === 'gemini' ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20' :
                                    'bg-slate-500/10 text-slate-400 border-slate-500/20'
                                 }`}>
                                    {plan.agent}
                                 </span>
                                 <h3 className="text-white font-bold text-sm">Plan from Session {plan.session_id.slice(0, 8)}</h3>
                              </div>
                              <div className="text-[10px] font-mono text-slate-500 uppercase tracking-widest">
                                 Detected {format(new Date(plan.timestamp), 'MMM d, HH:mm')}
                              </div>
                           </div>
                           <div className="p-8 prose prose-invert prose-slate prose-sm max-w-none prose-pre:bg-slate-950 prose-pre:border prose-pre:border-slate-800 prose-emerald">
                              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                 {plan.content}
                              </ReactMarkdown>
                           </div>
                           <div className="p-4 border-t border-slate-800/50 bg-slate-950/20 flex justify-end">
                              <Link 
                                 href={`/sessions/${plan.session_id}?agent=${plan.agent}`}
                                 className="text-[10px] font-black uppercase text-blue-400 hover:text-blue-300 transition-colors flex items-center gap-2"
                              >
                                 View Full Context <ArrowLeft className="rotate-180" size={12} />
                              </Link>
                           </div>
                        </div>
                     ))}
                  </div>
               )}
            </section>
         )}

         {activeTab === "config" && (
            <ConfigSection config={config} loading={configLoading} />
         )}
      </main>
    </div>
  );
}

function Metric({ icon, label, value, color }: { icon: React.ReactNode, label: string, value: number | string, color: string }) {
   const colors: any = {
      blue: "text-blue-400 bg-blue-500/10 border-blue-500/20",
      purple: "text-purple-400 bg-purple-500/10 border-purple-500/20",
      emerald: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
      amber: "text-amber-400 bg-amber-500/10 border-amber-500/20"
   };
   
   return (
      <div className={`flex flex-col items-center justify-center min-w-[100px] p-3 rounded-2xl border ${colors[color]}`}>
         <div className="mb-1 opacity-60">{icon}</div>
         <span className="text-[9px] font-black uppercase tracking-widest opacity-70 mb-1">{label}</span>
         <span className="text-xl font-black tracking-tight text-white">{value}</span>
      </div>
   );
}


const AGENT_TONE: Record<string, string> = {
  claude: "bg-orange-500/10 text-orange-400 border-orange-500/20",
  codex: "bg-purple-500/10 text-purple-400 border-purple-500/20",
  cursor: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  gemini: "bg-cyan-500/10 text-cyan-400 border-cyan-500/20",
  antigravity: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  qwen: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  vibe: "bg-pink-500/10 text-pink-400 border-pink-500/20",
  copilot: "bg-indigo-500/10 text-indigo-400 border-indigo-500/20",
  opencode: "bg-amber-500/10 text-amber-400 border-amber-500/20",
};

function ConfigSection({ config, loading }: { config: any; loading: boolean }) {
  if (loading) {
    return (
      <div className="p-24 text-center text-slate-500 flex flex-col items-center gap-4">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-cyan-500 mx-auto"></div>
        <span className="font-mono text-xs uppercase tracking-widest">Loading Configuration...</span>
      </div>
    );
  }
  if (!config) return <div className="p-16 text-center text-slate-600 italic">Click Configuration to load.</div>;

  const skills = config.skills || [];
  const mcps = config.mcps || [];
  const memory = config.memory || [];
  const commands = config.commands || [];
  const subagents = config.subagents || [];

  const bucket = <T extends { scope: string }>(arr: T[]) => ({
    project: arr.filter(x => x.scope === "project"),
    user: arr.filter(x => x.scope === "user"),
  });
  const sb = bucket(skills);
  const mb = bucket(mcps);
  const memb = bucket(memory);
  const cb = bucket(commands);
  const agb = bucket(subagents);

  const projectHasAny = sb.project.length + mb.project.length + memb.project.length + cb.project.length + agb.project.length > 0;
  const userHasAny = sb.user.length + mb.user.length + memb.user.length + cb.user.length + agb.user.length > 0;

  const renderSkill = (s: any) => (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 hover:border-slate-700 transition-colors">
      <div className="flex items-center justify-between mb-2 gap-2">
        <span className="text-sm font-black text-white truncate">{s.name}</span>
        <span className={`text-[9px] font-black uppercase px-2 py-0.5 rounded border ${AGENT_TONE[s.agent] || "text-slate-400 border-slate-700"}`}>{s.agent}</span>
      </div>
      {s.description && <p className="text-[11px] text-slate-400 leading-relaxed line-clamp-3">{s.description}</p>}
      <div className="text-[9px] font-mono text-slate-600 mt-3 truncate" title={s.source}>{s.source?.replace(/^.*\//, "")}</div>
    </div>
  );

  const renderSubagent = (a: any) => (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 hover:border-purple-500/40 transition-colors">
      <div className="flex items-center justify-between mb-2 gap-2">
        <span className="text-sm font-black text-white truncate flex items-center gap-2"><Users size={12} className="text-purple-400"/>{a.name}</span>
        <span className={`text-[9px] font-black uppercase px-2 py-0.5 rounded border ${AGENT_TONE[a.agent] || "text-slate-400 border-slate-700"}`}>{a.agent}</span>
      </div>
      {a.description && <p className="text-[11px] text-slate-400 leading-relaxed line-clamp-3 mb-2">{a.description}</p>}
      <div className="flex flex-wrap gap-1.5 mt-2">
        {a.model && <span className="text-[9px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">{a.model}</span>}
        {a.tools && <span className="text-[9px] font-mono px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-300 truncate max-w-full" title={a.tools}>{a.tools}</span>}
      </div>
    </div>
  );

  const renderCommand = (c: any) => (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 hover:border-slate-700 transition-colors">
      <div className="flex items-center justify-between mb-2 gap-2">
        <span className="text-sm font-black text-white truncate">/{c.name}</span>
        <span className={`text-[9px] font-black uppercase px-2 py-0.5 rounded border ${AGENT_TONE[c.agent] || "text-slate-400 border-slate-700"}`}>{c.agent}</span>
      </div>
      {c.description && <p className="text-[11px] text-slate-400 leading-relaxed line-clamp-3">{c.description}</p>}
    </div>
  );

  const renderMcp = (m: any) => (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 hover:border-slate-700 transition-colors">
      <div className="flex items-center justify-between mb-2 gap-2">
        <span className="text-sm font-black text-white truncate">{m.name}</span>
        <span className={`text-[9px] font-black uppercase px-2 py-0.5 rounded border ${AGENT_TONE[m.agent] || "text-slate-400 border-slate-700"}`}>{m.agent}</span>
      </div>
      {m.command && <div className="text-[10px] font-mono text-slate-400 bg-slate-950 px-2 py-1 rounded border border-slate-800 mt-2 truncate" title={m.command}><Package size={10} className="inline mr-1 opacity-60"/>{m.command}</div>}
      {m.url && <div className="text-[10px] font-mono text-slate-400 bg-slate-950 px-2 py-1 rounded border border-slate-800 mt-2 truncate" title={m.url}><Globe size={10} className="inline mr-1 opacity-60"/>{m.url}</div>}
      {m.type && <div className="text-[9px] font-mono text-slate-600 mt-2 uppercase tracking-widest">{m.type}</div>}
    </div>
  );

  const renderMemory = (m: any) => (
    <details className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden">
      <summary className="px-5 py-3 cursor-pointer hover:bg-slate-800/40 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <span className={`text-[9px] font-black uppercase px-2 py-0.5 rounded border ${AGENT_TONE[m.agent] || "text-slate-400 border-slate-700"}`}>{m.agent}</span>
          <span className="text-sm font-bold text-white">{m.name}</span>
        </div>
        <span className="text-[9px] font-mono text-slate-600 truncate max-w-[380px]" title={m.path}>{m.path}</span>
      </summary>
      <pre className="text-[11px] font-mono text-slate-300 whitespace-pre-wrap bg-slate-950 border-t border-slate-800 p-4 max-h-96 overflow-y-auto">{m.preview}{m.truncated ? "\n…(truncated)" : ""}</pre>
    </details>
  );

  const ScopeGroup = ({ items, render, cols = 3 }: { items: any[]; render: (x: any) => React.ReactNode; cols?: number }) =>
    items.length === 0 ? null : (
      <div className={`grid grid-cols-1 md:grid-cols-2 ${cols === 3 ? "lg:grid-cols-3" : ""} gap-3`}>
        {items.map((x, i) => <div key={i}>{render(x)}</div>)}
      </div>
    );

  return (
    <div className="space-y-8">
      {/* Summary — project counts primary, user counts muted */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <SumCard icon={<Users size={16}/>} label="Subagents" value={agb.project.length} userValue={agb.user.length} tone="purple" />
        <SumCard icon={<BookOpen size={16}/>} label="Skills" value={sb.project.length} userValue={sb.user.length} tone="cyan" />
        <SumCard icon={<Terminal size={16}/>} label="Commands" value={cb.project.length} userValue={cb.user.length} tone="emerald" />
        <SumCard icon={<Wrench size={16}/>} label="MCP Servers" value={mb.project.length} userValue={mb.user.length} tone="emerald" />
        <SumCard icon={<FileText size={16}/>} label="Memory" value={memb.project.length} userValue={memb.user.length} tone="amber" />
      </div>

      {/* PROJECT SCOPE — inline */}
      <section>
        <div className="flex items-center gap-3 mb-6">
          <Folder className="text-blue-400" size={18} />
          <h2 className="text-lg font-black text-white">Project Configuration</h2>
          <span className="text-[9px] font-mono text-slate-500 bg-blue-500/10 border border-blue-500/20 px-2 py-0.5 rounded">{config.project}</span>
        </div>

        {!projectHasAny ? (
          <div className="p-12 text-center bg-slate-900/50 rounded-2xl border border-dashed border-slate-800 text-slate-600 italic">
            No project-scoped skills, commands, or MCPs found in this workspace.
          </div>
        ) : (
          <div className="space-y-6">
            {agb.project.length > 0 && (<div><SectionHead icon={<Users size={14} className="text-purple-400"/>} label="Subagents" count={agb.project.length}/><ScopeGroup items={agb.project} render={renderSubagent}/></div>)}
            {sb.project.length > 0 && (<div><SectionHead icon={<BookOpen size={14} className="text-cyan-400"/>} label="Skills" count={sb.project.length}/><ScopeGroup items={sb.project} render={renderSkill}/></div>)}
            {cb.project.length > 0 && (<div><SectionHead icon={<Terminal size={14} className="text-emerald-400"/>} label="Commands" count={cb.project.length}/><ScopeGroup items={cb.project} render={renderCommand}/></div>)}
            {mb.project.length > 0 && (<div><SectionHead icon={<Wrench size={14} className="text-emerald-400"/>} label="MCP Servers" count={mb.project.length}/><ScopeGroup items={mb.project} render={renderMcp}/></div>)}
            {memb.project.length > 0 && (<div><SectionHead icon={<FileText size={14} className="text-amber-400"/>} label="Memory Files" count={memb.project.length}/><div className="space-y-3">{memb.project.map((m,i)=>(<div key={i}>{renderMemory(m)}</div>))}</div></div>)}
          </div>
        )}
      </section>

      {/* ROOT (USER) SCOPE — collapsed accordion */}
      {userHasAny && (
        <details className="bg-slate-900/50 border border-slate-800 rounded-2xl overflow-hidden group">
          <summary className="px-6 py-4 cursor-pointer hover:bg-slate-900 flex items-center justify-between gap-4 list-none">
            <div className="flex items-center gap-3">
              <Settings2 className="text-slate-400 group-open:text-slate-200 transition-colors" size={18} />
              <div>
                <h2 className="text-sm font-black text-white uppercase tracking-wider">Root / User Configuration</h2>
                <p className="text-[10px] text-slate-500 font-mono">Shared across all projects for all tools</p>
              </div>
            </div>
            <div className="flex items-center gap-4 text-[10px] font-mono text-slate-500">
              <span><span className="text-purple-400 font-black">{agb.user.length}</span> subagents</span>
              <span><span className="text-cyan-400 font-black">{sb.user.length}</span> skills</span>
              <span><span className="text-emerald-400 font-black">{cb.user.length}</span> commands</span>
              <span><span className="text-emerald-400 font-black">{mb.user.length}</span> mcps</span>
              <span><span className="text-amber-400 font-black">{memb.user.length}</span> memory</span>
              <span className="text-slate-600 group-open:rotate-180 transition-transform">▾</span>
            </div>
          </summary>
          <div className="p-6 border-t border-slate-800 space-y-6">
            {agb.user.length > 0 && (<div><SectionHead icon={<Users size={14} className="text-purple-400"/>} label="Subagents" count={agb.user.length}/><ScopeGroup items={agb.user} render={renderSubagent}/></div>)}
            {sb.user.length > 0 && (<div><SectionHead icon={<BookOpen size={14} className="text-cyan-400"/>} label="Skills" count={sb.user.length}/><ScopeGroup items={sb.user} render={renderSkill}/></div>)}
            {cb.user.length > 0 && (<div><SectionHead icon={<Terminal size={14} className="text-emerald-400"/>} label="Commands" count={cb.user.length}/><ScopeGroup items={cb.user} render={renderCommand}/></div>)}
            {mb.user.length > 0 && (<div><SectionHead icon={<Wrench size={14} className="text-emerald-400"/>} label="MCP Servers" count={mb.user.length}/><ScopeGroup items={mb.user} render={renderMcp}/></div>)}
            {memb.user.length > 0 && (<div><SectionHead icon={<FileText size={14} className="text-amber-400"/>} label="Memory Files" count={memb.user.length}/><div className="space-y-3">{memb.user.map((m,i)=>(<div key={i}>{renderMemory(m)}</div>))}</div></div>)}
          </div>
        </details>
      )}
    </div>
  );
}

function SectionHead({ icon, label, count }: { icon: React.ReactNode; label: string; count: number }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      {icon}
      <span className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">{label}</span>
      <span className="text-[9px] font-mono text-slate-600">{count}</span>
    </div>
  );
}

function ScopeBlock({ title, icon, projectItems, userItems, renderItem }: { title: string; icon: React.ReactNode; projectItems: any[]; userItems: any[]; renderItem: (x: any) => React.ReactNode }) {
  if (projectItems.length === 0 && userItems.length === 0) return null;
  return (
    <section>
      <h3 className="text-xs font-black uppercase tracking-[0.2em] text-slate-500 mb-4 flex items-center gap-2">{icon} {title}</h3>
      {projectItems.length > 0 && (
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[9px] font-black uppercase text-blue-400 bg-blue-500/10 border border-blue-500/20 px-2 py-0.5 rounded">Project</span>
            <span className="text-[9px] font-mono text-slate-600">{projectItems.length}</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {projectItems.map((x, i) => <div key={i}>{renderItem(x)}</div>)}
          </div>
        </div>
      )}
      {userItems.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[9px] font-black uppercase text-slate-400 bg-slate-500/10 border border-slate-700 px-2 py-0.5 rounded">User</span>
            <span className="text-[9px] font-mono text-slate-600">{userItems.length}</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {userItems.map((x, i) => <div key={i}>{renderItem(x)}</div>)}
          </div>
        </div>
      )}
    </section>
  );
}

function SumCard({ icon, label, value, userValue, tone }: { icon: React.ReactNode; label: string; value: number; userValue?: number; tone: "cyan" | "emerald" | "amber" | "purple" }) {
  const toneCls = tone === "cyan" ? "border-cyan-500/20 bg-cyan-500/5 text-cyan-400" : tone === "emerald" ? "border-emerald-500/20 bg-emerald-500/5 text-emerald-400" : tone === "purple" ? "border-purple-500/20 bg-purple-500/5 text-purple-400" : "border-amber-500/20 bg-amber-500/5 text-amber-400";
  return (
    <div className={`p-5 rounded-2xl border ${toneCls}`}>
      <div className="flex items-center gap-2 mb-2 opacity-80">{icon}<span className="text-[10px] font-black uppercase tracking-widest">{label}</span></div>
      <div className="flex items-baseline gap-2">
        <div className="text-3xl font-black tracking-tighter text-white">{value}</div>
        <div className="text-[10px] font-mono text-slate-500">project</div>
      </div>
      {userValue !== undefined && userValue > 0 && (
        <div className="text-[10px] font-mono text-slate-600 mt-1">+{userValue} at user scope</div>
      )}
    </div>
  );
}

function dayFromOffset(start: Date, offset: number) {
  const d = new Date(start); d.setDate(d.getDate() + offset);
  return d.toISOString().slice(0, 10);
}
function fmtNum(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}
function fmtDate(s: string) {
  const d = new Date(s + "T00:00:00");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function ProjectInsights({ insights, heatMetric, setHeatMetric }: { insights: any; heatMetric: "sessions" | "tokens"; setHeatMetric: (m: "sessions" | "tokens") => void }) {
  const { dailyArr, agents, topTokens, tools, topToolCount, current, longest, start, today, perAgent, dowHour, maxDowHour } = insights;

  const buildWeeks = (arr: { count: number; tokens: number }[]) => {
    const weeks: any[][] = [];
    let cur: any[] = [];
    const offset = new Date(start).getDay();
    for (let i = 0; i < offset; i++) cur.push(null);
    for (const d of arr) { cur.push(d); if (cur.length === 7) { weeks.push(cur); cur = []; } }
    if (cur.length) { while (cur.length < 7) cur.push(null); weeks.push(cur); }
    return weeks;
  };

  const totalTokens = agents.reduce((a: number, [, x]: any) => a + x.tokens, 0);
  const totalSessions = agents.reduce((a: number, [, x]: any) => a + x.count, 0);
  const DOW_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  return (
    <div className="space-y-6">
      {/* Row 1: Streaks + global tallies */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatTile label="Current Streak" value={`${current}d`} accent="#10b981" />
        <StatTile label="Longest Streak" value={`${longest}d`} accent="#f59e0b" />
        <StatTile label="Total Sessions" value={fmtNum(totalSessions)} accent="#3b82f6" />
        <StatTile label="Total Tokens" value={totalTokens.toLocaleString()} accent="#a855f7" />
      </div>

      {/* Row 2: Per-agent heatmaps */}
      <section className="bg-slate-900 rounded-3xl border border-slate-800 p-6">
        <div className="flex justify-between items-center mb-4">
          <div>
            <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest">Activity Heatmap — per agent</h3>
            <p className="text-[10px] font-mono text-slate-600 mt-0.5">Last 365 days · each row is one agent. Intensity scales within each agent so quiet agents stay visible.</p>
          </div>
          <div className="flex gap-1 bg-slate-950 border border-slate-800 rounded-lg p-1">
            {(["sessions", "tokens"] as const).map((m) => (
              <button key={m} onClick={() => setHeatMetric(m)}
                className={`px-3 py-1 rounded text-[9px] font-black uppercase tracking-widest transition-colors ${heatMetric === m ? "bg-blue-600 text-white" : "text-slate-500 hover:text-slate-300"}`}>
                {m}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-5">
          {perAgent.map(({ agent, stats, arr, max, maxTok }: any) => {
            const weeks = buildWeeks(arr);
            const color = AGENT_HEX[agent] || "#3b82f6";
            const denom = heatMetric === "sessions" ? max : maxTok;
            return (
              <div key={agent}>
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded" style={{ backgroundColor: color }} />
                    <span className="text-[10px] font-black uppercase tracking-widest" style={{ color }}>{agent}</span>
                  </div>
                  <span className="text-[9px] font-mono text-slate-500 tabular-nums">
                    {stats.count} sess · {fmtNum(stats.tokens)} tok
                  </span>
                </div>
                <div className="overflow-x-auto">
                  <div className="flex gap-[2px]" style={{ minWidth: weeks.length * 10 }}>
                    {weeks.map((wk, wi) => (
                      <div key={wi} className="flex flex-col gap-[2px]">
                        {wk.map((d: any, di: number) => {
                          const val = d ? (heatMetric === "sessions" ? d.count : d.tokens) : 0;
                          const intensity = val > 0 ? Math.max(0.2, val / (denom || 1)) : 0;
                          return (
                            <div key={di}
                              title={d ? `${fmtDate(dayFromOffset(start, wi*7+di - new Date(start).getDay()))} · ${d.count} sessions · ${fmtNum(d.tokens)} tokens` : ""}
                              className="w-[9px] h-[9px] rounded-[2px] border border-slate-900/60"
                              style={{ backgroundColor: intensity > 0 ? hexWithAlpha(color, intensity) : "#0f172a" }} />
                          );
                        })}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            );
          })}
          {perAgent.length === 0 && <div className="text-slate-600 italic text-sm">No activity in the last year.</div>}
        </div>
      </section>

      {/* Row 3: Agent leaderboard + migration ribbon */}
      <section className="bg-slate-900 rounded-3xl border border-slate-800 p-6">
        <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4">Agent Leaderboard</h3>
        <div className="space-y-3">
          {agents.length === 0 && <div className="text-slate-600 italic text-sm">No agent activity yet.</div>}
          {agents.map(([a, s]: any) => {
            const pct = (s.tokens / (topTokens || 1)) * 100;
            return (
              <div key={a} className="grid grid-cols-[80px_1fr_auto] items-center gap-4">
                <span className="text-[10px] font-black uppercase tracking-wider" style={{ color: AGENT_HEX[a] || "#64748b" }}>{a}</span>
                <div className="h-2 bg-slate-950 rounded-full overflow-hidden border border-slate-800/50">
                  <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: AGENT_HEX[a] || "#3b82f6" }} />
                </div>
                <span className="text-[10px] font-mono text-slate-500 tabular-nums whitespace-nowrap">
                  {s.count} sess · {fmtNum(s.tokens)} tok
                </span>
              </div>
            );
          })}
        </div>

        {agents.length > 1 && (
          <>
            <h4 className="text-[10px] font-black text-slate-500 uppercase tracking-widest mt-8 mb-3">Agent Migration</h4>
            <MigrationRibbon agents={agents} start={start} today={today} />
          </>
        )}
      </section>

      {/* Row 4: Tools + Hour-of-day */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <section className="bg-slate-900 rounded-3xl border border-slate-800 p-6">
          <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4">Tools & MCPs Used</h3>
          <p className="text-[10px] font-mono text-slate-600 mb-4">Number of sessions each tool appeared in, colored by dominant caller.</p>
          {tools.length === 0 ? (
            <div className="text-slate-600 italic text-sm">No tool invocations recorded.</div>
          ) : (
            <div className="space-y-2 max-h-96 overflow-y-auto pr-2">
              {tools.slice(0, 30).map(([t, info]: any) => {
                const top = Object.entries(info.byAgent).sort((a: any, b: any) => b[1] - a[1])[0]?.[0];
                const color = AGENT_HEX[top as string] || "#64748b";
                return (
                  <div key={t} className="grid grid-cols-[140px_1fr_auto] items-center gap-3">
                    <span className="text-xs font-mono text-slate-300 truncate" title={t}>{t}</span>
                    <div className="h-1.5 bg-slate-950 rounded-full overflow-hidden border border-slate-800/50">
                      <div className="h-full" style={{ width: `${(info.sessions / topToolCount) * 100}%`, backgroundColor: color }} />
                    </div>
                    <span className="text-[10px] font-mono text-slate-500 tabular-nums whitespace-nowrap">{info.sessions}</span>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        <section className="bg-slate-900 rounded-3xl border border-slate-800 p-6">
          <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4">When You Work</h3>
          <p className="text-[10px] font-mono text-slate-600 mb-6">Session starts by day-of-week × hour (local time).</p>
          <div className="grid grid-cols-[40px_1fr] gap-2 items-center">
            <div />
            <div className="grid gap-[2px] text-[7px] font-mono text-slate-500 mb-1" style={{ gridTemplateColumns: "repeat(24, minmax(0, 1fr))" }}>
              {Array.from({ length: 24 }, (_, h) => (
                <div key={h} className="text-center">{h % 2 === 0 ? h : ""}</div>
              ))}
            </div>
            {DOW_LABELS.map((label, d) => (
              <Fragment key={d}>
                <div className="text-[10px] font-bold text-slate-500 pr-2 text-right uppercase tracking-tighter">{label}</div>
                <div className="grid gap-[2px]" style={{ gridTemplateColumns: "repeat(24, minmax(0, 1fr))" }}>
                  {dowHour[d].map((v: number, h: number) => {
                    const intensity = v > 0 ? Math.max(0.2, v / maxDowHour) : 0;
                    return (
                      <div key={h}
                        title={`${label} ${h.toString().padStart(2,'0')}:00 — ${v} sessions`}
                        className="aspect-square rounded-[1px] transition-colors hover:ring-1 hover:ring-white/30"
                        style={{ backgroundColor: intensity > 0 ? hexWithAlpha("#3b82f6", intensity) : "#0f172a" }} />
                    );
                  })}
                </div>
              </Fragment>
            ))}
          </div>
          <div className="flex items-center justify-end gap-2 mt-6 text-[9px] font-mono text-slate-500">
            <span className="opacity-50 italic">quiet</span>
            <span className="flex gap-[1px]">
              {[0, 0.2, 0.4, 0.6, 0.8, 1].map(x => (
                <span key={x} className="w-[12px] h-[12px] rounded-[1px]" style={{ backgroundColor: x === 0 ? "#0f172a" : hexWithAlpha("#3b82f6", x) }} />
              ))}
            </span>
            <span className="opacity-50 italic">busy</span>
          </div>
        </section>
      </div>
    </div>
  );
}

function StatTile({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <div className="bg-slate-900 rounded-2xl border border-slate-800 p-5">
      <div className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2" style={{ color: accent }}>{label}</div>
      <div className="text-2xl font-black tracking-tighter text-white">{value}</div>
    </div>
  );
}

function MigrationRibbon({ agents, start, today }: { agents: [string, any][]; start: Date; today: Date }) {
  const span = Math.max(1, today.getTime() - start.getTime());
  return (
    <div className="space-y-2">
      {agents.map(([a, s]: any) => {
        const firstPct = Math.max(0, ((s.firstSeen - start.getTime()) / span) * 100);
        const lastPct = Math.min(100, ((s.lastSeen - start.getTime()) / span) * 100);
        const width = Math.max(1, lastPct - firstPct);
        return (
          <div key={a} className="grid grid-cols-[80px_1fr] items-center gap-4">
            <span className="text-[10px] font-black uppercase tracking-wider" style={{ color: AGENT_HEX[a] || "#64748b" }}>{a}</span>
            <div className="relative h-4 bg-slate-950 rounded-full border border-slate-800/50 overflow-hidden">
              <div className="absolute top-0 h-full rounded-full" style={{ left: `${firstPct}%`, width: `${width}%`, backgroundColor: AGENT_HEX[a] || "#3b82f6", opacity: 0.8 }} />
              <div className="absolute top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-white" style={{ left: `calc(${firstPct}% - 4px)` }} title={`first: ${new Date(s.firstSeen).toLocaleDateString()}`} />
              <div className="absolute top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-white" style={{ left: `calc(${lastPct}% - 4px)` }} title={`last: ${new Date(s.lastSeen).toLocaleDateString()}`} />
            </div>
          </div>
        );
      })}
      <div className="grid grid-cols-[80px_1fr] items-center gap-4 pt-1">
        <span />
        <div className="flex justify-between text-[9px] font-mono text-slate-600">
          <span>{start.toLocaleDateString(undefined, { month: "short", year: "numeric" })}</span>
          <span>today</span>
        </div>
      </div>
    </div>
  );
}

function hexWithAlpha(hex: string, alpha: number) {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha.toFixed(2)})`;
}
