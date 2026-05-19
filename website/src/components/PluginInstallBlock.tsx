"use client";
import { useState } from "react";
import { Copy, Check } from "lucide-react";

const COMMAND =
  "git clone https://github.com/VasiHemanth/tokentelemetry.git && cd tokentelemetry && ./scripts/install-hermes-plugin.sh && hermes dashboard";

const LINES = [
  { prompt: "$", text: "git clone https://github.com/VasiHemanth/tokentelemetry.git" },
  { prompt: "$", text: "cd tokentelemetry" },
  { prompt: "$", text: "./scripts/install-hermes-plugin.sh" },
  { prompt: "$", text: "hermes dashboard" },
];

export default function PluginInstallBlock() {
  const [copied, setCopied] = useState(false);

  const copy = () => {
    navigator.clipboard?.writeText(COMMAND);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 border-b border-[var(--tt-border)] bg-[var(--tt-raised)]">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-medium uppercase tracking-[0.18em] text-[#eab308]">
            Install the plugin
          </span>
          <span className="text-[10px] font-mono text-[var(--tt-fg-dim)]">
            :9119 → :3000
          </span>
        </div>
        <button
          onClick={copy}
          aria-label="Copy install command"
          className="inline-flex items-center gap-1.5 px-2 py-1 rounded text-[11px] font-medium text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] hover:bg-[var(--tt-panel)] transition-colors"
        >
          {copied ? (
            <>
              <Check size={12} className="text-emerald-400" /> Copied
            </>
          ) : (
            <>
              <Copy size={12} /> Copy
            </>
          )}
        </button>
      </div>
      <pre className="px-4 py-3 text-[12.5px] font-mono leading-relaxed overflow-x-auto">
        {LINES.map((line, i) => (
          <div key={i} className="flex gap-2">
            <span className="text-[var(--tt-fg-dim)] select-none">{line.prompt}</span>
            <span className="text-[var(--tt-fg)]">{line.text}</span>
          </div>
        ))}
      </pre>
      <div className="px-4 py-2 border-t border-[var(--tt-border)] text-[11px] text-[var(--tt-fg-dim)] leading-relaxed">
        Then open{" "}
        <code className="font-mono text-[var(--tt-fg-muted)]">http://127.0.0.1:9119</code>{" "}
        and click <strong className="text-[var(--tt-fg-muted)]">TokenTelemetry</strong> in the sidebar.
      </div>
    </div>
  );
}
