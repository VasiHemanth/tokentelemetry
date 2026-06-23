"use client";

import { useEffect, useState } from "react";
import {
  Settings2, Folder, Puzzle, Users, BookOpen, Terminal, Wrench, FileText,
  Globe, Package,
} from "lucide-react";

import { apiFetch } from "@/lib/api";
import {
  Card, CardHeader, CardTitle, CardEyebrow, Section, Badge, AgentBadge,
  EmptyState, Skeleton,
} from "@/components/ui";
import BudgetEditor from "@/components/budgets/BudgetEditor";
import { useProject } from "../_lib/project-context";

interface ConfigItem { name: string; agent: string; scope: "project" | "user"; description?: string; source?: string; pluginRef?: string; [k: string]: unknown }
interface SubagentItem extends ConfigItem { model?: string; tools?: string }
interface CommandItem extends ConfigItem {}
interface SkillItem extends ConfigItem {}
interface McpItem extends ConfigItem { command?: string; url?: string; type?: string }
interface PluginItem extends ConfigItem { version?: string; marketplace?: string; enabled?: boolean; components?: string[] }
interface MemoryItem extends ConfigItem { path?: string; preview?: string; truncated?: boolean }

interface ProjectConfig {
  project: string;
  skills: SkillItem[];
  mcps: McpItem[];
  memory: MemoryItem[];
  commands: CommandItem[];
  subagents: SubagentItem[];
  plugins: PluginItem[];
}

interface UsageData {
  by_skill?: Record<string, { invocations: number; session_count: number }>;
  by_mcp_server?: Record<string, { calls: number; tools: Record<string, number>; session_count: number }>;
  by_subagent_type?: Record<string, { spawns: number; tokens: number; cost: number; session_count: number }>;
}

