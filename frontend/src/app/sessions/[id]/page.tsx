"use client";

import React, { useEffect, useState, useMemo, useRef } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ArrowLeft, Brain, Code, MessageSquare, Terminal, User, FileText, Activity, Zap, Info, Sparkles, GitBranch, LayoutPanelLeft, ListMusic, ChevronRight, ChevronLeft, Play, Pause, Wrench, Cpu, Folder, AlertTriangle, Hash, Clock, FileCode, Settings2, ChevronDown, ChevronUp } from "lucide-react";
import Link from "next/link";
import { format } from "date-fns";

interface Artifact {
  name: string;
  path: string;
  type: 'video' | 'image' | 'document' | 'terminal';
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
  plans: any[];
  model?: string;
  tokens?: { input: number; output: number; cached: number; total: number };
  artifacts?: Artifact[];
}

interface Event {
  id?: string;
  type: string;
  role?: string;
  timestamp?: string;
  normalized_timestamp?: number;
  payload?: any;
  message?: any;
  attachment?: any;
  toolUseResult?: any;
  uuid?: string;
  content?: any;
  thoughts?: any[];
  toolCalls?: any[];
}

type StepKind = "user" | "assistant" | "reasoning" | "tool" | "tool_result" | "meta" | "other";

interface Step {
  idx: number;
  kind: StepKind;
  label: string;
  ts?: number;
}

function eventKind(evt: Event): StepKind {
  const type = evt.type;
  const role = evt.role || evt.message?.role;
  
  if (type === "session_meta" || type === "event_msg" || type === "turn_context") return "meta";
  if (type === "agent_reasoning" || evt.thoughts || evt.payload?.type === "reasoning" || type === "assistant_thinking") return "reasoning";
  if (Array.isArray(evt.payload) && evt.payload.some((p: any) => p.kind === "thinking" || p.type === "thinking")) return "reasoning";
  if (role === "assistant" && Array.isArray(evt.message?.content) && evt.message.content.some((c: any) => c.type === "thinking" || c.type === "thought")) return "reasoning";
  if (evt.toolCalls || evt.payload?.type === "function_call" || evt.payload?.type === "tool_use") return "tool";
  if (role === "assistant" && Array.isArray(evt.message?.content) && evt.message.content.some((c: any) => c.type === "tool_use")) return "tool";
  if ((type === "user" || role === "user") && Array.isArray(evt.message?.content) && evt.message.content.some((c: any) => c.type === "tool_result")) return "tool_result";
  if (type === "user" || role === "user" || (type === "response_item" && evt.payload?.role === "user") || type === "request_item") return "user";
  if (type === "assistant" || role === "assistant" || role === "model" || role === "gemini" || type === "model" || type === "gemini" || (type === "response_item" && evt.payload?.role === "assistant" && evt.payload?.type === "message")) return "assistant";
  return "other";
}

function normalizeTs(evt: Event): number | undefined {
  if (typeof evt.normalized_timestamp === "number") return evt.normalized_timestamp;
  if (evt.timestamp) {
    const t = new Date(evt.timestamp).getTime();
    if (!Number.isNaN(t)) return t;
  }
  return undefined;
}

const stepRingClass: Record<StepKind, string> = {
  user: "ring-2 ring-blue-500/70",
  assistant: "ring-2 ring-emerald-500/70",
  reasoning: "ring-2 ring-amber-500/70",
  tool: "ring-2 ring-sky-500/70",
  tool_result: "ring-2 ring-slate-500/70",
  meta: "ring-2 ring-slate-600/60",
  other: "ring-2 ring-slate-600/60",
};

function stepLabel(evt: Event, kind: StepKind): string {
  if (kind === "tool") {
    if (evt.toolCalls?.[0]) return evt.toolCalls[0].name;
    const tu = Array.isArray(evt.message?.content) ? evt.message.content.find((c: any) => c.type === "tool_use") : null;
    if (tu) return tu.name;
    if (evt.payload?.type === "function_call" || evt.payload?.type === "tool_use") return evt.payload.name;
  }
  if (kind === "user") {
    const c = evt.message?.content || evt.payload?.content;
    const text = Array.isArray(c) ? c.map((p: any) => p.text || p.input_text).filter(Boolean).join(" ") : (typeof c === "string" ? c : "");
    return (text || "User Query").slice(0, 40);
  }
  if (kind === "assistant") return "Response";
  if (kind === "reasoning") return "Reasoning";
  if (kind === "tool_result") return "Tool output";
  if (kind === "meta") return evt.type;
  return evt.type || "event";
}

