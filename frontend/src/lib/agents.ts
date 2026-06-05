import {
  Terminal, Database, Sparkles, Orbit, Cpu, Zap, MousePointer2,
  GitBranch, Code2, Server, type LucideIcon,
} from "lucide-react";
import HermesIcon from "@/components/icons/HermesIcon";
import GrokIcon from "@/components/icons/GrokIcon";

export type AgentKey =
  | "claude" | "codex" | "gemini" | "antigravity"
  | "qwen" | "vibe" | "cursor" | "copilot" | "opencode" | "hermes" | "grok"
  | "openai_compat";

export interface AgentMeta {
  key: AgentKey;
  label: string;
  /** Brand hex, also exposed as `--agent-{key}` CSS variable. */
  hex: string;
  icon: LucideIcon;
}

export const AGENTS: Record<AgentKey, AgentMeta> = {
  claude:      { key: "claude",      label: "Claude Code", hex: "#f97316", icon: Terminal },
  codex:       { key: "codex",       label: "Codex",       hex: "#a855f7", icon: Database },
  gemini:      { key: "gemini",      label: "Gemini CLI",  hex: "#06b6d4", icon: Sparkles },
  antigravity: { key: "antigravity", label: "Antigravity", hex: "#10b981", icon: Orbit },
  qwen:        { key: "qwen",        label: "Qwen CLI",    hex: "#3b82f6", icon: Cpu },
  vibe:        { key: "vibe",        label: "Vibe",        hex: "#f472b6", icon: Zap },
  cursor:      { key: "cursor",      label: "Cursor",      hex: "#60a5fa", icon: MousePointer2 },
  copilot:     { key: "copilot",     label: "Copilot",     hex: "#6366f1", icon: GitBranch },
  opencode:    { key: "opencode",    label: "OpenCode",    hex: "#f59e0b", icon: Code2 },
  hermes:      { key: "hermes",      label: "Hermes Agent", hex: "#eab308", icon: HermesIcon },
  grok:        { key: "grok",        label: "Grok Build",  hex: "#d4d4d8", icon: GrokIcon },
  openai_compat: { key: "openai_compat", label: "OpenAI-compatible server", hex: "#14b8a6", icon: Server },
};

const FALLBACK: AgentMeta = {
  key: "claude", label: "Unknown", hex: "#64748b", icon: Terminal,
};

export function getAgent(key: string | undefined | null): AgentMeta {
  if (!key) return FALLBACK;
  return (AGENTS as Record<string, AgentMeta>)[key] ?? { ...FALLBACK, label: key };
}

export const ALL_AGENT_KEYS = Object.keys(AGENTS) as AgentKey[];
