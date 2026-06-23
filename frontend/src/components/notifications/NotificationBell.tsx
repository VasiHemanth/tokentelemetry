"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Bell, AlertTriangle, Check, X } from "lucide-react";

import { cn } from "@/lib/cn";
import { timeAgo, type AppNotification, type NotificationSeverity } from "@/lib/notifications";
import { useNotifications } from "./NotificationProvider";

const SEV_DOT: Record<NotificationSeverity, string> = {
  info: "bg-[var(--tt-brand)]",
  warn: "bg-[var(--tt-warn)]",
  over: "bg-[var(--tt-danger)]",
};

/**
 * Sidebar-bottom notification bell. Built for the collapsed (72px) rail:
 * icon + unread badge when collapsed, icon + label + badge when expanded.
 * Clicking opens a panel that pops out to the RIGHT so it never shifts layout.
 */
export default function NotificationBell({ collapsed }: { collapsed: boolean }) {
  const { feed, markAllRead, clearAll, clearOne } = useNotifications();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const unread = feed.unread_count;
  const items = feed.notifications;

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // Opening the panel marks everything read (clears the badge).
  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && unread > 0) markAllRead();
  };

  return (
    <div ref={rootRef} className="relative">
      <button
        onClick={toggle}
        aria-label={`Notifications${unread ? ` (${unread} unread)` : ""}`}
        aria-expanded={open}
        title={collapsed ? "Notifications" : undefined}
        className={cn(
          "w-full flex items-center rounded-[var(--tt-radius)] border border-transparent transition-colors h-9",
          "text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)] hover:border-[var(--tt-border)] hover:tt-tint-1",
          collapsed ? "justify-center" : "justify-between gap-2 px-2",
          open && "tt-tint-1 text-[var(--tt-fg)]",
        )}
      >
        <span className="relative flex items-center gap-2">
          <span className="relative">
            <Bell size={collapsed ? 16 : 14} />
            {unread > 0 && (
              <span
                className="absolute -top-1.5 -right-1.5 min-w-[15px] h-[15px] px-1 grid place-items-center rounded-full bg-[var(--tt-danger)] text-white text-[9px] font-bold tabular leading-none"
                aria-hidden
              >
                {unread > 9 ? "9+" : unread}
              </span>
            )}
          </span>
          {!collapsed && (
            <span className="text-[10px] uppercase tracking-[0.18em]">Notifications</span>
          )}
        </span>
      </button>

      {open && (
        <Panel
          items={items}
          onClearAll={clearAll}
          onClearOne={clearOne}
          onNavigate={() => setOpen(false)}
          collapsed={collapsed}
        />
      )}
    </div>
  );
}

function Panel({
  items, onClearAll, onClearOne, onNavigate, collapsed,
}: {
  items: AppNotification[];
  onClearAll: () => void;
  onClearOne: (id: number) => void;
  onNavigate: () => void;
  collapsed: boolean;
}) {
  return (
    <div
      role="dialog"
      aria-label="Notifications"
      className={cn(
        "absolute z-[200] bottom-0 w-80 max-h-[70vh] flex flex-col",
        "rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] shadow-2xl",
        // Pop to the right of the rail so layout never shifts.
        collapsed ? "left-[calc(100%+12px)]" : "left-[calc(100%+8px)]",
      )}
    >
      <div className="flex items-center justify-between px-3.5 py-2.5 border-b border-[var(--tt-border)]">
        <span className="text-[12px] font-semibold text-[var(--tt-fg)]">Notifications</span>
        {items.length > 0 && (
          <button
            onClick={onClearAll}
            className="text-[11px] text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] transition-colors"
          >
            Clear all
          </button>
        )}
      </div>

      {items.length === 0 ? (
        <div className="px-4 py-10 text-center">
          <Check size={20} className="mx-auto text-[var(--tt-fg-faint)] mb-2" />
          <div className="text-[12px] text-[var(--tt-fg-dim)]">You&apos;re all caught up</div>
        </div>
      ) : (
        <div className="overflow-y-auto divide-y divide-[var(--tt-border)]">
          {items.map((n) => (
            <Row key={n.id} n={n} onClear={() => onClearOne(n.id)} onNavigate={onNavigate} />
          ))}
        </div>
      )}
    </div>
  );
}

function Row({
  n, onClear, onNavigate,
}: { n: AppNotification; onClear: () => void; onNavigate: () => void }) {
  const dot = SEV_DOT[n.severity] ?? SEV_DOT.info;
  const inner = (
    <div className="flex items-start gap-2.5 px-3.5 py-3 group hover:tt-tint-1 transition-colors">
      <span className={cn("mt-1 w-1.5 h-1.5 rounded-full shrink-0", dot)} aria-hidden />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          {n.severity === "over" && <AlertTriangle size={12} className="text-[var(--tt-danger)] shrink-0" />}
          <span className={cn(
            "text-[12px] truncate",
            n.read ? "text-[var(--tt-fg-muted)]" : "text-[var(--tt-fg)] font-medium",
          )}>
            {n.title}
          </span>
        </div>
        {n.body && <div className="text-[11px] text-[var(--tt-fg-dim)] mt-0.5 truncate">{n.body}</div>}
        <div className="text-[10px] text-[var(--tt-fg-faint)] mt-0.5">{timeAgo(n.created_at)}</div>
      </div>
      <button
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); onClear(); }}
        aria-label="Clear notification"
        className="opacity-0 group-hover:opacity-100 grid place-items-center h-5 w-5 rounded text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)] transition-all shrink-0"
      >
        <X size={13} />
      </button>
    </div>
  );

  if (n.href) {
    return <Link href={n.href} onClick={onNavigate} className="block">{inner}</Link>;
  }
  return inner;
}
