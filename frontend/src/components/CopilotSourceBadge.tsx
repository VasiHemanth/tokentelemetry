// Copilot surface sub-label — distinguishes the GitHub Copilot CLI/agent
// (~/.copilot/session-state) from the VS Code Copilot chat store. Both roll up
// under the single "Copilot" agent; this chip just says which surface (#36).

import { Terminal, Code } from "lucide-react";

type CopilotSource = "cli" | "vscode";

const META: Record<CopilotSource, { label: string; icon: typeof Terminal; cls: string }> = {
  cli:    { label: "CLI",     icon: Terminal, cls: "text-amber-300 bg-amber-500/10 border-amber-500/30" },
  vscode: { label: "VS CODE", icon: Code,     cls: "text-sky-300 bg-sky-500/10 border-sky-500/30" },
};

export default function CopilotSourceBadge({
  source,
  size = "sm",
}: {
  source: string | null | undefined;
  size?: "xs" | "sm";
}) {
  const meta = source && (META as Record<string, typeof META.cli>)[source];
  if (!meta) return null; // only render when we actually know the surface
  const Icon = meta.icon;
  const sizing =
    size === "xs" ? "text-[9px] px-1.5 py-[1px] gap-1" : "text-[10px] px-2 py-[2px] gap-1";
  const iconSize = size === "xs" ? 9 : 11;
  return (
    <span
      className={`inline-flex items-center font-mono uppercase tracking-wider rounded border ${sizing} ${meta.cls}`}
      title={`Copilot surface: ${meta.label.toLowerCase()}`}
    >
      <Icon size={iconSize} />
      {meta.label}
    </span>
  );
}