export default function SessionDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params?.id as string;
  const searchParams = useSearchParams();
  const agent = searchParams.get("agent");
  
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [sessionInfo, setSessionInfo] = useState<Session | null>(null);
  
  // Trace View States
  const [splitView, setSplitView] = useState(false);
  const [playbackIndex, setPlaybackIndex] = useState(1000);
  const [isPlaying, setIsPlaying] = useState(false);
  const [sidebarTab, setSidebarTab] = useState<"context" | "tools" | "artifacts" | "raw">("context");
  const [activeStep, setActiveStep] = useState<number | null>(null);
  const [timelineOpen, setTimelineOpen] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [projectConfig, setProjectConfig] = useState<any>(null);
  const stepRefs = useRef<Record<number, HTMLDivElement | null>>({});

  useEffect(() => {
    if (id && agent) {
      // 1. Fetch Session Metadata (for tokens/insights)
      fetch(`http://localhost:8000/sessions`)
        .then(res => res.json())
        .then(data => {
           const info = data.find((s: any) => s.id === id);
           if (info) setSessionInfo(info);
        });

      // 2. Fetch Detailed Trace
      fetch(`http://localhost:8000/sessions/${id}?agent=${agent}`)
        .then((res) => res.json())
        .then((data) => {
          let evts = [];
          if (agent === 'gemini' || agent === 'antigravity') {
            evts = (data.messages || []).map((m: any) => ({
              ...m,
              type: m.type === 'gemini' ? 'assistant' : m.type
            }));
          } else {
            evts = Array.isArray(data) ? data : [];
          }
          setEvents(evts);
          setPlaybackIndex(evts.length);
          setLoading(false)
        })
        .catch((err) => {
          console.error("Failed to fetch session detail:", err);
          setLoading(false);
        });
    }
  }, [id, agent]);

  // Timeline Auto-play logic
  useEffect(() => {
    if (!isPlaying) return;
    const interval = setInterval(() => {
      setPlaybackIndex((prev) => {
        if (prev >= events.length) {
          setIsPlaying(false);
          return prev;
        }
        const next = prev + 1;
        const target = next - 1;
        setActiveStep(target);
        requestAnimationFrame(() => {
          stepRefs.current[target]?.scrollIntoView({ behavior: "smooth", block: "center" });
        });
        return next;
      });
    }, 600);
    return () => clearInterval(interval);
  }, [isPlaying, events.length]);

  const togglePlay = () => {
    if (!isPlaying && playbackIndex >= events.length) {
      setPlaybackIndex(0);
      setActiveStep(null);
    }
    setIsPlaying((v) => !v);
  };

  const visibleEvents = useMemo(() => {
     return events.slice(0, playbackIndex);
  }, [events, playbackIndex]);

  // SAFE Helper to check content for a type (Fixes TypeError)
  const hasContentType = (event: Event, type: string) => {
    const content = event.message?.content;
    if (Array.isArray(content)) {
      return content.some((c: any) => c.type === type);
    }
    return false;
  };

  // Steps for left index
  const steps: Step[] = useMemo(
    () =>
      events.map((evt, idx) => {
        const kind = eventKind(evt);
        return { idx, kind, label: stepLabel(evt, kind), ts: normalizeTs(evt) };
      }),
    [events]
  );

  // Stats
  const stats = useMemo(() => {
    let toolCalls = 0;
    let reasoning = 0;
    let errors = 0;
    let userTurns = 0;
    const timestamps: number[] = [];
    events.forEach((e) => {
      const k = eventKind(e);
      if (k === "tool") toolCalls++;
      if (k === "reasoning") reasoning++;
      if (k === "user") userTurns++;
      const ts = normalizeTs(e);
      if (ts) timestamps.push(ts);
      const raw = JSON.stringify(e).toLowerCase();
      if (raw.includes('"is_error":true') || raw.includes("exception")) errors++;
    });
    let duration = "—";
    if (timestamps.length >= 2) {
      const ms = Math.max(...timestamps) - Math.min(...timestamps);
      duration = ms > 60000 ? `${(ms / 60000).toFixed(1)}m` : `${(ms / 1000).toFixed(1)}s`;
    }
    return { total: events.length, toolCalls, reasoning, userTurns, errors, duration };
  }, [events]);

  // Models used across the session (distinct, in order of first appearance)
  const modelsUsed = useMemo(() => {
    const seen = new Set<string>();
    const order: string[] = [];
    const push = (m?: string) => {
      if (m && !seen.has(m)) {
        seen.add(m);
        order.push(m);
      }
    };
    events.forEach((e: any) => {
      push(e.message?.model); // Claude per-message
      push(e.model); // some providers
      if (e.type === "session_meta") {
        push(e.payload?.model);
        push(e.payload?.model_provider);
      }
      if (e.type === "turn_context") {
        push(e.payload?.model);
        push(e.payload?.model_provider);
      }
      if (e.payload?.model) push(e.payload.model);
    });
    return order;
  }, [events]);

  // Context Inspector
  const context = useMemo(() => {
    const meta = events.find((e) => e.type === "session_meta")?.payload;
    const turnCtx = events.find((e) => e.type === "turn_context")?.payload;
    const firstSystem = events.find((e) => e.type === "user" && typeof e.message?.content === "string")?.message?.content;
    return {
      sessionId: id,
      agent: sessionInfo?.agent,
      model: modelsUsed[0] || meta?.model || meta?.model_provider || sessionInfo?.model,
      modelsUsed,
      provider: meta?.model_provider,
      cwd: meta?.cwd || sessionInfo?.project,
      sandbox: meta?.sandbox_policy || turnCtx?.sandbox_policy,
      approvalPolicy: meta?.approval_policy || turnCtx?.approval_policy,
      reasoningEffort: turnCtx?.model_reasoning_effort,
      instructions: meta?.instructions || turnCtx?.instructions,
      env: meta?.env,
      systemPrompt: typeof firstSystem === "string" ? firstSystem : undefined,
      projectConfig,
    };
  }, [events, sessionInfo, modelsUsed, projectConfig, id]);

  // Fetch per-project config (skills + MCPs) once we know the cwd
  useEffect(() => {
    const cwd = events.find((e) => e.type === "session_meta")?.payload?.cwd || sessionInfo?.project;
    if (!cwd) return;
    fetch(`http://localhost:8000/config?project=${encodeURIComponent(cwd)}`)
      .then((r) => r.json())
      .then(setProjectConfig)
      .catch(() => {});
  }, [events, sessionInfo]);

  // Tool summary
  const toolSummary = useMemo(() => {
    const rows: { name: string; start: number; duration: number }[] = [];
    events.forEach((evt, idx) => {
      const ts = normalizeTs(evt);
      if (evt.message?.role === "assistant" && Array.isArray(evt.message?.content)) {
        const tu = evt.message.content.find((c: any) => c.type === "tool_use");
        if (tu && ts) {
          const result = events.slice(idx + 1).find((e) => e.type === "user" && Array.isArray(e.message?.content) && e.message.content.some((c: any) => c.tool_use_id === tu.id));
          const end = (result && normalizeTs(result)) || ts + 200;
          rows.push({ name: tu.name, start: ts, duration: end - ts });
        }
      }
      if (evt.toolCalls && ts) {
        evt.toolCalls.forEach((tc: any) => rows.push({ name: tc.name, start: ts, duration: 300 }));
      }
      if ((evt.payload?.type === "function_call" || evt.payload?.type === "tool_use") && ts) {
         rows.push({ name: evt.payload.name, start: ts, duration: 400 });
      }
    });
    const m: Record<string, { count: number; total: number }> = {};
    rows.forEach((r) => {
      m[r.name] = m[r.name] || { count: 0, total: 0 };
      m[r.name].count++;
      m[r.name].total += r.duration;
    });
    return Object.entries(m)
      .map(([name, v]) => ({ name, count: v.count, avg: v.total / v.count }))
      .sort((a, b) => b.count - a.count);
  }, [events]);

  const jumpTo = (idx: number) => {
    setActiveStep(idx);
    setPlaybackIndex((p) => Math.max(p, idx + 1));
    requestAnimationFrame(() => {
      stepRefs.current[idx]?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  };

  // Waterfall Logic
  const waterfallData = useMemo(() => {
     const tools: any[] = [];
     events.forEach((evt, idx) => {
        let toolName = "";
        let startTime = evt.normalized_timestamp || (evt.timestamp ? new Date(evt.timestamp).getTime() : 0);
        
        // Claude Tool Call Detection
        if (evt.type === "assistant" && Array.isArray(evt.message?.content)) {
           const tu = evt.message.content.find((c: any) => c.type === "tool_use");
           if (tu) {
              toolName = tu.name;
              // Look ahead for tool_result from user
              const result = events.slice(idx).find(e => e.type === "user" && Array.isArray(e.message?.content) && e.message.content.some((c: any) => c.tool_use_id === tu.id));
              const endTime = result?.normalized_timestamp || (result?.timestamp ? new Date(result.timestamp).getTime() : startTime + 2000);
              tools.push({ name: toolName, start: startTime, end: endTime, id: tu.id });
           }
        }
        // Gemini / Antigravity Tool Call Detection
        if (evt.toolCalls) {
           evt.toolCalls.forEach(tc => {
              tools.push({ name: tc.name, start: startTime, end: startTime + 800, id: tc.name + idx });
           });
        }
        // Codex Tool Call Detection
        if (evt.payload?.type === "function_call" || evt.payload?.type === "tool_use") {
           tools.push({ name: evt.payload.name, start: startTime, end: startTime + 500, id: (evt.payload.name || "tool") + idx });
        }
     });
     return tools;
  }, [events]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 font-sans flex flex-col">
      <header className="bg-slate-900/50 border-b border-slate-800 p-6 sticky top-0 z-50 backdrop-blur-md">
        <div className="max-w-[1600px] mx-auto flex flex-col gap-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
               <button
                  onClick={() => router.back()}
                  className="bg-slate-800 p-2 rounded-xl hover:bg-slate-700 transition-colors shadow-lg"
                  title="Back"
               >
                  <ArrowLeft size={20} />
               </button>
               <div>
                  <h1 className="text-xl font-black text-white flex items-center gap-3 tracking-tight">
                     <Activity className="text-blue-500" size={24} />
                     SESSION TRACE
                  </h1>
                  <div className="flex items-center gap-3 mt-1">
                     <span className={`px-2 py-0.5 rounded text-[9px] font-black uppercase border shadow-sm ${
                        agent === 'claude' ? 'bg-orange-500/10 text-orange-400 border-orange-500/20' : 
                        agent === 'codex' ? 'bg-purple-500/10 text-purple-400 border-purple-500/20' :
                        agent === 'gemini' ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20' :
                        agent === 'cursor' ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' :
                        'bg-slate-500/10 text-slate-400 border-slate-500/20'
                     }`}>
                        {agent}
                     </span>
                     <span className="text-[10px] font-mono text-slate-500 bg-slate-950 px-2 py-0.5 rounded border border-slate-800">ID: {id.slice(0, 12)}...</span>
                     {modelsUsed.slice(0, 3).map((m) => (
                        <span key={m} title={m} className="flex items-center gap-1 text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20 max-w-[260px] truncate">
                           <Cpu size={10} /> {m}
                        </span>
                     ))}
                     {modelsUsed.length > 3 && (
                        <span className="text-[10px] font-mono text-slate-500">+{modelsUsed.length - 3}</span>
                     )}
                  </div>
               </div>
            </div>

            <div className="flex items-center gap-3 flex-wrap justify-end">
               {/* Stats strip */}
               <div className="flex items-center gap-1.5 flex-wrap">
                  <StatPill icon={<Hash size={12} />} label="Steps" value={stats.total} />
                  <StatPill icon={<Wrench size={12} />} label="Tools" value={stats.toolCalls} tone="blue" />
                  {sessionInfo?.artifacts && sessionInfo.artifacts.length > 0 && <StatPill icon={<LayoutPanelLeft size={12} />} label="Arts" value={sessionInfo.artifacts.length} tone="emerald" />}
                  <StatPill icon={<Brain size={12} />} label="Reason" value={stats.reasoning} tone="amber" />
                  <StatPill icon={<User size={12} />} label="Turns" value={stats.userTurns} />
                  <StatPill icon={<Clock size={12} />} label="Dur" value={stats.duration} />
                  <StatPill icon={<AlertTriangle size={12} />} label="Err" value={stats.errors} tone={stats.errors > 0 ? "red" : undefined} />
               </div>
               {/* RESTORED: Token Telemetry */}
               {sessionInfo?.tokens && (
                  <div className="hidden lg:flex items-center gap-4 bg-slate-950 px-4 py-2 rounded-xl border border-slate-800 shadow-inner">
                     <div className="flex flex-col items-center">
                        <span className="text-[8px] font-black text-slate-500 uppercase tracking-widest">Input</span>
                        <span className="text-xs font-bold text-slate-300">{sessionInfo.tokens.input.toLocaleString()}</span>
                     </div>
                     <div className="w-px h-6 bg-slate-800"></div>
                     <div className="flex flex-col items-center">
                        <span className="text-[8px] font-black text-slate-500 uppercase tracking-widest">Output</span>
                        <span className="text-xs font-bold text-slate-300">{sessionInfo.tokens.output.toLocaleString()}</span>
                     </div>
                     <div className="w-px h-6 bg-slate-800"></div>
                     <div className="flex flex-col items-center">
                        <span className="text-[8px] font-black text-cyan-500 uppercase tracking-widest">Cache Hit</span>
                        <span className="text-xs font-bold text-cyan-400">{sessionInfo.tokens.cached.toLocaleString()}</span>
                     </div>
                  </div>
               )}

               <button 
                  onClick={() => setSplitView(!splitView)}
                  className={`p-2 px-4 rounded-xl border transition-all flex items-center gap-2 text-[10px] font-black uppercase tracking-widest ${splitView ? 'bg-blue-600 border-blue-500 text-white shadow-lg shadow-blue-900/20' : 'bg-slate-900 border-slate-800 text-slate-400 hover:border-slate-700'}`}
               >
                  <LayoutPanelLeft size={16} />
                  {splitView ? 'Unified' : 'Split Brain'}
               </button>
            </div>
          </div>

          {/* Timeline Scrubber */}
          {!loading && events.length > 0 && (
             <div className="bg-slate-950 p-4 rounded-2xl border border-slate-800 flex items-center gap-6 shadow-inner">
                <div className="flex items-center gap-2">
                   <button 
                     onClick={() => setPlaybackIndex(Math.max(0, playbackIndex - 1))}
                     className="p-1.5 hover:bg-slate-800 rounded-lg text-slate-400 transition-colors"
                   >
                      <ChevronLeft size={18} />
                   </button>
                   <button
                     onClick={togglePlay}
                     title={isPlaying ? "Pause replay" : (playbackIndex >= events.length ? "Replay from start" : "Resume replay")}
                     className="p-2 bg-blue-600 text-white rounded-xl hover:bg-blue-500 shadow-lg shadow-blue-900/30 transition-all active:scale-95"
                   >
                      {isPlaying ? <Pause size={18} /> : <Play size={18} />}
                   </button>
                   <button 
                     onClick={() => setPlaybackIndex(Math.min(events.length, playbackIndex + 1))}
                     className="p-1.5 hover:bg-slate-800 rounded-lg text-slate-400 transition-colors"
                   >
                      <ChevronRight size={18} />
                   </button>
                </div>
                
                <div className="flex-1 flex flex-col gap-2">
                   <input 
                      type="range" 
                      min="0" 
                      max={events.length} 
                      value={playbackIndex} 
                      onChange={(e) => setPlaybackIndex(parseInt(e.target.value))}
                      className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-blue-500"
                   />
                   <div className="flex justify-between text-[8px] font-black text-slate-600 uppercase tracking-[0.2em]">
                      <span>Session Start</span>
                      <span className="text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded-full border border-blue-500/20">Step {playbackIndex} of {events.length}</span>
                      <span>Real-time Tip</span>
                   </div>
                </div>
             </div>
          )}
        </div>
      </header>

      {loading ? (
        <div className="flex-1 flex items-center justify-center text-slate-500 flex-col gap-4">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
          <span className="font-black text-xs uppercase tracking-[0.3em]">Reconstructing Log Streams...</span>
        </div>
      ) : (
        <main className={`flex-1 w-full max-w-[1800px] mx-auto grid min-h-0 ${sidebarOpen ? "grid-cols-[240px_1fr_380px]" : "grid-cols-[240px_1fr_40px]"}`}>
          {/* LEFT: Step Index */}
          <aside className="border-r border-slate-800 bg-slate-950/40 overflow-y-auto max-h-[calc(100vh-200px)] sticky top-[200px]">
             <div className="px-3 py-2 border-b border-slate-800 flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-500">
                <ListMusic size={12} /> Step Index
             </div>
             <div className="py-1">
                {steps.map((s) => (
                   <StepRow key={s.idx} step={s} active={activeStep === s.idx} beyond={s.idx >= playbackIndex} onClick={() => jumpTo(s.idx)} />
                ))}
             </div>
          </aside>

          {/* CENTER: Conversation */}
          <section className="overflow-y-auto max-h-[calc(100vh-200px)] p-8">
             <div className={splitView ? "grid grid-cols-2 gap-8" : "space-y-8"}>
                <div className="space-y-8">
                   {splitView && <h3 className="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em] ml-2 mb-2 flex items-center gap-2"><User size={14}/> User & Agent Dialogue</h3>}
                   {visibleEvents.map((event, idx) => {
                      const isReasoning = event.type === "agent_reasoning" || event.thoughts || (event.message?.role === "assistant" && (hasContentType(event, "thinking") || hasContentType(event, "thought"))) || event.payload?.type === "reasoning" || event.type === "assistant_thinking";
                      const isTool = event.toolCalls || (event.message?.role === "assistant" && hasContentType(event, "tool_use")) || (event.type === "user" && hasContentType(event, "tool_result")) || event.payload?.type === "function_call";
                      
                      // Check for thinking inside Copilot assistant payload array
                      const hasThinkingPart = Array.isArray(event.payload) && event.payload.some((p: any) => p.kind === "thinking" || p.type === "thinking");
                      
                      // For Cursor/Claude/Codex/Copilot: If it's an message with BOTH text and tools/reasoning, 
                      // we want the text to show up in the dialogue column.
                      const hasText = (Array.isArray(event.message?.content) && event.message.content.some((c: any) => (c.type === "text" || c.type === "input_text") && (c.text || c.input_text))) || 
                                      (event.type === "response_item" && event.payload?.type === "message" && Array.isArray(event.payload.content) && event.payload.content.some((c: any) => c.text || c.input_text)) ||
                                      (event.type === "assistant" && Array.isArray(event.payload) && event.payload.some((p: any) => p.value && p.kind !== "thinking")) ||
                                      (event.type === "user" && (event.payload?.text || typeof event.payload === 'string')) ||
                                      (typeof event.content === 'string' && event.content.trim().length > 0);
                      
                      if (splitView && ((isReasoning || hasThinkingPart) && !hasText)) return null;
                      const kind = eventKind(event);
                      return (
                         <div key={idx} ref={(el) => { stepRefs.current[idx] = el; }} className={activeStep === idx ? `${stepRingClass[kind]} rounded-3xl` : ""}>
                            <EventCard event={event} mode={splitView ? "dialogue" : "all"} agent={agent} />
                         </div>
                      );
                   })}
                </div>
                {splitView && (
                   <div className="space-y-8 border-l border-slate-800/50 pl-8">
                      <h3 className="text-[10px] font-black text-emerald-500 uppercase tracking-[0.2em] mb-2 flex items-center gap-2"><Brain size={14}/> Internal Reasoning & Tools</h3>
                      {visibleEvents.map((event, idx) => {
                         const isReasoning = event.type === "agent_reasoning" || event.thoughts || (event.message?.role === "assistant" && (hasContentType(event, "thinking") || hasContentType(event, "thought"))) || event.payload?.type === "reasoning" || event.type === "assistant_thinking";
                         const isTool = event.toolCalls || (event.message?.role === "assistant" && hasContentType(event, "tool_use")) || (event.type === "user" && hasContentType(event, "tool_result")) || event.payload?.type === "function_call";
                         
                         const hasThinkingPart = Array.isArray(event.payload) && event.payload.some((p: any) => p.kind === "thinking" || p.type === "thinking");

                         if (!isReasoning && !isTool && !hasThinkingPart) return null;
                         const kind = eventKind(event);
                         return (
                            <div key={idx} ref={(el) => { stepRefs.current[idx] = el; }} className={activeStep === idx ? `${stepRingClass[kind]} rounded-3xl` : ""}>
                               <EventCard event={event} mode="brain" agent={agent} />
                            </div>
                         );
                      })}
                   </div>
                )}
             </div>
          </section>

          {/* RIGHT: Sidebar */}
          <aside className="border-l border-slate-800 bg-slate-950/40 overflow-y-auto max-h-[calc(100vh-200px)] sticky top-[200px]">
             {!sidebarOpen ? (
                <button
                   onClick={() => setSidebarOpen(true)}
                   title="Open inspector"
                   className="w-full h-full flex flex-col items-center justify-start gap-3 pt-4 text-slate-500 hover:text-blue-400 hover:bg-slate-900/60 transition-colors"
                >
                   <ChevronLeft size={16} />
                   <span className="text-[9px] font-black uppercase tracking-[0.3em] [writing-mode:vertical-rl] rotate-180">Inspector</span>
                </button>
             ) : (
             <>
             <div className="flex border-b border-slate-800 text-[10px] font-black uppercase tracking-[0.2em]">
                <TabBtn active={sidebarTab === "context"} onClick={() => setSidebarTab("context")} icon={<Settings2 size={12} />}>Context</TabBtn>
                <TabBtn active={sidebarTab === "tools"} onClick={() => setSidebarTab("tools")} icon={<Wrench size={12} />}>Tools</TabBtn>
                {sessionInfo?.artifacts && sessionInfo.artifacts.length > 0 && <TabBtn active={sidebarTab === "artifacts"} onClick={() => setSidebarTab("artifacts")} icon={<LayoutPanelLeft size={12} />}>Artifacts</TabBtn>}
                <TabBtn active={sidebarTab === "raw"} onClick={() => setSidebarTab("raw")} icon={<FileCode size={12} />}>Raw</TabBtn>
                <button
                   onClick={() => setSidebarOpen(false)}
                   title="Close inspector"
                   className="px-3 border-l border-slate-800 text-slate-500 hover:text-white hover:bg-slate-900 transition-colors"
                >
                   <ChevronRight size={14} />
                </button>
             </div>
             <div className="p-4 text-[11px]">
                {sidebarTab === "context" && <ContextPanel ctx={context} />}
                {sidebarTab === "tools" && <ToolsPanel summary={toolSummary} onJump={(name) => {
                   const idx = events.findIndex((e) => {
                      const mc = Array.isArray(e.message?.content) ? e.message.content : [];
                      const tu = mc.find?.((c: any) => c.type === "tool_use" && c.name === name);
                      return !!tu || !!e.toolCalls?.some?.((t: any) => t.name === name);
                   });
                   if (idx >= 0) jumpTo(idx);
                }} />}
                {sidebarTab === "artifacts" && <ArtifactsPanel artifacts={sessionInfo?.artifacts || []} />}
                {sidebarTab === "raw" && (
                   <pre className="text-[9px] font-mono text-slate-400 whitespace-pre-wrap break-all max-h-[calc(100vh-260px)] overflow-y-auto">
                      {JSON.stringify(activeStep !== null ? events[activeStep] : events[0], null, 2)}
                   </pre>
                )}
             </div>
             </>
             )}
          </aside>
        </main>
      )}

      {/* RESTORED: Waterfall Footer */}
      {!loading && waterfallData.length > 0 && (
         <footer className="bg-slate-900 border-t border-slate-800 sticky bottom-0 z-40 backdrop-blur-xl bg-opacity-80">
            <div className={`max-w-[1600px] mx-auto ${timelineOpen ? "p-6" : "px-6 py-2"}`}>
               <div className={`flex items-center justify-between ${timelineOpen ? "mb-6" : ""}`}>
                  <button
                     onClick={() => setTimelineOpen((v) => !v)}
                     className="flex items-center gap-2 group"
                     title={timelineOpen ? "Collapse timeline" : "Expand timeline"}
                  >
                     <div className="p-1.5 bg-blue-500/10 rounded-lg border border-blue-500/20 group-hover:bg-blue-500/20 transition-colors">
                        <ListMusic size={16} className="text-blue-400" />
                     </div>
                     <span className="text-[10px] font-black uppercase tracking-[0.2em] text-white">Execution Timeline</span>
                     <span className="text-slate-500 group-hover:text-slate-300 transition-colors">
                        {timelineOpen ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
                     </span>
                  </button>
                  <div className="flex items-center gap-3">
                     <span className="text-[9px] font-mono text-slate-500">{waterfallData.length} Tools Invoked</span>
                     <button
                        onClick={() => setTimelineOpen((v) => !v)}
                        className="text-[9px] font-black uppercase tracking-[0.2em] text-slate-400 hover:text-white px-2 py-1 rounded-md border border-slate-800 hover:border-slate-700 bg-slate-950/60 transition-colors"
                     >
                        {timelineOpen ? "Close" : "Open"}
                     </button>
                  </div>
               </div>
               {timelineOpen && (
               <div className="flex flex-col gap-2.5 max-h-48 overflow-y-auto pr-6 scrollbar-thin">
                  {waterfallData.map((tool, i) => {
                     const totalRange = waterfallData[waterfallData.length-1].end - waterfallData[0].start;
                     const left = ((tool.start - waterfallData[0].start) / Math.max(1, totalRange)) * 95;
                     const width = ((tool.end - tool.start) / Math.max(1, totalRange)) * 95;
                     
                     return (
                        <div key={i} className="flex items-center gap-4 group">
                           <div className="w-28 flex flex-col">
                              <span className="text-[9px] font-bold text-slate-400 truncate group-hover:text-white transition-colors">{tool.name}</span>
                              <span className="text-[7px] font-mono text-slate-600 uppercase">{(tool.end - tool.start).toFixed(0)}ms</span>
                           </div>
                           <div className="flex-1 bg-slate-950 h-3 rounded-full relative border border-slate-800/50 shadow-inner">
                              <div 
                                 className="absolute h-full bg-gradient-to-r from-blue-600/30 to-blue-500/60 border-r border-blue-400 rounded-full group-hover:from-blue-500 group-hover:to-blue-400 transition-all"
                                 style={{ left: `${left}%`, width: `${Math.max(1, width)}%` }}
                              ></div>
                           </div>
                        </div>
                     );
                  })}
               </div>
               )}
            </div>
         </footer>
      )}
    </div>
  );
}

function StatPill({ icon, label, value, tone }: { icon: React.ReactNode; label: string; value: number | string; tone?: "blue" | "amber" | "red" | "emerald" | "cyan" }) {
  const toneCls = 
    tone === "blue" ? "text-blue-400" : 
    tone === "amber" ? "text-amber-400" : 
    tone === "red" ? "text-red-400" : 
    tone === "emerald" ? "text-emerald-400" :
    tone === "cyan" ? "text-cyan-400" :
    "text-slate-300";
  return (
    <div className="flex items-center gap-1.5 bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1 shadow-inner">
      <span className="text-slate-600">{icon}</span>
      <span className="text-[8px] font-black text-slate-500 uppercase tracking-widest">{label}</span>
      <span className={`text-[11px] font-black tabular-nums ${toneCls}`}>{value}</span>
    </div>
  );
}

function TabBtn({ active, onClick, icon, children }: { active: boolean; onClick: () => void; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 border-b-2 transition-colors ${active ? "border-blue-500 text-blue-400 bg-blue-500/5" : "border-transparent text-slate-500 hover:text-slate-300"}`}
    >
      {icon}
      {children}
    </button>
  );
}

function StepRow({ step, active, beyond, onClick }: { step: Step; active: boolean; beyond: boolean; onClick: () => void }) {
  const icon: Record<StepKind, React.ReactNode> = {
    user: <User size={11} />,
    assistant: <MessageSquare size={11} />,
    reasoning: <Brain size={11} />,
    tool: <Wrench size={11} />,
    tool_result: <Terminal size={11} />,
    meta: <Info size={11} />,
    other: <Zap size={11} />,
  };
  const color: Record<StepKind, string> = {
    user: "text-blue-400",
    assistant: "text-emerald-400",
    reasoning: "text-amber-400",
    tool: "text-sky-400",
    tool_result: "text-slate-500",
    meta: "text-slate-600",
    other: "text-slate-600",
  };
  return (
    <button
      onClick={onClick}
      className={`w-full text-left flex items-center gap-2 px-3 py-1.5 text-[10px] font-mono border-l-2 transition-colors ${active ? "bg-blue-500/10 border-blue-500" : "border-transparent hover:bg-slate-900/60"} ${beyond ? "opacity-30" : ""}`}
    >
      <span className="text-slate-600 w-7 tabular-nums">{step.idx.toString().padStart(3, "0")}</span>
      <span className={color[step.kind]}>{icon[step.kind]}</span>
      <span className="text-slate-300 truncate flex-1">{step.label}</span>
    </button>
  );
}

function ContextPanel({ ctx }: { ctx: any }) {
  const Row = ({ k, v, mono = true }: { k: string; v?: any; mono?: boolean }) =>
    v ? (
      <div className="space-y-0.5">
        <div className="text-[9px] font-black uppercase tracking-widest text-slate-500">{k}</div>
        <div className={`text-slate-300 break-all ${mono ? "font-mono text-[10px]" : ""}`}>{typeof v === "string" ? v : JSON.stringify(v)}</div>
      </div>
    ) : null;
  const hasAny = ctx.model || ctx.cwd || ctx.systemPrompt || ctx.instructions || ctx.sandbox;
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">
        <Cpu size={12} /> Session Context
      </div>
      {ctx.sessionId && (
        <div className="space-y-1">
          <div className="text-[9px] font-black uppercase tracking-widest text-slate-500">Session ID</div>
          <div className="flex items-center gap-1.5 bg-slate-950 border border-slate-800 rounded px-2 py-1.5">
            <span className="text-[10px] font-mono text-slate-300 break-all flex-1" title={ctx.sessionId}>{ctx.sessionId}</span>
            <button
              onClick={() => { navigator.clipboard?.writeText(ctx.sessionId); }}
              className="text-[9px] font-black uppercase text-slate-500 hover:text-blue-400 transition-colors px-1"
              title="Copy">
              copy
            </button>
          </div>
          {ctx.agent && <div className="text-[9px] font-mono text-slate-600 uppercase">agent: {ctx.agent}</div>}
        </div>
      )}
      <Row k="Model" v={ctx.model} />
      <Row k="Provider" v={ctx.provider} />
      {ctx.modelsUsed && ctx.modelsUsed.length > 0 && (
        <div className="space-y-1">
          <div className="text-[9px] font-black uppercase tracking-widest text-slate-500">Models Used ({ctx.modelsUsed.length})</div>
          <div className="flex flex-wrap gap-1.5">
            {ctx.modelsUsed.map((m: string) => (
              <span key={m} className="flex items-center gap-1 text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                <Cpu size={10} /> {m}
              </span>
            ))}
          </div>
        </div>
      )}
      <Row k="CWD" v={ctx.cwd} />

      {ctx.projectConfig && (ctx.projectConfig.counts?.skills > 0 || ctx.projectConfig.counts?.mcps > 0) && (
        <div className="space-y-3 pt-2 border-t border-slate-800">
          <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">
            <Settings2 size={12} /> Project Configuration
          </div>
          {ctx.projectConfig.counts.skills > 0 && (
            <details open>
              <summary className="text-[9px] font-black uppercase tracking-widest text-slate-500 cursor-pointer hover:text-slate-300">
                Skills ({ctx.projectConfig.counts.skills}) ▸
              </summary>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {ctx.projectConfig.skills.map((s: any, i: number) => (
                  <span
                    key={i}
                    title={`${s.scope} · ${s.agent}${s.description ? "\n" + s.description : ""}`}
                    className={`text-[10px] font-mono px-2 py-0.5 rounded border ${s.scope === "project" ? "bg-cyan-500/10 text-cyan-400 border-cyan-500/20" : "bg-slate-800/60 text-slate-400 border-slate-700"}`}
                  >
                    {s.name}
                  </span>
                ))}
              </div>
            </details>
          )}
          {ctx.projectConfig.counts.mcps > 0 && (
            <details open>
              <summary className="text-[9px] font-black uppercase tracking-widest text-slate-500 cursor-pointer hover:text-slate-300">
                MCP Servers ({ctx.projectConfig.counts.mcps}) ▸
              </summary>
              <div className="mt-2 space-y-1">
                {ctx.projectConfig.mcps.map((m: any, i: number) => (
                  <div key={i} className="flex items-center justify-between gap-2 text-[10px] font-mono bg-slate-900/60 border border-slate-800 rounded px-2 py-1">
                    <span className="text-slate-300 truncate" title={m.command || m.url || ""}>{m.name}</span>
                    <span className={`px-1.5 py-0.5 rounded text-[8px] font-black uppercase ${m.scope === "project" ? "bg-blue-500/10 text-blue-400 border border-blue-500/20" : "bg-slate-800 text-slate-400 border border-slate-700"}`}>{m.agent}</span>
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>
      )}

      <Row k="Sandbox" v={ctx.sandbox} />
      <Row k="Approval Policy" v={ctx.approvalPolicy} />
      <Row k="Reasoning Effort" v={ctx.reasoningEffort} />
      {ctx.instructions && (
        <details>
          <summary className="text-[9px] font-black uppercase tracking-widest text-slate-500 cursor-pointer hover:text-slate-300">Instructions ▸</summary>
          <pre className="mt-2 text-[10px] font-mono text-slate-400 whitespace-pre-wrap bg-slate-950 border border-slate-800 rounded-lg p-3 max-h-64 overflow-y-auto">{ctx.instructions}</pre>
        </details>
      )}
      {ctx.systemPrompt && (
        <details>
          <summary className="text-[9px] font-black uppercase tracking-widest text-slate-500 cursor-pointer hover:text-slate-300">System Prompt ▸</summary>
          <pre className="mt-2 text-[10px] font-mono text-slate-400 whitespace-pre-wrap bg-slate-950 border border-slate-800 rounded-lg p-3 max-h-64 overflow-y-auto">
            {ctx.systemPrompt.slice(0, 4000)}
            {ctx.systemPrompt.length > 4000 ? "\n…(truncated)" : ""}
          </pre>
        </details>
      )}
      {ctx.env && (
        <details>
          <summary className="text-[9px] font-black uppercase tracking-widest text-slate-500 cursor-pointer hover:text-slate-300">Environment ▸</summary>
          <pre className="mt-2 text-[10px] font-mono text-slate-400 whitespace-pre-wrap bg-slate-950 border border-slate-800 rounded-lg p-3 max-h-48 overflow-y-auto">{JSON.stringify(ctx.env, null, 2)}</pre>
        </details>
      )}
      {!hasAny && <div className="text-slate-600 text-[10px] italic">No context metadata found for this session.</div>}
    </div>
  );
}

function ToolsPanel({ summary, onJump }: { summary: { name: string; count: number; avg: number }[]; onJump: (name: string) => void }) {
  if (!summary.length) return <div className="text-slate-600 text-[10px] italic">No tool calls in this session.</div>;
  const maxCount = summary[0]?.count || 1;
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">
        <Wrench size={12} /> Tool Summary
      </div>
      {summary.map((t) => (
        <button key={t.name} onClick={() => onJump(t.name)} className="w-full text-left bg-slate-900/60 border border-slate-800 hover:border-slate-700 rounded-lg px-3 py-2 transition-colors">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[11px] font-mono text-slate-200 truncate">{t.name}</span>
            <span className="text-[9px] font-black text-blue-400 tabular-nums">×{t.count}</span>
          </div>
          <div className="h-1 bg-slate-800 rounded overflow-hidden">
            <div className="h-full bg-blue-500/60" style={{ width: `${(t.count / maxCount) * 100}%` }} />
          </div>
          <div className="text-[9px] font-mono text-slate-600 mt-1">avg {t.avg >= 1000 ? `${(t.avg / 1000).toFixed(2)}s` : `${t.avg.toFixed(0)}ms`}</div>
        </button>
      ))}
    </div>
  );
}

function ArtifactsPanel({ artifacts }: { artifacts: Artifact[] }) {
  if (!artifacts.length) return <div className="text-slate-600 text-[10px] italic">No artifacts for this session.</div>;
  
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400">
        <LayoutPanelLeft size={12} /> Session Artifacts
      </div>
      <div className="space-y-4">
        {artifacts.map((a, i) => (
          <div key={i} className="bg-slate-900/60 border border-slate-800 rounded-xl overflow-hidden shadow-lg group text-[11px]">
            <div className="px-3 py-2 border-b border-slate-800 bg-slate-950/40 flex items-center justify-between">
               <div className="flex items-center gap-2 min-w-0">
                  {a.type === 'video' ? <Play size={10} className="text-blue-400" /> : 
                   a.type === 'image' ? <LayoutPanelLeft size={10} className="text-emerald-400" /> :
                   a.type === 'terminal' ? <Terminal size={10} className="text-purple-400" /> :
                   <FileText size={10} className="text-slate-400" />}
                  <span className="text-[10px] font-mono text-slate-300 truncate" title={a.name}>{a.name}</span>
               </div>
               <a 
                 href={`http://localhost:8000/artifacts?path=${encodeURIComponent(a.path)}`} 
                 download={a.name}
                 className="text-[8px] font-black uppercase text-slate-500 hover:text-white transition-colors"
               >
                 DL
               </a>
            </div>
            
            <div className="p-3">
               {a.type === 'video' && (
                 <video controls className="w-full rounded-lg shadow-inner bg-black aspect-video">
                   <source src={`http://localhost:8000/artifacts?path=${encodeURIComponent(a.path)}`} type="video/mp4" />
                   Your browser does not support the video tag.
                 </video>
               )}
               {a.type === 'image' && (
                 <img 
                    src={`http://localhost:8000/artifacts?path=${encodeURIComponent(a.path)}`} 
                    alt={a.name} 
                    className="w-full rounded-lg shadow-inner bg-slate-950" 
                 />
               )}
               {(a.type === 'terminal' || a.type === 'document') && (
                 <div className="max-h-48 overflow-y-auto scrollbar-thin">
                    <ArtifactViewer path={a.path} />
                 </div>
               )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ArtifactViewer({ path }: { path: string }) {
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`http://localhost:8000/artifacts?path=${encodeURIComponent(path)}`)
      .then(res => res.text())
      .then(t => {
        setContent(t);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [path]);

  if (loading) return <div className="animate-pulse h-4 bg-slate-800 rounded w-1/2"></div>;
  return (
    <pre className="text-[9px] font-mono text-slate-400 whitespace-pre-wrap break-all leading-relaxed">
      {content || "Failed to load content."}
    </pre>
  );
}

function EventCard({ event, mode = "all", agent }: { event: any, mode?: "dialogue" | "brain" | "all", agent?: string | null }) {
  const { type, timestamp, message, attachment, toolUseResult, payload, content, thoughts, toolCalls } = event;

  // Render a tiny timestamp badge if available
  const renderTimestamp = () => {
    const ts = timestamp || event.normalized_timestamp;
    if (!ts) return null;
    const date = new Date(ts);
    if (Number.isNaN(date.getTime())) return null;
    const timeStr = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
    return (
      <div className="flex items-center gap-1 text-[9px] font-mono text-slate-500 mb-2 opacity-60 group-hover:opacity-100 transition-opacity">
        <Clock size={10} />
        {timeStr}
      </div>
    );
  };

  // Helper to extract text from content array (Used by Claude and Cursor)
  const extractText = (contentArr: any[]) => {
    if (!Array.isArray(contentArr)) return "";
    return contentArr
      .filter((c: any) => c.type === "text")
      .map((c: any) => c.text)
      .filter(Boolean)
      .join("\n");
  };

  const parts: React.ReactNode[] = [];

  // 1. OLLAMA
  if (agent === "ollama") {
     parts.push(
        <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-2xl relative overflow-hidden group hover:border-slate-600 transition-all text-left">
          <div className="absolute top-0 left-0 w-1 h-full bg-blue-600"></div>
          <div className="flex justify-between items-start mb-4">
            <div className="flex items-center gap-2 text-blue-400 font-black text-[10px] uppercase tracking-[0.2em]">
                <User size={16} strokeWidth={3} /> Ollama History
            </div>
            {renderTimestamp()}
          </div>
          <div className="text-slate-200 whitespace-pre-wrap text-sm leading-relaxed font-medium">{content}</div>
        </div>
     );
  }

  // 2. COPILOT (Separate blocks for user/assistant parts)
  if (agent === "copilot") {
    if (type === "user" && payload?.text) {
       parts.push(
        <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-2xl relative overflow-hidden group hover:border-slate-600 transition-all text-left">
          <div className="absolute top-0 left-0 w-1 h-full bg-blue-600"></div>
          <div className="flex justify-between items-start mb-4">
            <div className="flex items-center gap-2 text-blue-400 font-black text-[10px] uppercase tracking-[0.2em]">
                <User size={16} strokeWidth={3} /> User Prompt
            </div>
            {renderTimestamp()}
          </div>
          <div className="text-slate-200 whitespace-pre-wrap text-sm leading-relaxed font-medium">{payload.text}</div>
        </div>
       );
    }
    if (type === "assistant_thinking" && payload?.text && mode !== "dialogue") {
       parts.push(
        <div className="bg-indigo-500/5 border border-indigo-500/20 rounded-2xl p-6 shadow-sm ml-4 border-l-4 border-l-indigo-500/50 group">
          <div className="flex justify-between items-start mb-3">
            <div className="flex items-center gap-2 text-indigo-400 font-bold text-xs uppercase tracking-widest">
              <Brain size={16} /> Copilot Reasoning
            </div>
            {renderTimestamp()}
          </div>
          <div className="text-slate-400 whitespace-pre-wrap italic text-xs leading-relaxed font-mono opacity-80">{payload.text}</div>
        </div>
       );
    }
    if (type === "assistant" && Array.isArray(payload)) {
       const thinkingParts = payload.filter((p: any) => p.kind === "thinking" || p.type === "thinking");
       const textParts = payload.filter((p: any) => p.kind !== "thinking" && p.type !== "thinking" && (p.value || typeof p === 'string'));
       const combinedText = textParts.map((p: any) => typeof p === 'string' ? p : (p.value || "")).join("");

       if (thinkingParts.length > 0 && mode !== "dialogue") {
         thinkingParts.forEach((p: any, i: number) => {
           parts.push(
             <div key={`copilot-think-${i}`} className="bg-indigo-500/5 border border-indigo-500/20 rounded-2xl p-6 shadow-sm ml-4 border-l-4 border-l-indigo-500/50 group">
               <div className="flex justify-between items-start mb-3">
                 <div className="flex items-center gap-2 text-indigo-400 font-bold text-xs uppercase tracking-widest">
                   <Brain size={16} /> Reasoning
                 </div>
                 {renderTimestamp()}
               </div>
               <div className="text-slate-400 whitespace-pre-wrap italic text-xs leading-relaxed font-mono opacity-80">{p.value}</div>
             </div>
           );
         });
       }
       if (combinedText && mode !== "brain") {
         parts.push(
           <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-2xl relative overflow-hidden group hover:border-slate-600 transition-all">
             <div className="absolute top-0 left-0 w-1 h-full bg-indigo-600"></div>
             <div className="flex justify-between items-start mb-4">
               <div className="flex items-center gap-2 text-indigo-400 font-black text-[10px] uppercase tracking-[0.2em]">
                   <GitBranch size={16} strokeWidth={3} /> Response
               </div>
               {renderTimestamp()}
             </div>
             <ResponseBody text={combinedText} />
           </div>
         );
       }
    }
  }

  // 3. VIBE / OPENCODE Common User Prompt
  if (type === "user" && payload?.content && !message) {
     parts.push(
        <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-2xl relative overflow-hidden group hover:border-slate-600 transition-all text-left">
          <div className="absolute top-0 left-0 w-1 h-full bg-blue-600"></div>
          <div className="flex justify-between items-start mb-4">
            <div className="flex items-center gap-2 text-blue-400 font-black text-[10px] uppercase tracking-[0.2em]">
                <User size={16} strokeWidth={3} /> User Prompt
            </div>
            {renderTimestamp()}
          </div>
          <div className="text-slate-200 whitespace-pre-wrap text-sm leading-relaxed font-medium">{payload.content}</div>
        </div>
     );
  }

  // 4. VIBE / OPENCODE Assistant Response
  if (type === "assistant" && payload?.content && !message) {
    const isOpencode = agent === "opencode";
    const accent = isOpencode ? "bg-amber-600" : "bg-pink-600";
    const textColor = isOpencode ? "text-amber-400" : "text-pink-400";
    parts.push(
      <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-2xl relative overflow-hidden group hover:border-slate-600 transition-all text-left">
        <div className={`absolute top-0 left-0 w-1 h-full ${accent}`}></div>
        <div className="flex justify-between items-start mb-4">
          <div className={`flex items-center gap-2 ${textColor} font-black text-[10px] uppercase tracking-[0.2em]`}>
              <Zap size={16} strokeWidth={3} /> Thinking
          </div>
          {renderTimestamp()}
        </div>
        <ResponseBody text={payload.content} />
      </div>
    );
  }

  // 5. OPENCODE tool_call
  if (agent === "opencode" && type === "tool_call" && payload && mode !== "dialogue") {
    const state = payload.state || {};
    const status = state.status;
    const input = state.input;
    const output = state.output;
    parts.push(
      <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4 shadow-lg group">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2 text-amber-400 font-black text-[10px] uppercase tracking-[0.2em]">
            <Wrench size={14} strokeWidth={3} /> Tool · {payload.tool || "unknown"}
          </div>
          <div className="flex items-center gap-3">
             {renderTimestamp()}
             {status && <span className="text-[9px] font-bold uppercase tracking-widest text-slate-500">{status}</span>}
          </div>
        </div>
        {input && (
          <details className="mt-1">
            <summary className="text-[10px] font-mono text-slate-500 cursor-pointer hover:text-slate-300">input ▸</summary>
            <pre className="mt-2 text-[10px] font-mono text-slate-400 whitespace-pre-wrap bg-slate-950 border border-slate-800 rounded-lg p-3 max-h-64 overflow-y-auto">{typeof input === "string" ? input : JSON.stringify(input, null, 2)}</pre>
          </details>
        )}
        {output && (
          <details className="mt-1">
            <summary className="text-[10px] font-mono text-slate-500 cursor-pointer hover:text-slate-300">output ▸</summary>
            <pre className="mt-2 text-[10px] font-mono text-slate-400 whitespace-pre-wrap bg-slate-950 border border-slate-800 rounded-lg p-3 max-h-64 overflow-y-auto">{typeof output === "string" ? output.slice(0, 4000) : JSON.stringify(output, null, 2).slice(0, 4000)}</pre>
          </details>
        )}
      </div>
    );
  }

  // 6. GEMINI / ANTIGRAVITY (Multi-part support: thoughts + content + toolCalls)
  if (thoughts && Array.isArray(thoughts) && mode !== "dialogue") {
    parts.push(
      <div className="space-y-4">
        {thoughts.map((thought: any, i: number) => (
          <div key={i} className="bg-cyan-500/5 border border-cyan-500/20 rounded-2xl p-6 shadow-sm ml-4 border-l-4 border-l-cyan-500/50 group">
            <div className="flex justify-between items-start mb-3">
              <div className="flex items-center gap-2 text-cyan-400 font-bold text-xs uppercase tracking-widest">
                <Brain size={16} /> {thought.subject || "Reasoning"}
              </div>
              {renderTimestamp()}
            </div>
            <div className="text-slate-400 whitespace-pre-wrap italic text-[11px] leading-relaxed font-mono opacity-80">{thought.description}</div>
          </div>
        ))}
      </div>
    );
  }

  if (toolCalls && Array.isArray(toolCalls) && mode !== "dialogue") {
    parts.push(
      <div className="space-y-4">
        {toolCalls.map((call: any, i: number) => (
          <div key={i} className="space-y-4">
            <div className="bg-blue-500/5 border border-blue-500/20 rounded-2xl p-6 shadow-sm ml-4 border-l-4 border-l-blue-500/50 group">
              <div className="flex justify-between items-start mb-4">
                <div className="flex items-center gap-2 text-blue-400 font-bold text-xs uppercase tracking-widest">
                  <Code size={16} /> Tool Call: {call.name}
                </div>
                {renderTimestamp()}
              </div>
              <pre className="bg-slate-950 text-blue-300 p-5 rounded-xl text-[11px] overflow-x-auto font-mono border border-slate-800 shadow-inner">
                {JSON.stringify(call.args, null, 2)}
              </pre>
            </div>
            {call.result && (
              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl ml-8 group hover:border-emerald-500/30 transition-all">
                <div className="flex justify-between items-start mb-4">
                  <div className="flex items-center gap-2 text-slate-500 font-bold text-xs uppercase tracking-widest group-hover:text-emerald-500">
                    <Terminal size={16} /> Tool Output
                  </div>
                  {renderTimestamp()}
                </div>
                <pre className="bg-slate-950 text-emerald-400 p-5 rounded-xl text-[11px] overflow-x-auto font-mono border border-slate-800 shadow-inner">
                  {typeof call.result === 'string' ? call.result : JSON.stringify(call.result, null, 2)}
                </pre>
              </div>
            )}
          </div>
        ))}
      </div>
    );
  }

  if (type === "user" && content && (agent === "gemini" || agent === "antigravity")) {
    const textContent = Array.isArray(content) ? content.map((c: any) => c.text).filter(Boolean).join("\n") : (typeof content === 'string' ? content : "");
    if (textContent) {
      parts.push(
        <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-2xl relative overflow-hidden group hover:border-slate-600 transition-all text-left">
          <div className="absolute top-0 left-0 w-1 h-full bg-blue-600"></div>
          <div className="flex justify-between items-start mb-4">
            <div className="flex items-center gap-2 text-blue-400 font-black text-[10px] uppercase tracking-[0.2em]">
                <User size={16} strokeWidth={3} /> User Prompt
            </div>
            {renderTimestamp()}
          </div>
          <div className="text-slate-200 whitespace-pre-wrap text-sm leading-relaxed font-medium">{textContent}</div>
        </div>
      );
    }
  }

  const role = event.role || event.message?.role;
  if ((type === "assistant" || role === "assistant" || role === "model" || role === "gemini" || type === "model" || type === "gemini") && typeof content === 'string' && content.trim() && mode !== "brain") {
    parts.push(
      <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-2xl relative overflow-hidden group hover:border-slate-600 transition-all text-left">
        <div className="absolute top-0 left-0 w-1 h-full bg-cyan-600"></div>
        <div className="flex justify-between items-start mb-4">
          <div className="flex items-center gap-2 text-cyan-400 font-black text-[10px] uppercase tracking-[0.2em]">
              <Sparkles size={16} strokeWidth={3} /> Response
          </div>
          {renderTimestamp()}
        </div>
        <ResponseBody text={content} />
      </div>
    );
  }

  // 7. CATCH-ALL for separate reasoning events (Claude/Cursor/Copilot/Qwen)
  if ((type === "agent_reasoning" || type === "assistant_thinking" || type === "reasoning" || payload?.type === "reasoning") && mode !== "dialogue") {
    const rawReasoning = payload?.text ?? payload?.content ?? payload?.thinking ?? payload?.summary ?? payload?.value ?? payload?.message ?? event.thoughts ?? (typeof payload === 'string' ? payload : payload);
    let text = "";
    if (typeof rawReasoning === 'string') text = rawReasoning;
    else if (Array.isArray(rawReasoning)) text = rawReasoning.map((p: any) => (typeof p === 'string' ? p : (p?.text ?? p?.thinking ?? p?.content ?? p?.value ?? ""))).filter(Boolean).join("\n\n");
    else if (rawReasoning && typeof rawReasoning === 'object') text = rawReasoning.text ?? rawReasoning.thinking ?? rawReasoning.content ?? rawReasoning.value ?? JSON.stringify(rawReasoning, null, 2);
    if (text) {
      const isCopilot = agent === "copilot" || type === "assistant_thinking";
      const accent = isCopilot ? "border-l-indigo-500/50" : "border-l-amber-500/50";
      const textColor = isCopilot ? "text-indigo-400" : "text-amber-500";
      const bg = isCopilot ? "bg-indigo-500/5" : "bg-amber-500/5";
      const border = isCopilot ? "border-indigo-500/20" : "border-amber-500/20";

      parts.push(
        <div className={`${bg} border ${border} rounded-2xl p-6 shadow-sm ml-4 border-l-4 ${accent} group`}>
          <div className="flex justify-between items-start mb-3">
            <div className={`flex items-center gap-2 ${textColor} font-bold text-xs uppercase tracking-widest`}>
              <Brain size={16} /> Reasoning
            </div>
            {renderTimestamp()}
          </div>
          <div className="text-slate-400 whitespace-pre-wrap italic text-[11px] leading-relaxed font-mono opacity-80">{text}</div>
        </div>
      );
    }
  }

  // 8. CLAUDE / CURSOR (Multi-part support: thinkingArr + text + tool_result)
  if ((type === "user" || role === "user") && message?.role === "user") {
    const toolResults = Array.isArray(message.content) ? message.content.filter((c: any) => c.type === "tool_result") : [];
    if (toolResults.length > 0 && mode !== "dialogue") {
      parts.push(
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl ml-8 group hover:border-emerald-500/30 transition-all">
          <div className="flex justify-between items-start mb-4">
            <div className="flex items-center gap-2 text-slate-500 font-bold text-xs uppercase tracking-widest group-hover:text-emerald-500">
              <Terminal size={16} /> Tool Output
            </div>
            {renderTimestamp()}
          </div>
          {toolResults.map((c: any, i: number) => (
            <div key={i} className="space-y-3 mb-6 last:mb-0">
               <div className="text-[9px] font-mono text-slate-600 bg-slate-950 px-2 py-0.5 rounded border border-slate-800 w-fit">ID: {c.tool_use_id}</div>
              <pre className="bg-slate-950 text-emerald-400 p-5 rounded-xl text-[11px] overflow-x-auto font-mono border border-slate-800 shadow-inner">
                {typeof c.content === 'string' ? c.content : JSON.stringify(c.content, null, 2)}
              </pre>
            </div>
          ))}
        </div>
      );
    }
    const textContent = Array.isArray(message.content) ? extractText(message.content) : (typeof message.content === 'string' ? message.content : "");
    if (textContent && mode !== "brain") {
      parts.push(
        <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-2xl relative overflow-hidden group hover:border-slate-600 transition-all text-left">
          <div className="absolute top-0 left-0 w-1 h-full bg-blue-600"></div>
          <div className="flex justify-between items-start mb-4">
            <div className="flex items-center gap-2 text-blue-400 font-black text-[10px] uppercase tracking-[0.2em]">
                <User size={16} strokeWidth={3} /> User Prompt
            </div>
            {renderTimestamp()}
          </div>
          <div className="text-slate-200 whitespace-pre-wrap text-sm leading-relaxed font-medium">{textContent}</div>
        </div>
      );
    }
  }

  if ((type === "assistant" || role === "assistant") && (message?.role === "assistant" || role === "assistant")) {
    const contentArr = Array.isArray(message?.content) ? message.content : [];
    const toolCallsArr = contentArr.filter((c: any) => c.type === "tool_use");
    const thinkingArr = contentArr.filter((c: any) => c.type === "thinking");
    const text = extractText(contentArr);

    if (thinkingArr.length > 0 && mode !== "dialogue") {
       thinkingArr.forEach((t: any, i: number) => {
         const body = t.thinking || t.text || t.content || "";
         const isEncrypted = !body && (t.signature || t.type === "redacted_thinking");
         parts.push(
            <div key={`think-${i}`} className="bg-amber-500/5 border border-amber-500/20 rounded-2xl p-6 shadow-sm ml-4 border-l-4 border-l-amber-500/50 group">
              <div className="flex justify-between items-start mb-3">
                <div className="flex items-center gap-2 text-amber-500 font-bold text-xs uppercase tracking-widest">
                  <Brain size={16} /> Reasoning {isEncrypted && <span className="text-[9px] font-mono normal-case tracking-normal text-amber-500/70 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/30">encrypted</span>}
                </div>
                {renderTimestamp()}
              </div>
              {isEncrypted ? (
                <div className="text-slate-500 italic text-[11px] leading-relaxed">
                  Extended thinking is sealed by the API — the local log stores only the cryptographic signature, not the reasoning text.
                  <div className="mt-2 text-[9px] font-mono text-slate-600 break-all opacity-60">sig: {String(t.signature || "").slice(0, 64)}…</div>
                </div>
              ) : (
                <div className="text-slate-400 whitespace-pre-wrap italic text-[11px] leading-relaxed font-mono opacity-80">{body || JSON.stringify(t)}</div>
              )}
            </div>
         );
       });
    }

    if (text && mode !== "brain") {
      parts.push(
        <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-2xl relative overflow-hidden group hover:border-slate-600 transition-all text-left">
          <div className="absolute top-0 left-0 w-1 h-full bg-emerald-500"></div>
          <div className="flex justify-between items-start mb-4">
            <div className="flex items-center gap-2 text-emerald-400 font-black text-[10px] uppercase tracking-[0.2em]">
                <MessageSquare size={16} strokeWidth={3} /> Response
            </div>
            {renderTimestamp()}
          </div>
          <ResponseBody text={text} />
        </div>
      );
    }

    if (toolCallsArr.length > 0 && mode !== "dialogue") {
      toolCallsArr.forEach((toolUse: any, i: number) => {
        parts.push(
          <div key={`tool-${i}`} className="bg-blue-500/5 border border-blue-500/20 rounded-2xl p-6 shadow-sm ml-4 border-l-4 border-l-blue-500/50 group">
            <div className="flex justify-between items-start mb-4">
              <div className="flex items-center gap-2 text-blue-400 font-bold text-xs uppercase tracking-widest">
                <Code size={16} /> Tool Call: {toolUse.name}
              </div>
              {renderTimestamp()}
            </div>
            <pre className="bg-slate-950 text-blue-300 p-5 rounded-xl text-[11px] overflow-x-auto font-mono border border-slate-800 shadow-inner">
              {JSON.stringify(toolUse.input || toolUse.args || toolUse.payload, null, 2)}
            </pre>
          </div>
        );
      });
    }
  }

  // 9. CODEX (request_item / response_item)
  if (type === "response_item" || type === "request_item") {
    const role = payload?.role || (type === "request_item" ? "user" : "assistant");
    const itemType = payload?.type;
    
    if (itemType === "reasoning" && mode !== "dialogue") {
       parts.push(
          <div className="bg-purple-500/5 border border-purple-500/20 rounded-2xl p-6 shadow-sm ml-4 border-l-4 border-l-purple-500/50 group">
            <div className="flex justify-between items-start mb-3">
              <div className="flex items-center gap-2 text-purple-400 font-bold mb-3 text-xs uppercase tracking-widest">
                <Brain size={16} /> Reasoning
              </div>
              {renderTimestamp()}
            </div>
            <div className="text-slate-400 whitespace-pre-wrap italic text-xs leading-relaxed font-mono opacity-80">{
              Array.isArray(payload.content)
                ? payload.content.map((c: any) => c?.text ?? c?.summary ?? c?.content ?? (typeof c === 'string' ? c : "")).filter(Boolean).join("\n\n")
                : (typeof payload.content === 'string' ? payload.content : (payload.summary ?? payload.text ?? ""))
            }</div>
          </div>
       );
    }

    if ((itemType === "function_call" || itemType === "tool_use") && mode !== "dialogue") {
       parts.push(
          <div className="bg-blue-500/5 border border-blue-500/20 rounded-2xl p-6 shadow-sm ml-4 border-l-4 border-l-blue-500/50 group">
            <div className="flex justify-between items-start mb-4">
              <div className="flex items-center gap-2 text-blue-400 font-bold mb-4 text-xs uppercase tracking-widest">
                <Code size={16} /> Tool Call: {payload.name}
              </div>
              {renderTimestamp()}
            </div>
            <pre className="bg-slate-950 text-blue-300 p-5 rounded-xl text-[11px] overflow-x-auto font-mono border border-slate-800 shadow-inner">
              {JSON.stringify(payload.arguments || payload.input || payload.parameters, null, 2)}
            </pre>
          </div>
       );
    }

    if (itemType === "message") {
       const content = payload.content;
       let text = "";
       if (Array.isArray(content)) {
          text = content.map((c: any) => c.text || c.input_text).filter(Boolean).join("\n");
       } else if (typeof content === 'string') {
          text = content;
       }

       if (text) {
         const isAssistant = role === "assistant";
         if (mode !== "brain") {
           parts.push(
              <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-2xl relative overflow-hidden group hover:border-slate-600 transition-all text-left">
                <div className={`absolute top-0 left-0 w-1 h-full ${isAssistant ? 'bg-emerald-600' : 'bg-blue-600'}`}></div>
                <div className="flex justify-between items-start mb-4">
                  <div className={`flex items-center gap-2 ${isAssistant ? 'text-emerald-400' : 'text-blue-400'} font-black text-[10px] uppercase tracking-[0.2em]`}>
                      {isAssistant ? <MessageSquare size={16} strokeWidth={3} /> : <User size={16} strokeWidth={3} />}
                      {isAssistant ? 'Response' : 'User Prompt'}
                  </div>
                  {renderTimestamp()}
                </div>
                {isAssistant
                  ? <ResponseBody text={text} />
                  : <div className="text-slate-200 whitespace-pre-wrap text-sm leading-relaxed font-medium">{text}</div>}
              </div>
           );
         }
       }
    }
  }

  // 10. SYSTEM METADATA
  if (type === "session_meta") {
    parts.push(
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-2xl opacity-90 border-dashed">
        <div className="flex items-center gap-2 text-slate-400 font-bold mb-4 text-xs uppercase tracking-widest">
          <Info size={16} /> Session Metadata
        </div>
        <div className="grid grid-cols-2 gap-6 text-[11px] font-mono text-slate-500">
           <div className="flex flex-col gap-1">
              <span className="text-[8px] uppercase tracking-widest opacity-50">CWD</span>
              <span className="text-slate-300 truncate">{payload.cwd}</span>
           </div>
           <div className="flex flex-col gap-1">
              <span className="text-[8px] uppercase tracking-widest opacity-50">Model</span>
              <span className="text-slate-300">{payload.model_provider}</span>
           </div>
        </div>
      </div>
    );
  }

  if (type === "event_msg") {
    parts.push(
      <div className="bg-slate-900/30 border border-slate-800/50 rounded-xl p-4 text-[10px] text-slate-500 flex items-center gap-4 group hover:bg-slate-800/20 transition-all">
        <Zap size={14} className="text-purple-500/50 group-hover:text-purple-400" />
        <span className="font-bold text-slate-400 uppercase tracking-[0.2em]">{payload?.type}</span>
      </div>
    );
  }

  if (parts.length === 0 && mode === "all") {
    parts.push(
      <div className="bg-slate-900/20 border border-slate-800/30 rounded-xl p-3 text-[10px] text-slate-600 flex justify-between items-center opacity-40 hover:opacity-100 transition-opacity">
        <span className="font-mono">System Event: {type}</span>
      </div>
    );
  }

  return <div className="space-y-6 w-full">{parts.map((p, i) => <React.Fragment key={i}>{p}</React.Fragment>)}</div>;
}
function ResponseBody({ text, tone = "default" }: { text: string; tone?: "default" | "muted" }) {
  const [mode, setMode] = useState<"md" | "raw">("md");
  if (!text) return null;
  const base = tone === "muted"
    ? "text-slate-400 whitespace-pre-wrap italic text-xs leading-relaxed font-mono opacity-80"
    : "text-slate-200 whitespace-pre-wrap text-sm leading-relaxed font-medium";
  return (
    <div className="relative group/body">
      {mode === "md" ? (
        <div className="prose prose-invert prose-sm max-w-none text-slate-200 text-sm leading-relaxed">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
        </div>
      ) : (
        <div className={base}>{text}</div>
      )}
      <button
        onClick={(e) => { e.stopPropagation(); setMode(mode === "md" ? "raw" : "md"); }}
        className="absolute -bottom-2 -right-2 text-[8px] font-black uppercase tracking-widest px-2 py-1 rounded-lg bg-slate-900/80 backdrop-blur-md border border-slate-800 text-slate-500 hover:text-blue-400 hover:border-blue-500/50 transition-all opacity-0 group-hover/body:opacity-100 shadow-xl z-10"
        title={mode === "md" ? "Show raw text" : "Render markdown"}
      >
        {mode === "md" ? "View Raw" : "View MD"}
      </button>
    </div>
  );
}