export default function ConfigTab() {
  const { decodedPath, project } = useProject();
  const projectAgents = project?.agents ?? [];
  const [config, setConfig] = useState<ProjectConfig | null>(null);
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    apiFetch(`/config?project=${encodeURIComponent(decodedPath)}`)
      .then((r) => r.json())
      .then(setConfig)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [decodedPath]);

  // Usage overlay: cross-link recorded skill/MCP/subagent invocations from
  // session telemetry onto the inventory ("installed but never used" is itself
  // an insight). Signal currently comes from Claude Code session logs.
  useEffect(() => {
    apiFetch(`/analytics`)
      .then((r) => r.json())
      .then(setUsage)
      .catch(() => {});
  }, []);

  const skillUse = (x: ConfigItem) => {
    const m = usage?.by_skill || {};
    if (m[x.name]) return m[x.name];
    // Plugin-namespaced skills are invoked as "<plugin>:<name>".
    const plugin = x.pluginRef ? String(x.pluginRef).split("@")[0] : null;
    return plugin ? m[`${plugin}:${x.name}`] : undefined;
  };
  const mcpUse = (x: ConfigItem) => usage?.by_mcp_server?.[x.name];
  const subagentUse = (x: ConfigItem) => usage?.by_subagent_type?.[x.name];

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-20" />)}
        </div>
        <Skeleton className="h-72" />
      </div>
    );
  }
  if (!config) {
    return <Card><EmptyState icon={<Settings2 size={20} />} title="Configuration unavailable" /></Card>;
  }

  const bucket = <T extends { scope: string }>(arr: T[]) => ({
    project: arr.filter((x) => x.scope === "project"),
    user:    arr.filter((x) => x.scope === "user"),
  });
  const sb  = bucket(config.skills    ?? []);
  const mb  = bucket(config.mcps      ?? []);
  const mem = bucket(config.memory    ?? []);
  const cb  = bucket(config.commands  ?? []);
  const ag  = bucket(config.subagents ?? []);
  const pb  = bucket(config.plugins   ?? []);

  const projectHasAny = sb.project.length + mb.project.length + mem.project.length + cb.project.length + ag.project.length + pb.project.length > 0;
  const userHasAny    = sb.user.length    + mb.user.length    + mem.user.length    + cb.user.length    + ag.user.length    + pb.user.length    > 0;

  return (
    <div className="space-y-7">
      {/* Budgets — set spend limits for this project (overall + per agent) */}
      <BudgetEditor projectPath={decodedPath} agents={projectAgents} />

      {/* Summary tiles */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <Sum icon={<Puzzle size={14} />}   label="Plugins"   value={pb.project.length}  user={pb.user.length}  hex="#a78bfa" />
        <Sum icon={<Users size={14} />}    label="Subagents" value={ag.project.length}  user={ag.user.length}  hex="#c084fc" />
        <Sum icon={<BookOpen size={14} />} label="Skills"    value={sb.project.length}  user={sb.user.length}  hex="#22d3ee" />
        <Sum icon={<Terminal size={14} />} label="Commands"  value={cb.project.length}  user={cb.user.length}  hex="#34d399" />
        <Sum icon={<Wrench size={14} />}   label="MCP servers" value={mb.project.length} user={mb.user.length} hex="#34d399" />
        <Sum icon={<FileText size={14} />} label="Memory"    value={mem.project.length} user={mem.user.length} hex="#fbbf24" />
      </div>

      {/* Project scope */}
      <Section
        title={<span className="flex items-center gap-2"><Folder size={12} className="text-[var(--tt-brand)]" /> Project configuration</span>}
        actions={<Badge variant="brand" size="sm" className="font-mono normal-case">{config.project}</Badge>}
      >
        {!projectHasAny ? (
          <Card>
            <EmptyState
              icon={<Settings2 size={18} />}
              title="No project-scoped config"
              description="No plugins, skills, commands, MCPs, or memory found in this workspace."
            />
          </Card>
        ) : (
          <div className="space-y-5">
            {pb.project.length  > 0 && <Group label="Plugins"   icon={<Puzzle size={12} className="text-violet-400" />}    items={pb.project}  render={renderPlugin} />}
            {ag.project.length  > 0 && <Group label="Subagents" icon={<Users size={12} className="text-purple-400" />}     items={ag.project}  render={(x) => renderSubagent(x, subagentUse(x), usage !== null)} />}
            {sb.project.length  > 0 && <Group label="Skills"    icon={<BookOpen size={12} className="text-cyan-400" />}    items={sb.project}  render={(x) => renderSkill(x, skillUse(x), usage !== null)} />}
            {cb.project.length  > 0 && <Group label="Commands"  icon={<Terminal size={12} className="text-emerald-400" />} items={cb.project}  render={(x) => renderCommand(x, skillUse(x), usage !== null)} />}
            {mb.project.length  > 0 && <Group label="MCP servers" icon={<Wrench size={12} className="text-emerald-400" />} items={mb.project} render={(x) => renderMcp(x, mcpUse(x), usage !== null)} />}
            {mem.project.length > 0 && <Group label="Memory files" icon={<FileText size={12} className="text-amber-400" />} items={mem.project} render={renderMemory} cols={1} />}
          </div>
        )}
      </Section>

      {/* User scope (collapsed) */}
      {userHasAny && (
        <details className="group rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] overflow-hidden">
          <summary className="flex items-center justify-between gap-4 px-5 py-4 cursor-pointer hover:tt-tint-1 list-none">
            <div className="flex items-center gap-3">
              <Settings2 size={16} className="text-[var(--tt-fg-dim)] group-open:text-[var(--tt-fg)] transition-colors" />
              <div>
                <div className="text-[13px] font-semibold text-[var(--tt-fg)]">Root / user configuration</div>
                <div className="text-[11px] text-[var(--tt-fg-dim)]">Shared across all projects, all tools.</div>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-[var(--tt-fg-dim)] tabular">
              <CountChip color="#a78bfa" label="plugins"   value={pb.user.length} />
              <CountChip color="#c084fc" label="subagents" value={ag.user.length} />
              <CountChip color="#22d3ee" label="skills"    value={sb.user.length} />
              <CountChip color="#34d399" label="commands"  value={cb.user.length} />
              <CountChip color="#34d399" label="mcps"      value={mb.user.length} />
              <CountChip color="#fbbf24" label="memory"    value={mem.user.length} />
              <span className="text-[var(--tt-fg-faint)] group-open:rotate-180 transition-transform ml-1">▾</span>
            </div>
          </summary>
          <div className="px-5 py-5 border-t border-[var(--tt-border)] space-y-5">
            {pb.user.length  > 0 && <Group label="Plugins"   icon={<Puzzle size={12} className="text-violet-400" />}    items={pb.user}  render={renderPlugin} />}
            {ag.user.length  > 0 && <Group label="Subagents" icon={<Users size={12} className="text-purple-400" />}     items={ag.user}  render={(x) => renderSubagent(x, subagentUse(x), usage !== null)} />}
            {sb.user.length  > 0 && <Group label="Skills"    icon={<BookOpen size={12} className="text-cyan-400" />}    items={sb.user}  render={(x) => renderSkill(x, skillUse(x), usage !== null)} />}
            {cb.user.length  > 0 && <Group label="Commands"  icon={<Terminal size={12} className="text-emerald-400" />} items={cb.user}  render={(x) => renderCommand(x, skillUse(x), usage !== null)} />}
            {mb.user.length  > 0 && <Group label="MCP servers" icon={<Wrench size={12} className="text-emerald-400" />} items={mb.user}  render={(x) => renderMcp(x, mcpUse(x), usage !== null)} />}
            {mem.user.length > 0 && <Group label="Memory files" icon={<FileText size={12} className="text-amber-400" />} items={mem.user} render={renderMemory} cols={1} />}
          </div>
        </details>
      )}
    </div>
  );
}

