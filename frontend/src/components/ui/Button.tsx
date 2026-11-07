import * as React from "react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const VARIANT: Record<Variant, string> = {
  primary:   "bg-[var(--tt-brand-deep)] hover:bg-[var(--tt-brand-deep)] text-white border border-transparent hover:border-[var(--tt-brand)]",
  secondary: "tt-tint-2 hover:tt-tint-3 text-[var(--tt-fg)] border border-[var(--tt-border-strong)]",
  ghost:     "bg-transparent hover:tt-tint-2 text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)]",
  danger:    "bg-rose-500/15 hover:bg-rose-500/25 text-rose-300 border border-rose-500/30",
};

const SIZE: Record<Size, string> = {
  sm: "h-8 px-2.5 text-xs gap-1.5",
  md: "h-9 px-3.5 text-[13px] gap-2",
  lg: "h-10 px-4 text-sm gap-2",
};

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", className, ...rest }, ref,
) {
  return (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center rounded-[var(--tt-radius)] font-medium tracking-tight transition-colors disabled:opacity-50 disabled:pointer-events-none",
        VARIANT[variant], SIZE[size], className,
      )}
      {...rest}
    />
  );
});
