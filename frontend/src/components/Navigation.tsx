"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Folder, BarChart3, Activity, Orbit, ChevronLeft, PanelLeftOpen, PanelLeftClose, Server } from "lucide-react";
import { useEffect, useState } from "react";

interface NavigationProps {
  isCollapsed: boolean;
  setIsCollapsed: (collapsed: boolean) => void;
}

export default function Navigation({ isCollapsed, setIsCollapsed }: NavigationProps) {
  const pathname = usePathname();
  const [availableAgents, setAvailableAgents] = useState<string[]>([]);

  useEffect(() => {
    fetch("http://127.0.0.1:8000/agents")
      .then(res => res.json())
      .then(data => setAvailableAgents(data))
      .catch(() => {});
  }, []);

  const links = [
    { name: "Dashboard", href: "/", icon: LayoutDashboard },
    { name: "Projects", href: "/projects", icon: Folder },
    { name: "Analytics", href: "/analytics", icon: BarChart3 },
    // { name: "Local Lab", href: "/locallab", icon: Server },
  ];

  return (
    <nav className={`${isCollapsed ? "w-20" : "w-64"} bg-slate-900 border-r border-slate-800 h-screen sticky top-0 flex flex-col p-4 transition-all duration-300 ease-in-out z-[100]`}>
      <div className={`flex items-center ${isCollapsed ? "justify-center" : "justify-between"} mb-10 mt-2`}>
        {!isCollapsed && (
          <div className="flex items-center gap-3 px-2">
            <div className="bg-blue-600 p-2 rounded-lg shadow-lg shadow-blue-900/20">
              <Activity className="text-white" size={20} />
            </div>
            <span className="font-black text-white tracking-tighter text-lg uppercase">AGENT</span>
          </div>
        )}
        {isCollapsed && (
           <div className="bg-blue-600 p-2 rounded-lg shadow-lg shadow-blue-900/20">
              <Activity className="text-white" size={20} />
           </div>
        )}
      </div>

      <div className="space-y-2">
        {links.map((link) => {
          const Icon = link.icon;
          const isActive = pathname === link.href || (link.href !== "/" && pathname.startsWith(link.href));
          return (
            <Link
              key={link.name}
              href={link.href}
              title={isCollapsed ? link.name : ""}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all relative group ${
                isActive 
                  ? "bg-blue-600/10 text-blue-400 border border-blue-600/20 shadow-[0_0_15px_rgba(37,99,235,0.05)]" 
                  : "text-slate-500 hover:text-slate-200 hover:bg-slate-800/50 border border-transparent"
              }`}
            >
              <Icon size={20} strokeWidth={isActive ? 2.5 : 2} />
              {!isCollapsed && <span className="text-sm font-bold uppercase tracking-widest">{link.name}</span>}
              {isCollapsed && isActive && (
                 <div className="absolute left-0 w-1 h-6 bg-blue-500 rounded-r-full"></div>
              )}
            </Link>
          );
        })}
      </div>

      <div className="mt-auto space-y-4">
        {/* Agent Indicators */}
        {!isCollapsed && (
          <div className="p-4 bg-slate-950/50 rounded-2xl border border-slate-800/50">
            <div className="text-[9px] font-black text-slate-600 uppercase tracking-[0.2em] mb-3">Connected</div>
            <div className="space-y-2.5">
                {availableAgents.includes("claude") && <AgentDot color="bg-orange-500" label="Claude" />}
                {availableAgents.includes("codex") && <AgentDot color="bg-purple-500" label="Codex" />}
                {availableAgents.includes("gemini") && <AgentDot color="bg-cyan-500" label="Gemini" />}
                {availableAgents.includes("antigravity") && <AgentDot color="bg-emerald-500" label="Antigravity" />}
                {availableAgents.includes("cursor") && <AgentDot color="bg-blue-500" label="Cursor" />}
            </div>
          </div>
        )}

        <button 
          onClick={() => setIsCollapsed(!isCollapsed)}
          className="w-full flex items-center justify-center p-3 rounded-xl bg-slate-800/50 hover:bg-slate-800 text-slate-400 hover:text-white transition-all border border-slate-700/50"
        >
          {isCollapsed ? <PanelLeftOpen size={20} /> : <div className="flex items-center gap-2"><PanelLeftClose size={18} /><span className="text-[10px] font-black uppercase tracking-widest">Collapse</span></div>}
        </button>
      </div>
    </nav>
  );
}

function AgentDot({ color, label }: { color: string, label: string }) {
  return (
    <div className="flex items-center gap-2 text-[10px] text-slate-400 font-bold uppercase tracking-tight">
      <div className={`w-1.5 h-1.5 rounded-full ${color} shadow-[0_0_8px_rgba(255,255,255,0.1)]`}></div>
      {label}
    </div>
  );
}