/* ─────────────────── Cards ─────────────────── */

function Group({
  label, icon, items, render, cols = 3,
}: {
  label: string; icon: React.ReactNode; items: ConfigItem[];
  render: (x: ConfigItem) => React.ReactNode; cols?: 1 | 2 | 3;
}) {
  const grid = cols === 1
    ? "grid-cols-1"
    : cols === 2
    ? "grid-cols-1 md:grid-cols-2"
    : "grid-cols-1 md:grid-cols-2 lg:grid-cols-3";
  return (
    <div>
      <div className="flex items-center gap-2 mb-2.5">
        {icon}
        <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--tt-fg-muted)]">{label}</span>
        <span className="text-[10px] tabular text-[var(--tt-fg-faint)]">{items.length}</span>
      </div>
      <div className={`grid ${grid} gap-3`}>
        {items.map((x, i) => <div key={i}>{render(x)}</div>)}
      </div>
    </div>
  );
}

/* Usage overlay chip. Counts come from scanned session telemetry — the skill/
   subagent signal is recorded by Claude Code logs (other agents don't log it),
   so "no recorded use" means "not seen in recent scanned sessions", not proof
   of zero use everywhere. */
function UsageChip({ loaded, text }: { loaded: boolean; text: string | null }) {
  if (!loaded) return null;
  if (!text) {
    return (
      <div className="mt-2 text-[10px] text-[var(--tt-fg-faint)]"
           title="Not seen in recently scanned sessions (usage signal currently recorded by Claude Code logs)">
        no recorded use
      </div>
    );
  }
  return <div className="mt-2 text-[10px] tabular text-cyan-300/80">{text}</div>;
}

const sessionsLabel = (n: number) => `${n} session${n === 1 ? "" : "s"}`;

