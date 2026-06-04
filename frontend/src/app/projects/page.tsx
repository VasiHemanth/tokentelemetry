"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  Folder, Search, ArrowRight, Wrench, Users, ClipboardList,
  LayoutGrid, List as ListIcon, ArrowUpDown, FolderOpen,
} from "lucide-react";

import { useResource } from "@/lib/api";
import { getAgent } from "@/lib/agents";
import { cn } from "@/lib/cn";
import { formatTokens, formatCost } from "@/lib/format";
import {
  PageHeader, Section, Card, Badge, AgentBadge, Button, EmptyState, Skeleton,
  Table, THead, TBody, TR, TH, TD,
} from "@/components/ui";

interface Project {
  name: string;
  path: string;
  session_count: number;
  agents: string[];
  mcp_tools: string[];
  subagent_count: number;
  configured_subagent_count?: number;
  plan_count: number;
  tokens?: { input: number; output: number; cached: number; total: number; cost: number };
}

type ViewMode = "grid" | "list";
type SortKey = "sessions" | "tokens" | "cost" | "name";

const SORTS: { key: SortKey; label: string }[] = [
  { key: "sessions", label: "Sessions" },
  { key: "tokens",   label: "Tokens"   },
  { key: "cost",     label: "API equiv."     },
  { key: "name",     label: "Name"     },
];

