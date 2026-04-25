"use client";

import { useEffect, useState, useMemo } from "react";
import { Folder, Terminal, Database, Sparkles, ArrowLeft, Cpu, Users, ClipboardList, Zap, GitBranch, Orbit, ArrowRight, Search, MousePointer2, Code2 } from "lucide-react";
import Link from "next/link";

interface Project {
  name: string;
  path: string;
  session_count: number;
  agents: string[];
  mcp_tools: string[];
  subagent_count: number;
  configured_subagent_count?: number;
  plan_count: number;
  tokens?: { input: number; output: number; cached: number; total: number; cost: number };
}

function formatCost(usd: number): string {
  if (!usd) return "$0.00";
  if (usd < 0.01) return `<$0.01`;
  return `$${usd.toFixed(2)}`;
}

function formatTokens(n: number): string {
  if (!n) return "0";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

const AGENT_ICONS: Record<string, any> = {
  claude: { icon: Terminal, color: "text-orange-400" },
  codex: { icon: Database, color: "text-purple-400" },
  gemini: { icon: Sparkles, color: "text-cyan-400" },
  antigravity: { icon: Orbit, color: "text-emerald-400" },
  qwen: { icon: Cpu, color: "text-blue-400" },
  vibe: { icon: Zap, color: "text-pink-400" },
  cursor: { icon: MousePointer2, color: "text-blue-400" },
  copilot: { icon: GitBranch, color: "text-indigo-400" },
  opencode: { icon: Code2, color: "text-amber-400" }
};

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");

  useEffect(() => {
    fetch("http://localhost:8000/projects")
      .then((res) => res.json())
      .then((data) => {
        setProjects(data.sort((a: Project, b: Project) => b.session_count - a.session_count));
        setLoading(false);
      })
      .catch((err) => {
        console.error("Failed to fetch projects:", err);
        setLoading(false);
      });
  }, []);

  const filteredProjects = useMemo(() => {
    return projects.filter(project => 
      project.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      project.path.toLowerCase().includes(searchTerm.toLowerCase())
    );
  }, [projects, searchTerm]);

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-10 pb-20">
      <header className="flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div>
          <Link href="/" className="text-blue-400 flex items-center gap-2 hover:underline mb-4 text-sm font-medium">
            <ArrowLeft size={16} /> Back to Dashboard
          </Link>
          <h1 className="text-4xl font-black text-white tracking-tight flex items-center gap-3">
            <Folder className="text-blue-500" size={32} />
            Projects
          </h1>
          <p className="text-slate-400 mt-2 font-medium">Activity grouped by workspace.</p>
        </div>

        <div className="relative w-full md:w-80">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" size={18} />
          <input 
            type="text"
            placeholder="Search projects..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-slate-900 border border-slate-800 rounded-2xl py-3 pl-12 pr-4 text-sm text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all placeholder:text-slate-600 shadow-xl"
          />
        </div>
      </header>

      {loading ? (
        <div className="text-center p-32 text-slate-500 flex flex-col items-center gap-4 text-slate-100">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-500 mx-auto"></div>
          <span className="font-mono text-xs uppercase tracking-widest">Mapping Workspace Traces...</span>
        </div>
      ) : filteredProjects.length === 0 ? (
        <div className="text-center p-32 bg-slate-900 rounded-3xl border border-dashed border-slate-800 text-slate-500">
           <Search size={48} className="mx-auto mb-4 opacity-20" />
           <p className="font-medium">No projects found matching "{searchTerm}"</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {filteredProjects.map((project) => (
            <div key={project.path} className="bg-slate-900 p-8 rounded-3xl shadow-2xl border border-slate-800 hover:border-slate-600 transition-all group flex flex-col h-full relative overflow-hidden">
              <div className="flex items-start justify-between mb-6">
                <div className="bg-blue-600/10 p-4 rounded-2xl border border-blue-500/20">
                  <Folder className="text-blue-400" size={28} />
                </div>
                <div className="flex gap-2 bg-slate-950/50 p-2 rounded-xl border border-slate-800">
                  {project.agents.map(agentKey => {
                    const config = AGENT_ICONS[agentKey];
                    if (!config) return null;
                    const Icon = config.icon;
                    return <Icon key={agentKey} size={14} className={config.color} />;
                  })}
                </div>
              </div>
              
              <h2 className="text-xl font-bold text-white mb-2 truncate group-hover:text-blue-400 transition-colors" title={project.name}>
                {project.name}
              </h2>
              
              <div className="flex-1 min-w-0 mb-6">
                <p className="text-[10px] text-slate-500 font-mono truncate bg-slate-950/50 px-2 py-1 rounded inline-block max-w-full" title={project.path}>
                  {project.path}
                </p>
              </div>
              
              {project.mcp_tools.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-8">
                  {project.mcp_tools.slice(0, 5).map(tool => (
                    <span key={tool} className="text-[9px] font-bold uppercase tracking-wider bg-slate-800 text-slate-400 px-2 py-1 rounded-lg border border-slate-700">
                      {tool}
                    </span>
                  ))}
                  {project.mcp_tools.length > 5 && (
                    <span className="text-[9px] text-slate-600 font-bold ml-1 flex items-center">+{project.mcp_tools.length - 5}</span>
                  )}
                </div>
              )}

              <div className="flex items-center justify-between mt-auto pt-6 border-t border-slate-800/50">
                <div className="flex gap-5">
                  <div className="flex flex-col items-center gap-1" title="Sessions">
                    <span className="text-lg font-black text-white leading-none">{project.session_count}</span>
                    <span className="text-[8px] font-black text-slate-500 uppercase tracking-widest">Sess</span>
                  </div>
                  <div className="flex flex-col items-center gap-1" title="Subagents">
                    <span className="text-lg font-black text-purple-400 leading-none">{(project.configured_subagent_count || 0) + (project.subagent_count || 0)}</span>
                    <span className="text-[8px] font-black text-slate-500 uppercase tracking-widest">Subs</span>
                  </div>
                  {project.plan_count > 0 && (
                     <div className="flex flex-col items-center gap-1" title="Plans">
                        <span className="text-lg font-black text-emerald-400 leading-none">{project.plan_count}</span>
                        <span className="text-[8px] font-black text-slate-500 uppercase tracking-widest">Plans</span>
                     </div>
                  )}
                  {(project.tokens?.total || 0) > 0 && (
                     <div className="flex flex-col items-center gap-1" title={`${(project.tokens?.total || 0).toLocaleString()} tokens`}>
                        <span className="text-lg font-black text-amber-400 leading-none tabular-nums">{formatCost(project.tokens?.cost || 0)}</span>
                        <span className="text-[8px] font-black text-slate-500 uppercase tracking-widest">Cost</span>
                     </div>
                  )}
                </div>
                
                <div className="flex flex-col items-end gap-2">
                   <Link 
                      href={`/projects/${encodeURIComponent(project.path)}`} 
                      className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all shadow-lg flex items-center gap-2 group/btn"
                   >
                      Activity <ArrowRight size={14} className="group-hover:translate-x-1 transition-transform" />
                   </Link>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
