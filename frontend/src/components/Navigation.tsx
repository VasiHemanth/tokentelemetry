"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Folder, BarChart3, Activity, Settings2,
  PanelLeftOpen, PanelLeftClose, Zap,
} from "lucide-react";
import { useResource } from "@/lib/api";
import { ALL_AGENT_KEYS, getAgent } from "@/lib/agents";
import { cn } from "@/lib/cn";
import { ThemeToggle } from "./ThemeToggle";
import NotificationBell from "./notifications/NotificationBell";
import HermesIcon from "./icons/HermesIcon";

interface NavigationProps {
  isCollapsed: boolean;
  setIsCollapsed: (collapsed: boolean) => void;
}

const LINKS = [
  { name: "Dashboard", href: "/",         icon: LayoutDashboard },
  { name: "Projects",  href: "/projects", icon: Folder },
  { name: "Analytics", href: "/analytics", icon: BarChart3 },
  { name: "Local Models", href: "/local-models", icon: Zap },
];

export default function Navigation({ isCollapsed, setIsCollapsed }: NavigationProps) {
  const pathname = usePathname();
  const { data: availableAgents = [] } = useResource<string[]>("/agents", { initial: [] });

  return (
    <nav
      className={cn(
        "sticky top-0 z-[100] h-screen flex flex-col p-3 transition-[width] duration-300 ease-out",
        "bg-[var(--tt-panel)]/80 backdrop-blur-md border-r border-[var(--tt-border)]",
        isCollapsed ? "w-[72px]" : "w-64",
      )}
    >
      {/* Brand */}
      <div className={cn("flex items-center gap-3 px-2 py-3 mb-3", isCollapsed && "justify-center px-0")}>
        <div className="relative h-8 w-8 grid place-items-center rounded-[var(--tt-radius)] bg-gradient-to-br from-[var(--tt-brand)] to-[var(--tt-brand-deep)] shadow-[0_0_20px_-4px_var(--tt-brand-glow)]">
          <Activity className="text-white" size={16} strokeWidth={2.5} />
        </div>
        {!isCollapsed && (
          <div className="min-w-0">
            <div className="text-[14px] font-semibold tracking-[-0.01em] text-[var(--tt-fg)] leading-tight">
              TokenTelemetry
            </div>
            <div className="text-[10px] tracking-[0.18em] uppercase text-[var(--tt-fg-dim)] leading-tight">
              Agent observability
            </div>
          </div>
        )}
      </div>

      {/* Links */}
      <div className="space-y-0.5">
        {[
          ...LINKS,
          ...(availableAgents.includes("hermes")
            ? [{ name: "Hermes Agent", href: "/hermes", icon: HermesIcon as typeof LayoutDashboard }]
            : []),
        ].map((link) => (
          <NavLink key={link.name} link={link} pathname={pathname} isCollapsed={isCollapsed} />
        ))}
      </div>

      {/* Connected agents */}
      <div className="mt-auto space-y-3">
        {!isCollapsed && availableAgents.length > 0 && (
          <div className="rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-sunken)] p-3">
            <div className="text-[9px] font-semibold uppercase tracking-[0.2em] text-[var(--tt-fg-dim)] mb-2.5 flex items-center justify-between">
              <span>Connected</span>
              <span className="tabular text-[var(--tt-fg-muted)]">{availableAgents.length}</span>
            </div>
            <div className="grid grid-cols-1 gap-1.5">
              {availableAgents.map((k) => {
                if (!ALL_AGENT_KEYS.includes(k as never)) return null;
                const meta = getAgent(k);
                return (
                  <div key={k} className="flex items-center gap-2 text-[11px] text-[var(--tt-fg-muted)]">
                    <span
                      className="w-1.5 h-1.5 rounded-full"
                      style={{ backgroundColor: meta.hex, boxShadow: `0 0 8px ${meta.hex}80` }}
                    />
                    <span className="truncate">{meta.label}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <NotificationBell collapsed={isCollapsed} />

        <NavLink
          link={{ name: "Settings", href: "/settings", icon: Settings2 }}
          pathname={pathname}
          isCollapsed={isCollapsed}
        />

        <ThemeToggle collapsed={isCollapsed} />

        <button
          onClick={() => setIsCollapsed(!isCollapsed)}
          aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={cn(
            "w-full flex items-center justify-center gap-2 rounded-[var(--tt-radius)] py-2 text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)] hover:tt-tint-1 transition-colors border border-transparent hover:border-[var(--tt-border)]",
          )}
        >
          {isCollapsed
            ? <PanelLeftOpen size={16} />
            : (<><PanelLeftClose size={14} /><span className="text-[10px] uppercase tracking-[0.18em]">Collapse</span></>)}
        </button>
      </div>
    </nav>
  );
}

type NavLinkItem = { name: string; href: string; icon: typeof LayoutDashboard };

function NavLink({ link, pathname, isCollapsed }: {
  link: NavLinkItem; pathname: string; isCollapsed: boolean;
}) {
  const Icon = link.icon;
  const isActive = pathname === link.href || (link.href !== "/" && pathname.startsWith(link.href));
  return (
    <Link
      href={link.href}
      title={isCollapsed ? link.name : undefined}
      className={cn(
        "relative flex items-center gap-3 rounded-[var(--tt-radius)] px-2.5 py-2 text-[13px] font-medium transition-colors",
        isActive
          ? "tt-tint-1 text-[var(--tt-fg)]"
          : "text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] hover:tt-tint-1",
        isCollapsed && "justify-center",
      )}
    >
      {isActive && (
        <span
          aria-hidden
          className="absolute left-0 top-1.5 bottom-1.5 w-[2px] rounded-r-full bg-[var(--tt-brand)] shadow-[0_0_10px_var(--tt-brand-glow)]"
        />
      )}
      <Icon size={16} strokeWidth={isActive ? 2.25 : 1.75} className={isActive ? "text-[var(--tt-brand)]" : ""} />
      {!isCollapsed && <span>{link.name}</span>}
    </Link>
  );
}