const renderSkill = (s: ConfigItem, use?: { invocations: number; session_count: number }, loaded = false) => (
  <Card padding="sm" className="!p-3.5">
    <div className="flex items-start justify-between gap-2 mb-1.5">
      <span className="text-[13px] font-semibold text-[var(--tt-fg)] truncate">{s.name}</span>
      <AgentBadge agent={s.agent} />
    </div>
    {s.description && <p className="text-[11px] text-[var(--tt-fg-muted)] leading-relaxed line-clamp-3">{String(s.description)}</p>}
    {s.pluginRef && <PluginRef ref_={String(s.pluginRef)} />}
    {s.source && (
      <div className="mt-2 text-[10px] font-mono text-[var(--tt-fg-faint)] truncate" title={String(s.source)}>
        {String(s.source).replace(/^.*\//, "")}
      </div>
    )}
    <UsageChip loaded={loaded} text={use ? `used ×${use.invocations} · ${sessionsLabel(use.session_count)}` : null} />
  </Card>
);

const renderSubagent = (a: ConfigItem, use?: { spawns: number; cost: number; session_count: number }, loaded = false) => {
  const sa = a as SubagentItem;
  return (
    <Card padding="sm" className="!p-3.5">
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <span className="flex items-center gap-1.5 text-[13px] font-semibold text-[var(--tt-fg)] truncate">
          <Users size={11} className="text-purple-400 shrink-0" />
          {sa.name}
        </span>
        <AgentBadge agent={sa.agent} />
      </div>
      {sa.description && <p className="text-[11px] text-[var(--tt-fg-muted)] leading-relaxed line-clamp-3 mb-2">{sa.description}</p>}
      <div className="flex flex-wrap items-center gap-1.5">
        {sa.model && <Badge variant="success" size="xs" className="font-mono normal-case">{sa.model}</Badge>}
        {sa.tools && (
          <Badge variant="neutral" size="xs" className="font-mono normal-case truncate max-w-full" title={sa.tools}>
            {sa.tools}
          </Badge>
        )}
        {sa.pluginRef && <PluginRef ref_={sa.pluginRef} />}
      </div>
      <UsageChip loaded={loaded} text={use ? `spawned ×${use.spawns} · ${sessionsLabel(use.session_count)} · $${use.cost.toFixed(2)}` : null} />
    </Card>
  );
};

const renderCommand = (c: ConfigItem, use?: { invocations: number; session_count: number }, loaded = false) => (
  <Card padding="sm" className="!p-3.5">
    <div className="flex items-start justify-between gap-2 mb-1.5">
      <span className="font-mono text-[13px] font-semibold text-[var(--tt-fg)] truncate">/{c.name}</span>
      <AgentBadge agent={c.agent} />
    </div>
    {c.description && <p className="text-[11px] text-[var(--tt-fg-muted)] leading-relaxed line-clamp-3">{String(c.description)}</p>}
    {c.pluginRef && <PluginRef ref_={String(c.pluginRef)} />}
    <UsageChip loaded={loaded} text={use ? `used ×${use.invocations} · ${sessionsLabel(use.session_count)}` : null} />
  </Card>
);

const renderMcp = (m: ConfigItem, use?: { calls: number; tools: Record<string, number>; session_count: number }, loaded = false) => {
  const mm = m as McpItem;
  return (
    <Card padding="sm" className="!p-3.5">
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <span className="text-[13px] font-semibold text-[var(--tt-fg)] truncate">{mm.name}</span>
        <AgentBadge agent={mm.agent} />
      </div>
      {mm.command && (
        <div className="flex items-center gap-1.5 text-[11px] font-mono text-[var(--tt-fg-muted)] bg-[var(--tt-sunken)] border border-[var(--tt-border)] rounded-md px-2 py-1 mt-1.5 truncate" title={mm.command}>
          <Package size={10} className="opacity-60 shrink-0" />
          <span className="truncate">{mm.command}</span>
        </div>
      )}
      {mm.url && (
        <div className="flex items-center gap-1.5 text-[11px] font-mono text-[var(--tt-fg-muted)] bg-[var(--tt-sunken)] border border-[var(--tt-border)] rounded-md px-2 py-1 mt-1.5 truncate" title={mm.url}>
          <Globe size={10} className="opacity-60 shrink-0" />
          <span className="truncate">{mm.url}</span>
        </div>
      )}
      {mm.type && <div className="mt-2 text-[10px] font-mono text-[var(--tt-fg-faint)] uppercase tracking-[0.16em]">{mm.type}</div>}
      {mm.pluginRef && <PluginRef ref_={mm.pluginRef} />}
      <UsageChip loaded={loaded} text={use ? `${use.calls} calls · ${Object.keys(use.tools).length} tools · ${sessionsLabel(use.session_count)}` : null} />
    </Card>
  );
};

const renderPlugin = (p: ConfigItem) => {
  const pp = p as PluginItem;
  return (
    <Card padding="sm" className="!p-3.5">
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <span className="flex items-center gap-1.5 text-[13px] font-semibold text-[var(--tt-fg)] truncate">
          <Puzzle size={11} className="text-violet-400 shrink-0" />
          {pp.name}
        </span>
        <AgentBadge agent={pp.agent} />
      </div>
      {pp.description && <p className="text-[11px] text-[var(--tt-fg-muted)] leading-relaxed line-clamp-2 mb-2">{pp.description}</p>}
      <div className="flex flex-wrap gap-1.5">
        {pp.version && <Badge variant="neutral" size="xs" className="font-mono normal-case">v{pp.version}</Badge>}
        {pp.marketplace && <Badge variant="brand" size="xs" className="font-mono normal-case">{pp.marketplace}</Badge>}
        {pp.enabled === false && <Badge variant="warn" size="xs">disabled</Badge>}
        {(pp.components ?? []).slice(0, 4).map((c, i) => (
          <Badge key={i} variant="neutral" size="xs" className="font-mono normal-case">{c}</Badge>
        ))}
      </div>
    </Card>
  );
};

const renderMemory = (m: ConfigItem) => {
  const mm = m as MemoryItem;
  return (
    <details className="rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] overflow-hidden">
      <summary className="px-4 py-3 cursor-pointer hover:tt-tint-1 flex items-center justify-between gap-3 list-none">
        <div className="flex items-center gap-2.5 min-w-0">
          <AgentBadge agent={mm.agent} />
          <span className="text-[13px] font-semibold text-[var(--tt-fg)] truncate">{mm.name}</span>
        </div>
        {mm.path && (
          <span className="text-[10px] font-mono text-[var(--tt-fg-faint)] truncate max-w-[420px]" title={mm.path}>{mm.path}</span>
        )}
      </summary>
      <pre className="text-[11px] font-mono text-[var(--tt-fg-muted)] whitespace-pre-wrap bg-[var(--tt-sunken)] border-t border-[var(--tt-border)] p-4 max-h-96 overflow-y-auto">
        {mm.preview}{mm.truncated ? "\n…(truncated)" : ""}
      </pre>
    </details>
  );
};

function PluginRef({ ref_ }: { ref_: string }) {
  return (
    <div className="mt-2 inline-flex">
      <Badge variant="brand" size="xs" className="font-mono normal-case">
        <Puzzle size={9} /> {ref_}
      </Badge>
    </div>
  );
}

function Sum({
  icon, label, value, user, hex,
}: { icon: React.ReactNode; label: string; value: number; user: number; hex: string }) {
  return (
    <Card padding="sm" className="!p-4 relative overflow-hidden">
      <span aria-hidden className="absolute left-0 top-3 bottom-3 w-[2px] rounded-r-full" style={{ backgroundColor: hex }} />
      <div className="flex items-center gap-2 text-[var(--tt-fg-dim)] mb-1.5">
        <span style={{ color: hex }}>{icon}</span>
        <span className="text-[10px] font-semibold uppercase tracking-[0.16em]">{label}</span>
      </div>
      <div className="flex items-baseline gap-2">
        <div className="tabular text-[22px] leading-none font-semibold text-[var(--tt-fg)]">{value}</div>
        <div className="text-[10px] text-[var(--tt-fg-faint)]">project</div>
      </div>
      {user > 0 && (
        <div className="text-[10px] text-[var(--tt-fg-dim)] mt-1 tabular">+{user} at user scope</div>
      )}
    </Card>
  );
}

function CountChip({ color, label, value }: { color: string; label: string; value: number }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className="font-semibold tabular" style={{ color }}>{value}</span>
      <span>{label}</span>
    </span>
  );
}
