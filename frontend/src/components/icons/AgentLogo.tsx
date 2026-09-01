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
 * OpenCode, Cline, Hermes — are monochrome marks by design; for those, `color`
 * tints the mark with the brand's own hex rather than inventing a palette, so
 * the prop means "the brand's colours" for every agent either way.
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
  // Near-white brand marks (Grok, Pi) are stored in globals.css as theme-aware
  // `--agent-<key>` variables so a light-mode build re-tints them to something
  // visible instead of a white glyph on a white surface. These brands are always
  // tinted — even when `color` is false — because their intrinsic mark is white,
  // so inheriting `currentColor` from a container that uses the brand hex would
  // leave them invisible on a light background (and monochrome elsewhere).
  const isLightBrand = agent === "grok" || agent === "pi" || agent === "qoder";
  const brandColor = isLightBrand ? `var(--agent-${agent})` : meta.hex;
  const applyTint = color || isLightBrand;
  const props = {
    "aria-hidden": decorative ? true : undefined,
    className,
    size,
    title: decorative ? undefined : meta.label,
    // Lobe's monochrome marks fill with currentColor, so the brand hex reaches
    // them through `style`. A full-colour mark ignores it, which is correct.
    ...(applyTint ? { style: { color: brandColor } } : {}),
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
