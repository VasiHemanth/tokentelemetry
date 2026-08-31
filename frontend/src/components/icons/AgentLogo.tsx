import type { SVGProps } from "react";
import {
  Antigravity, ClaudeCode, Cline, Codex, Copilot, Cursor, GeminiCLI, Grok,
  HermesAgent, OpenCode, Qoder, Qwen,
} from "@lobehub/icons";
import { getAgent, type AgentKey } from "@/lib/agents";

type LogoProps = Pick<SVGProps<SVGSVGElement>, "className" | "aria-hidden"> & {
  agent: string;
  size?: number;
  decorative?: boolean;
  /** Draw the brand's own colours instead of inheriting the current text colour. */
  color?: boolean;
};

/**
 * Brand marks for connected coding agents. Lobe Icons supplies MIT-licensed
 * local SVG components for the public brands; proprietary/local integrations
 * retain their original TokenTelemetry marks as an explicit fallback.
 */
/**
 * Brands whose Lobe mark ships a full-colour variant. The rest — Cursor, Grok,
 * OpenCode, Cline, Hermes — are monochrome marks by design, so `color` leaves
 * them inheriting the tile's brand tint rather than inventing a palette.
 */
const COLOR_MARKS = {
  claude: ClaudeCode.Color,
  codex: Codex.Color,
  gemini: GeminiCLI.Color,
  antigravity: Antigravity.Color,
  qwen: Qwen.Color,
  copilot: Copilot.Color,
  qoder: Qoder.Color,
} as const;

export function AgentLogo({ agent, size = 16, decorative = true, className, color = false }: LogoProps) {
  const meta = getAgent(agent);
  const props = {
    "aria-hidden": decorative ? true : undefined,
    className,
    size,
    title: decorative ? undefined : meta.label,
  };

  const ColorMark = color ? COLOR_MARKS[agent as keyof typeof COLOR_MARKS] : undefined;
  if (ColorMark) return <ColorMark {...props} />;

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
    case "qoder": return <Qoder {...props} />;
    default: {
      const Fallback = meta.icon;
      return <Fallback {...props} color={meta.hex} />;
    }
  }
}
