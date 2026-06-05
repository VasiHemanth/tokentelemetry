// Antigravity surface sub-label — Antigravity ships as an IDE and a CLI (each with
// its own ~/.gemini/antigravity-*/brain store); the bare `antigravity/` is the
// original app store. All roll up under one "Antigravity" agent; this chip says
// which surface a session came from. Mirrors CopilotSourceBadge.

import { Terminal, Code, AppWindow } from "lucide-react";

type AntigravitySource = "cli" | "ide" | "app";

const META: Record<AntigravitySource, { label: string; icon: typeof Terminal; cls: string }> = {
  cli: { label: "CLI", icon: Terminal,  cls: "text-amber-300 bg-amber-500/10 border-amber-500/30" },
  ide: { label: "IDE", icon: Code,      cls: "text-violet-300 bg-violet-500/10 border-violet-500/30" },
  app: { label: "APP", icon: AppWindow, cls: "text-emerald-300 bg-emerald-500/10 border-emerald-500/30" },
};

export default function AntigravitySourceBadge({
  source,
  size = "sm",
}: {
  source: string | null | undefined;
  size?: "xs" | "sm";
}) {
  const meta = source && (META as Record<string, typeof META.cli>)[source];
  if (!meta) return null; // only render when we know the surface
  const Icon = meta.icon;
  const sizing =
    size === "xs" ? "text-[9px] px-1.5 py-[1px] gap-1" : "text-[10px] px-2 py-[2px] gap-1";
  const iconSize = size === "xs" ? 9 : 11;
  return (
    <span
      className={`inline-flex items-center font-mono uppercase tracking-wider rounded border ${sizing} ${meta.cls}`}
      title={`Antigravity surface: ${meta.label.toLowerCase()}`}
    >
      <Icon size={iconSize} />
      {meta.label}
    </span>
  );
}
