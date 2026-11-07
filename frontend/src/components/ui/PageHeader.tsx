import * as React from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { cn } from "@/lib/cn";

export interface PageHeaderProps {
  backHref?: string;
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  description?: React.ReactNode;
  icon?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}

export function PageHeader({ backHref, eyebrow, title, description, icon, actions, className }: PageHeaderProps) {
  return (
    <header className={cn("flex flex-wrap items-end justify-between gap-6 pb-6 border-b border-[var(--tt-border)]", className)}>
      <div className="flex items-start gap-4 min-w-0">
        {backHref && (
          <Link
            href={backHref}
            title="Back"
            aria-label="Back"
            className="mt-1 h-9 w-9 grid place-items-center rounded-[var(--tt-radius)] border border-[var(--tt-border)] text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] hover:tt-tint-1 transition-colors shrink-0"
          >
            <ArrowLeft size={16} />
          </Link>
        )}
        {icon && (
          <div className="mt-1 flex h-10 w-10 items-center justify-center rounded-[var(--tt-radius)] tt-tint-2 border border-[var(--tt-border)] text-[var(--tt-brand)]">
            {icon}
          </div>
        )}
        <div className="min-w-0">
          {eyebrow && (
            <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--tt-fg-dim)] mb-1.5">
              {eyebrow}
            </div>
          )}
          <h1 className="text-[28px] leading-[1.05] font-semibold tracking-[-0.02em] text-[var(--tt-fg)] truncate">
            {title}
          </h1>
          {description && (
            <p className="mt-1.5 text-sm text-[var(--tt-fg-muted)] max-w-2xl">{description}</p>
          )}
        </div>
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </header>
  );
}
