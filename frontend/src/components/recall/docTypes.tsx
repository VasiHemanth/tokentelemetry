import {
  MessageSquare, Image as ImageIcon, Wand2, SquareTerminal, Bot, FileText, BookOpen, Plug, type LucideIcon,
} from "lucide-react";
import type { RecallDocType } from "@/lib/recall";

export interface DocTypeMeta {
  type: RecallDocType;
  label: string;
  plural: string;
  icon: LucideIcon;
  /** Theme token (a CSS variable), also resolved by the canvas drawing code. */
  color: string;
}

export const DOC_TYPES: Record<RecallDocType, DocTypeMeta> = {
  session:  { type: "session",  label: "Session",  plural: "sessions",  icon: MessageSquare,  color: "--tt-brand" },
  image:    { type: "image",    label: "Image",    plural: "images",    icon: ImageIcon,      color: "--tt-violet-fg" },
  skill:    { type: "skill",    label: "Skill",    plural: "skills",    icon: Wand2,          color: "--tt-success-fg" },
  command:  { type: "command",  label: "Command",  plural: "commands",  icon: SquareTerminal, color: "--tt-info-fg" },
  agent:    { type: "agent",    label: "Agent",    plural: "agents",    icon: Bot,            color: "--tt-warn-fg" },
  artifact: { type: "artifact", label: "Artifact", plural: "artifacts", icon: FileText,       color: "--tt-cyan-fg" },
  markdown: { type: "markdown", label: "Markdown", plural: "markdown files", icon: BookOpen,  color: "--tt-fg-muted" },
  mcp:      { type: "mcp",      label: "MCP",      plural: "MCP servers", icon: Plug,         color: "--tt-danger-fg" },
};

const FALLBACK: DocTypeMeta = DOC_TYPES.markdown;

export function docTypeMeta(t: string | undefined | null): DocTypeMeta {
  if (!t) return DOC_TYPES.session;
  return (DOC_TYPES as Record<string, DocTypeMeta>)[t] ?? FALLBACK;
}

export function DocTypeIcon({ type, size = 13, className }: { type: string | undefined | null; size?: number; className?: string }) {
  const m = docTypeMeta(type);
  const I = m.icon;
  return <I size={size} className={className} style={{ color: `var(${m.color})` }} aria-label={m.label} />;
}

/** Read a theme token off an element so canvas drawing follows light and dark themes. */
export function cssVar(el: Element, name: string, fallback = "#888"): string {
  const v = getComputedStyle(el).getPropertyValue(name).trim();
  return v || fallback;
}
