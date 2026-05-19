"use client";
import { useState } from "react";
import { Copy, Check, Info } from "lucide-react";

const FULL_COMMAND =
  "curl -fsSL https://tokentelemetry.com/install.sh | bash && hermes plugins install VasiHemanth/tokentelemetry-hermes-plugin && hermes dashboard";

const STEPS: { kicker: string; tagline: string; lines: string[] }[] = [
  {
    kicker: "1 · Run TokenTelemetry",
    tagline: "the engine — port :3000",
    lines: [
      "curl -fsSL https://tokentelemetry.com/install.sh | bash",
    ],
  },
  {
    kicker: "2 · Plug it into Hermes Dashboard",
    tagline: "the bridge — port :9119",
    lines: [
      "hermes plugins install VasiHemanth/tokentelemetry-hermes-plugin",
      "hermes dashboard",
    ],
  },
];

export default function PluginInstallBlock() {
  const [copied, setCopied] = useState(false);

  const copy = () => {
    navigator.clipboard?.writeText(FULL_COMMAND);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-[var(--tt-border)] bg-[var(--tt-raised)]">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-medium uppercase tracking-[0.18em] text-[#eab308]">
            Install in two acts
          </span>
          <span className="text-[10px] font-mono text-[var(--tt-fg-dim)]">
            :9119 → :3000
          </span>
        </div>
        <button
          onClick={copy}
          aria-label="Copy full install sequence"
          className="inline-flex items-center gap-1.5 px-2 py-1 rounded text-[11px] font-medium text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] hover:bg-[var(--tt-panel)] transition-colors"
        >
          {copied ? (
            <>
              <Check size={12} className="text-emerald-400" /> Copied all
            </>
          ) : (
            <>
              <Copy size={12} /> Copy all
            </>
          )}
        </button>
      </div>

      {/* Two steps */}
      <div className="divide-y divide-[var(--tt-border)]">
        {STEPS.map((step, i) => (
          <div key={i} className="px-4 py-3">
            <div className="flex items-baseline justify-between mb-1.5">
              <span className="text-[11px] font-semibold tracking-[-0.005em] text-[var(--tt-fg)]">
                {step.kicker}
              </span>
              <span className="text-[10px] font-mono text-[var(--tt-fg-dim)]">
                {step.tagline}
              </span>
            </div>
            <pre className="text-[12.5px] font-mono leading-relaxed overflow-x-auto">
              {step.lines.map((line, j) => (
                <div key={j} className="flex gap-2">
                  <span className="text-[var(--tt-fg-dim)] select-none">$</span>
                  <span className="text-[var(--tt-fg)]">{line}</span>
                </div>
              ))}
            </pre>
          </div>
        ))}
      </div>

      {/* The honesty footer */}
      <div className="flex items-start gap-2 px-4 py-2.5 border-t border-[var(--tt-border)] bg-[#eab308]/[0.04]">
        <Info size={12} className="text-[#eab308] mt-0.5 shrink-0" />
        <p className="text-[11px] text-[var(--tt-fg-muted)] leading-relaxed">
          <strong className="text-[var(--tt-fg)]">The plugin is a launcher, not the engine.</strong>{" "}
          It opens TokenTelemetry pages inside Hermes Dashboard — but only when TT itself is running. Skip step 1 if you already have TT on
          <code className="font-mono text-[var(--tt-fg-muted)] mx-0.5">:3000</code>.
        </p>
      </div>
    </div>
  );
}
