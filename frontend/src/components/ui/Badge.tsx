import * as React from "react";
import { cn } from "@/lib/cn";
import { getAgent } from "@/lib/agents";
import { AgentLogo } from "@/components/icons/AgentLogo";

type Variant = "neutral" | "brand" | "success" | "warn" | "danger" | "info" | "outline";

const VARIANT: Record<Variant, string> = {
  neutral: "tt-tint-2 text-[var(--tt-fg-muted)] border-[var(--tt-border)]",
  brand:   "bg-[color:var(--tt-brand-glow)] text-[var(--tt-brand)] border-[color:var(--tt-brand)]/25",
  success: "bg-[var(--tt-success-bg)] text-[var(--tt-success-fg)] border-[var(--tt-success-bd)]",
  warn:    "bg-[var(--tt-warn-bg)] text-[var(--tt-warn-fg)] border-[var(--tt-warn-bd)]",
  danger:  "bg-[var(--tt-danger-bg)] text-[var(--tt-danger-fg)] border-[var(--tt-danger-bd)]",
  info:    "bg-[var(--tt-info-bg)] text-[var(--tt-info-fg)] border-[var(--tt-info-bd)]",
  outline: "bg-transparent text-[var(--tt-fg-muted)] border-[var(--tt-border-strong)]",
};

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: Variant;
  size?: "xs" | "sm";
}

export function Badge({ variant = "neutral", size = "xs", className, ...rest }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border font-medium tracking-tight",
        size === "xs" ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-1 text-xs",
        VARIANT[variant],
        className,
      )}
      {...rest}
    />
  );
}

export interface AgentBadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  agent: string;
  withDot?: boolean;
  withLabel?: boolean;
  size?: "xs" | "sm";
}

/** Agent identity chip — brand mark + label tinted by agent hex. Uniform across the app. */
export function AgentBadge({
  agent, withDot = true, withLabel = true, size = "xs", className, ...rest
}: AgentBadgeProps) {
  const meta = getAgent(agent);
  // Near-white brand marks (Grok, Pi, Qoder) get a theme-aware tint so their chip
  // label and mark stay legible in light mode; the tinted background/border stay
  // on the literal hex (they are translucent and fine in either theme).
  const isLightBrand = agent === "grok" || agent === "pi" || agent === "qoder";
  const foreground = isLightBrand ? `var(--agent-${agent})` : meta.hex;
  return (
    <span
      style={{
        backgroundColor: `${meta.hex}14`,
        color: foreground,
        borderColor: `${meta.hex}33`,
      }}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border font-medium tracking-tight uppercase",
        size === "xs" ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-1 text-xs",
        className,
      )}
      {...rest}
    >
      {withDot && (
        <AgentLogo agent={agent} size={size === "xs" ? 11 : 13} />
      )}
      {withLabel && meta.label}
    </span>
  );
}
