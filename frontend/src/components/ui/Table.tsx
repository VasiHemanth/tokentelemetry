import * as React from "react";
import { cn } from "@/lib/cn";

/**
 * Lightweight table primitives. Sticky header, hairline rows, hover affordance.
 * Use semantic <table> for a11y; consumers compose <THead>/<TBody>/<TR>/<TH>/<TD>.
 */

export function Table({ className, ...rest }: React.TableHTMLAttributes<HTMLTableElement>) {
  return (
    <div className="relative overflow-x-auto">
      <table className={cn("w-full text-left border-separate border-spacing-0", className)} {...rest} />
    </div>
  );
}

export function THead({ className, ...rest }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <thead
      className={cn(
        "sticky top-0 z-10 bg-[var(--tt-panel)]/95 backdrop-blur supports-[backdrop-filter]:bg-[var(--tt-panel)]/70",
        className,
      )}
      {...rest}
    />
  );
}

export function TBody(props: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody {...props} />;
}

export function TR({ className, interactive, ...rest }:
  React.HTMLAttributes<HTMLTableRowElement> & { interactive?: boolean }) {
  return (
    <tr
      className={cn(
        "group",
        interactive && "cursor-pointer hover:tt-tint-1",
        className,
      )}
      {...rest}
    />
  );
}

export function TH({ className, ...rest }: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn(
        "px-4 py-2.5 text-[12px] font-medium text-[var(--tt-fg-dim)] border-b border-[var(--tt-border)] whitespace-nowrap",
        className,
      )}
      {...rest}
    />
  );
}

export function TD({ className, ...rest }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td
      className={cn(
        "px-4 py-3 text-[13px] text-[var(--tt-fg)] border-b border-[var(--tt-border)] align-middle",
        className,
      )}
      {...rest}
    />
  );
}