export default function ProjectsPage() {
  const { data: projects = [], loading } = useResource<Project[]>("/projects", { initial: [] });

  const [search, setSearch] = useState("");
  const [view, setView] = useState<ViewMode>("grid");
  const [sortKey, setSortKey] = useState<SortKey>("sessions");
  const [sortDesc, setSortDesc] = useState(true);

  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim();
    const list = !q ? projects : projects.filter((p) =>
      p.name.toLowerCase().includes(q) || p.path.toLowerCase().includes(q)
    );
    const cmp = (a: Project, b: Project) => {
      let av: number | string = 0, bv: number | string = 0;
      switch (sortKey) {
        case "sessions": av = a.session_count; bv = b.session_count; break;
        case "tokens":   av = a.tokens?.total ?? 0; bv = b.tokens?.total ?? 0; break;
        case "cost":     av = a.tokens?.cost ?? 0;  bv = b.tokens?.cost ?? 0;  break;
        case "name":     av = a.name.toLowerCase(); bv = b.name.toLowerCase(); break;
      }
      if (av < bv) return sortDesc ? 1 : -1;
      if (av > bv) return sortDesc ? -1 : 1;
      return 0;
    };
    return [...list].sort(cmp);
  }, [projects, search, sortKey, sortDesc]);

  return (
    <div className="px-8 py-8 max-w-[1600px] mx-auto space-y-8 pb-20">
      <PageHeader
        eyebrow="Workspaces"
        title="Projects"
        description="Activity grouped by workspace path. Each card opens a project workspace with sessions, plans, and config."
        icon={<Folder size={20} strokeWidth={2.25} />}
        actions={
          <Badge variant="neutral" size="sm" className="h-9">
            {projects.length} {projects.length === 1 ? "project" : "projects"}
          </Badge>
        }
      />

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[260px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--tt-fg-dim)] pointer-events-none" />
          <input
            type="text"
            placeholder="Search by name or path…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full h-9 pl-9 pr-3 rounded-[var(--tt-radius)] bg-[var(--tt-panel)] border border-[var(--tt-border)] text-[13px] text-[var(--tt-fg)] placeholder:text-[var(--tt-fg-faint)] hover:border-[var(--tt-border-strong)] focus:border-[color:var(--tt-brand)]/40 focus:outline-none focus:ring-1 focus:ring-[color:var(--tt-brand)]/30 transition-colors"
          />
        </div>

        {/* Sort */}
        <div className="flex items-center rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-panel)] overflow-hidden">
          <span className="pl-3 pr-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--tt-fg-dim)]">Sort</span>
          {SORTS.map((s) => (
            <button
              key={s.key}
              onClick={() => (sortKey === s.key ? setSortDesc(!sortDesc) : setSortKey(s.key))}
              className={cn(
                "h-9 px-2.5 text-[12px] font-medium transition-colors flex items-center gap-1",
                sortKey === s.key ? "text-[var(--tt-fg)] tt-tint-1" : "text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)]",
              )}
            >
              {s.label}
              {sortKey === s.key && (
                <ArrowUpDown size={11} className={cn("transition-transform", sortDesc && "rotate-180")} />
              )}
            </button>
          ))}
        </div>

        {/* View toggle */}
        <div className="flex items-center rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-panel)] overflow-hidden">
          {[
            { v: "grid", icon: LayoutGrid, label: "Grid" },
            { v: "list", icon: ListIcon,   label: "List" },
          ].map(({ v, icon: I, label }) => (
            <button
              key={v}
              onClick={() => setView(v as ViewMode)}
              aria-label={label}
              className={cn(
                "h-9 w-9 grid place-items-center transition-colors",
                view === v ? "text-[var(--tt-brand)] tt-tint-1" : "text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)]",
              )}
            >
              <I size={14} />
            </button>
          ))}
        </div>
      </div>

      {/* Results */}
      {loading ? (
        <ProjectsLoading view={view} />
      ) : filtered.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Search size={20} />}
            title={search ? `No projects match "${search}"` : "No projects detected yet"}
            description={
              search
                ? "Try a shorter query or clear the search to see all workspaces."
                : "Once your agents log activity in any workspace, projects will appear here."
            }
          />
        </Card>
      ) : view === "grid" ? (
        <Section>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {filtered.map((p) => <ProjectCard key={p.path} project={p} />)}
          </div>
        </Section>
      ) : (
        <Card padding="none">
          <Table>
            <THead>
              <TR>
                <TH className="pl-5">Project</TH>
                <TH>Agents</TH>
                <TH className="text-right">Sessions</TH>
                <TH className="text-right">Subagents</TH>
                <TH className="text-right">Plans</TH>
                <TH className="text-right">Tokens</TH>
                <TH className="text-right pr-5">API equiv.</TH>
              </TR>
            </THead>
            <TBody>
              {filtered.map((p) => (
                <TR key={p.path} interactive>
                  <TD className="pl-5">
                    <Link href={`/projects/${encodeURIComponent(p.path)}`} className="block min-w-0">
                      <div className="font-semibold text-[var(--tt-fg)] truncate">{p.name}</div>
                      <div className="font-mono text-[11px] text-[var(--tt-fg-dim)] truncate" title={p.path}>{p.path}</div>
                    </Link>
                  </TD>
                  <TD>
                    <div className="flex items-center gap-1 flex-wrap">
                      {p.agents.slice(0, 4).map((a) => <AgentBadge key={a} agent={a} withLabel={false} />)}
                      {p.agents.length > 4 && (
                        <span className="text-[10px] text-[var(--tt-fg-dim)]">+{p.agents.length - 4}</span>
                      )}
                    </div>
                  </TD>
                  <TD className="text-right tabular text-[var(--tt-fg)] font-semibold">{p.session_count}</TD>
                  <TD className="text-right tabular text-purple-300/90">
                    {(p.configured_subagent_count ?? 0) + (p.subagent_count ?? 0)}
                  </TD>
                  <TD className="text-right tabular text-emerald-300/90">{p.plan_count || 0}</TD>
                  <TD className="text-right tabular text-[var(--tt-fg-muted)]">{formatTokens(p.tokens?.total ?? 0)}</TD>
                  <TD className="text-right pr-5 tabular text-amber-300 font-semibold">{formatCost(p.tokens?.cost ?? 0)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </Card>
      )}
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────────────
   Cards
   ────────────────────────────────────────────────────────────────────────── */

function ProjectCard({ project }: { project: Project }) {
  const subs = (project.configured_subagent_count ?? 0) + (project.subagent_count ?? 0);
  const tokens = project.tokens?.total ?? 0;
  const cost = project.tokens?.cost ?? 0;

  return (
    <Link href={`/projects/${encodeURIComponent(project.path)}`} className="block group">
      <Card interactive className="!p-0 h-full flex flex-col overflow-hidden">
        <div className="p-5 flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0">
            <div className="h-9 w-9 grid place-items-center rounded-[var(--tt-radius)] bg-[var(--tt-brand-glow)] text-[var(--tt-brand)] border border-[color:var(--tt-brand)]/20 shrink-0">
              <Folder size={16} strokeWidth={2.25} />
            </div>
            <div className="min-w-0">
              <div className="text-[14px] font-semibold tracking-[-0.01em] text-[var(--tt-fg)] truncate group-hover:text-[var(--tt-brand)] transition-colors" title={project.name}>
                {project.name}
              </div>
              <div className="font-mono text-[10px] text-[var(--tt-fg-dim)] truncate mt-0.5" title={project.path}>
                {project.path}
              </div>
            </div>
          </div>
          <ArrowRight size={14} className="text-[var(--tt-fg-dim)] group-hover:text-[var(--tt-brand)] group-hover:translate-x-0.5 transition-all shrink-0 mt-1" />
        </div>

        <div className="px-5 pb-3 flex items-center gap-1.5 flex-wrap">
          {project.agents.slice(0, 5).map((a) => {
            const meta = getAgent(a);
            const Icon = meta.icon;
            return (
              <span
                key={a}
                title={meta.label}
                className="h-6 w-6 grid place-items-center rounded-md border"
                style={{ backgroundColor: `${meta.hex}10`, borderColor: `${meta.hex}33`, color: meta.hex }}
              >
                <Icon size={12} />
              </span>
            );
          })}
          {project.agents.length > 5 && (
            <span className="text-[10px] text-[var(--tt-fg-dim)] ml-1">+{project.agents.length - 5}</span>
          )}
        </div>

        {project.mcp_tools.length > 0 && (
          <div className="px-5 pb-4 flex items-center gap-1.5 flex-wrap">
            <Wrench size={11} className="text-[var(--tt-fg-faint)]" />
            {project.mcp_tools.slice(0, 4).map((t) => (
              <Badge key={t} variant="outline" size="xs" className="font-mono normal-case">{t}</Badge>
            ))}
            {project.mcp_tools.length > 4 && (
              <span className="text-[10px] text-[var(--tt-fg-dim)]">+{project.mcp_tools.length - 4}</span>
            )}
          </div>
        )}

        <div className="mt-auto grid grid-cols-4 gap-px bg-[var(--tt-border)] border-t border-[var(--tt-border)]">
          <Stat label="Sessions" value={project.session_count} />
          <Stat label="Subs"     value={subs}      tone="purple" />
          <Stat label="Plans"    value={project.plan_count || 0} tone="emerald" />
          <Stat label="API equiv." value={formatCost(cost)} tone="amber"
                hint={tokens ? formatTokens(tokens) : undefined} />
        </div>
      </Card>
    </Link>
  );
}

function Stat({
  label, value, tone = "default", hint,
}: { label: string; value: React.ReactNode; tone?: "default" | "purple" | "emerald" | "amber"; hint?: string }) {
  const TONE: Record<string, string> = {
    default: "text-[var(--tt-fg)]",
    purple:  "text-purple-300",
    emerald: "text-emerald-300",
    amber:   "text-amber-300",
  };
  return (
    <div className="bg-[var(--tt-panel)] py-3 px-2 text-center">
      <div className={cn("tabular text-[15px] font-semibold leading-none", TONE[tone])}>{value}</div>
      <div className="mt-1.5 text-[9px] uppercase tracking-[0.16em] text-[var(--tt-fg-dim)]">
        {hint ? `${hint} · ${label}` : label}
      </div>
    </div>
  );
}

function ProjectsLoading({ view }: { view: ViewMode }) {
  if (view === "list") {
    return (
      <Card padding="md">
        <div className="space-y-3">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
        </div>
      </Card>
    );
  }
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-56 w-full" />)}
    </div>
  );
}

// formatters live in @/lib/format — imported at the top of this file.
