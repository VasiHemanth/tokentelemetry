import type { SVGProps } from "react";
import {
  Antigravity, ClaudeCode, Cline, Codex, Copilot, Cursor, GeminiCLI, Grok,
  HermesAgent, OpenCode, Qwen,
} from "@lobehub/icons";
import { getAgent, type AgentKey } from "@/lib/agents";

type LogoProps = Pick<SVGProps<SVGSVGElement>, "className" | "aria-hidden"> & {
  agent: string;
  size?: number;
  decorative?: boolean;
};

/**
 * Brand marks for connected coding agents. Lobe Icons supplies MIT-licensed
 * local SVG components for the public brands; proprietary/local integrations
 * retain their original TokenTelemetry marks as an explicit fallback.
 */
export function AgentLogo({ agent, size = 16, decorative = true, className }: LogoProps) {
  const meta = getAgent(agent);
  const props = {
    "aria-hidden": decorative ? true : undefined,
    className,
    size,
    title: decorative ? undefined : meta.label,
  };

  switch (agent as AgentKey) {
    case "claude": return <ClaudeCode {...props} />;
    case "codex": return <Codex {...props} />;
    case "gemini": return <GeminiCLI {...props} />;
    case "antigravity": return <Antigravity {...props} />;
    case "qwen": return <Qwen {...props} />;
    case "cursor": return <Cursor {...props} />;
    case "copilot": return <Copilot {...props} />;
    case "opencode": return <OpenCode {...props} />;
    case "hermes": return <HermesAgent {...props} />;
    case "grok": return <Grok {...props} />;
    case "cline": return <Cline {...props} />;
    default: {
      const Fallback = meta.icon;
      return <Fallback {...props} color={meta.hex} />;
    }
  }
}
