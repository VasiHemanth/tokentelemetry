import { ShieldCheck } from "lucide-react";

/** The standing "what gets embedded" note from the v3 spec. Shown next to the index banner. */
export function EmbedNote() {
  return (
    <div className="flex items-start gap-2.5 rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-sunken)] px-3 py-2.5 text-[12px] text-[var(--tt-fg-muted)]">
      <ShieldCheck size={14} className="mt-0.5 shrink-0 text-[var(--tt-fg-dim)]" />
      <div className="space-y-1">
        <p className="font-medium text-[var(--tt-fg)]">What gets embedded</p>
        <ul className="list-disc pl-4 space-y-0.5">
          <li>Only projects you turn on. Nothing is embedded for projects you never enable.</li>
          <li>Only these content types: sessions, images, skills, commands, agents, artifacts/plans, .md files, MCP config. Never source code.</li>
        </ul>
      </div>
    </div>
  );
}
