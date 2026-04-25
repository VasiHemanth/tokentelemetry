"use client";

import { useEffect, useState } from "react";
import { Server, Database, HardDrive, Cpu, Activity, Zap, CheckCircle2, XCircle, Box, Download, ArrowRight, ShieldCheck } from "lucide-react";
import Link from "next/link";

interface LocalRuntime {
  ollama: string;
  models: any[];
  hf_usage: string;
}

export default function LocalLabPage() {
  const [data, setData] = useState<LocalRuntime | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("http://127.0.0.1:8000/local-runtime")
      .then(res => res.json())
      .then(d => {
        setData(data); // Wait, I should set d
        setData(d);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  return (
    <div className="p-8 max-w-[1600px] mx-auto space-y-10 pb-20 text-slate-100">
      <header className="flex justify-between items-end border-b border-slate-800 pb-6">
        <div>
          <h1 className="text-4xl font-black text-white tracking-tighter flex items-center gap-3">
            <Server className="text-blue-500" size={36} strokeWidth={3} />
            LOCAL LAB
          </h1>
          <p className="text-slate-500 mt-1 font-medium">Monitoring local LLM runtimes and private model storage.</p>
        </div>
        <div className="flex gap-2">
           <div className={`px-3 py-1.5 bg-slate-900 border border-slate-800 rounded-lg text-[10px] font-bold uppercase tracking-widest flex items-center gap-2 ${data?.ollama === "online" ? "text-emerald-400" : "text-red-400"}`}>
              <div className={`w-2 h-2 rounded-full ${data?.ollama === "online" ? "bg-emerald-500 animate-pulse" : "bg-red-500"}`}></div>
              Ollama {data?.ollama || "OFFLINE"}
           </div>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Ollama Section */}
        <section className="lg:col-span-2 space-y-6">
           <div className="bg-slate-900 rounded-3xl border border-slate-800 overflow-hidden shadow-2xl">
              <div className="p-6 border-b border-slate-800 bg-slate-900/50 flex justify-between items-center">
                 <h2 className="text-lg font-bold flex items-center gap-2">
                    <Box size={20} className="text-blue-400" />
                    Ollama Models
                 </h2>
                 <span className="text-[10px] font-mono text-slate-500 bg-slate-950 px-2 py-1 rounded border border-slate-800">
                    {data?.models?.length || 0} LOADED
                 </span>
              </div>
              
              <div className="p-0">
                 {loading ? (
                    <div className="p-20 text-center flex flex-col items-center gap-3">
                       <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
                       <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">Scanning Runtime...</span>
                    </div>
                 ) : data?.models && data.models.length > 0 ? (
                    <div className="divide-y divide-slate-800/50">
                       {data.models.map((model: any) => (
                          <div key={model.name} className="p-4 hover:bg-slate-800/30 transition-colors flex items-center justify-between group">
                             <div className="flex items-center gap-4">
                                <div className="p-2.5 bg-slate-950 rounded-xl border border-slate-800 group-hover:border-blue-500/30 transition-colors">
                                   <Cpu size={18} className="text-slate-400 group-hover:text-blue-400" />
                                </div>
                                <div>
                                   <div className="font-bold text-sm text-slate-200">{model.name}</div>
                                   <div className="text-[10px] font-mono text-slate-500 uppercase tracking-tighter">
                                      {model.details?.parameter_size} • {model.details?.quantization_level}
                                   </div>
                                </div>
                             </div>
                             <div className="text-right">
                                <div className="text-xs font-bold text-slate-300">{(model.size / (1024**3)).toFixed(1)} GB</div>
                                <div className="text-[9px] text-slate-600 font-medium">Last used: {new Date(model.modified_at).toLocaleDateString()}</div>
                             </div>
                          </div>
                       ))}
                    </div>
                 ) : (
                    <div className="p-20 text-center flex flex-col items-center gap-4 opacity-40">
                       <XCircle size={40} className="text-slate-600" />
                       <p className="text-sm font-medium">Ollama is offline or no models found.</p>
                    </div>
                 )}
              </div>
           </div>

           <div className="bg-slate-900 p-8 rounded-3xl border border-slate-800 shadow-2xl relative overflow-hidden group">
              <div className="absolute top-0 right-0 p-8 opacity-5 group-hover:scale-110 transition-transform">
                 <ShieldCheck size={120} strokeWidth={4} />
              </div>
              <h3 className="text-xl font-black mb-2 flex items-center gap-3">
                 <ShieldCheck className="text-emerald-500" />
                 PRIVACY FIRST
              </h3>
              <p className="text-slate-400 text-sm leading-relaxed max-w-2xl">
                 Your local models run entirely on your hardware. No data leaves your machine. 
                 The Agent Observability Harness only tracks metadata for monitoring performance and usage efficiency.
              </p>
           </div>
        </section>

        {/* Sidebar Stats */}
        <aside className="space-y-6">
           <div className="bg-slate-900 p-6 rounded-3xl border border-slate-800 shadow-2xl">
              <h3 className="text-xs font-black text-slate-500 uppercase tracking-[0.2em] mb-6">Model Storage</h3>
              <div className="space-y-6">
                 <div className="space-y-3">
                    <div className="flex justify-between items-center text-[10px] font-black uppercase tracking-widest">
                       <span className="flex items-center gap-2 text-blue-400"><Box size={12} /> Ollama Hub</span>
                       <span className="text-slate-300">{(data?.models?.reduce((acc: number, m: any) => acc + m.size, 0) / (1024**3) || 0).toFixed(1)} GB</span>
                    </div>
                    <div className="h-2 bg-slate-950 rounded-full border border-slate-800 overflow-hidden">
                       <div className="h-full bg-blue-500" style={{ width: "40%" }}></div>
                    </div>
                 </div>

                 <div className="space-y-3">
                    <div className="flex justify-between items-center text-[10px] font-black uppercase tracking-widest">
                       <span className="flex items-center gap-2 text-amber-400"><Download size={12} /> Hugging Face</span>
                       <span className="text-slate-300">{data?.hf_usage || "0 GB"}</span>
                    </div>
                    <div className="h-2 bg-slate-950 rounded-full border border-slate-800 overflow-hidden">
                       <div className="h-full bg-amber-500" style={{ width: "65%" }}></div>
                    </div>
                 </div>
              </div>
              
              <div className="mt-8 pt-6 border-t border-slate-800 flex items-center gap-3">
                 <div className="p-2 bg-slate-950 rounded-lg border border-slate-800">
                    <HardDrive size={16} className="text-slate-500" />
                 </div>
                 <div>
                    <div className="text-[10px] font-black text-slate-500 uppercase">Primary Cache</div>
                    <div className="text-xs font-bold text-slate-200">~/.cache/huggingface</div>
                 </div>
              </div>
           </div>

           <div className="bg-gradient-to-br from-indigo-600 to-blue-700 p-6 rounded-3xl shadow-xl text-white group hover:scale-[1.02] transition-transform cursor-pointer relative overflow-hidden">
              <h3 className="text-lg font-black tracking-tighter mb-2 flex items-center gap-2 uppercase">
                 DEPLOY NEW MODEL
                 <ArrowRight size={18} />
              </h3>
              <p className="text-blue-100 text-sm mb-6 leading-relaxed font-medium">Download and run high-performance models from the registry.</p>
              <div className="bg-white/10 p-3 rounded-xl border border-white/10 font-mono text-[10px] text-blue-100">
                 ollama run deepseek-coder-v2
              </div>
           </div>
        </aside>
      </div>
    </div>
  );
}
