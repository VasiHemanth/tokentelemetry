import * as React from "react";
import { cn } from "@/lib/cn";

export interface SectionProps extends Omit<React.HTMLAttributes<HTMLElement>, "title"> {
  title?: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
}

export function Section({ title, description, actions, className, children, ...rest }: SectionProps) {
  return (
    <section className={cn("space-y-3", className)} {...rest}>
      {(title || actions || description) && (
        <div className="flex items-end justify-between gap-3 px-0.5">
          <div>
            {title && (
              <h2 className="text-[16px] font-semibold text-[var(--tt-fg)]">
                {title}
              </h2>
            )}
            {description && (
              <p className="text-[13px] text-[var(--tt-fg-muted)] mt-1">{description}</p>
            )}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}
