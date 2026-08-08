import type { SVGProps } from "react";
import {
  Antigravity, ClaudeCode, Cline, Codex, Copilot, Cursor, GeminiCLI, Grok,
  HermesAgent, OpenCode, Qwen,
} from "@lobehub/icons";
import { Bot, Boxes, Zap } from "lucide-react";

type Props = { name: string; size?: number };
type MarkProps = Pick<SVGProps<SVGSVGElement>, "className" | "aria-hidden"> & { size?: number };

function PiMark({ size = 16 }: MarkProps) {
  return <svg aria-hidden width={size} height={size} viewBox="0 0 800 800" fill="currentColor"><path fillRule="evenodd" d="M165.29 165.29H517.36V400H400V517.36H282.65V634.72H165.29ZM282.65 282.65V400H400V282.65Z" /><path d="M517.36 400H634.72V634.72H517.36Z" /></svg>;
}

function MuseMark({ size = 16 }: MarkProps) {
  return <svg aria-hidden width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m12 2 1.5 6.5L20 10l-6.5 1.5L12 18l-1.5-6.5L4 10l6.5-1.5L12 2Z" /><path d="m18.5 16 .6 2.4 2.4.6-2.4.6-.6 2.4-.6-2.4-2.4-.6 2.4-.6.6-2.4Z" /></svg>;
}

function PrimeMark({ size = 16 }: MarkProps) {
  return <svg aria-hidden width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 18 10 12l3 3 7-8" /><path d="M16 7h4v4" /><path d="m7 4 .7 2.3L10 7l-2.3.7L7 10l-.7-2.3L4 7l2.3-.7L7 4Z" /></svg>;
}

/** Brand marks used by the public coverage grid; no generic status dots. */
export default function AgentIcon({ name, size = 16 }: Props) {
  const props = { size, "aria-hidden": true as const };
  switch (name) {
    case "Claude Code": return <ClaudeCode {...props} />;
    case "Codex": return <Codex {...props} />;
    case "Gemini CLI": return <GeminiCLI {...props} />;
    case "Antigravity": return <Antigravity {...props} />;
    case "Qwen CLI": return <Qwen {...props} />;
    case "Cursor": return <Cursor {...props} />;
    case "GitHub Copilot": return <Copilot {...props} />;
    case "OpenCode": return <OpenCode {...props} />;
    case "Grok Build": return <Grok {...props} />;
    case "Hermes Agent": return <HermesAgent {...props} />;
    case "Cline": return <Cline {...props} />;
    case "Pi": return <PiMark {...props} />;
    case "Muse Code": return <MuseMark {...props} />;
    case "Prime Agent": return <PrimeMark {...props} />;
    case "Vibe": return <Zap {...props} />;
    case "SmallCode": return <Boxes {...props} />;
    default: return <Bot {...props} />;
  }
}
