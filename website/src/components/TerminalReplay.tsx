"use client";
import { useEffect, useState } from "react";
import { TERMINAL_SCRIPT, SCRIPT_DURATION_MS, type ScriptLine } from "@/data/terminal-script";

const COLOR: Record<ScriptLine["kind"], string> = {
  header:    "text-slate-500",
  user:      "text-blue-300",
  reasoning: "text-amber-400/80 italic",
  tool:      "text-sky-300",
  result:    "text-slate-400",
  cost:      "text-emerald-400",
};

export default function TerminalReplay() {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const start = Date.now();
    const id = setInterval(() => {
      const t = (Date.now() - start) % (SCRIPT_DURATION_MS + 1500);
      setElapsed(t);
    }, 60);
    return () => clearInterval(id);
  }, []);

  const visible = TERMINAL_SCRIPT.filter((l) => l.delay <= elapsed);

  return (
    <div className="bg-slate-950 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden glow-blue">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-800 bg-slate-900/50">
        <div className="w-3 h-3 rounded-full bg-red-500/70" />
        <div className="w-3 h-3 rounded-full bg-yellow-500/70" />
        <div className="w-3 h-3 rounded-full bg-emerald-500/70" />
        <span className="ml-3 text-[10px] font-mono text-slate-500 uppercase tracking-widest truncate">tokentelemetry · session-trace</span>
      </div>
      <div className="p-4 sm:p-5 font-mono text-[11px] sm:text-[12px] leading-relaxed min-h-[280px] sm:min-h-[320px] space-y-1.5 overflow-x-auto">
        {visible.map((line, i) => (
          <div key={i} className={`${COLOR[line.kind]} transition-opacity whitespace-pre-wrap break-words`}>
            {line.text}
          </div>
        ))}
        <span className="inline-block w-2 h-4 bg-emerald-400/70 align-middle pulse-glow" />
      </div>
    </div>
  );
}
