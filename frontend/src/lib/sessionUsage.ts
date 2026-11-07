// What one session actually used (skills, MCP servers, subagents) and which of
// those calls failed, read from the /sessions record. This is the per-session
// counterpart to /config, which lists what is INSTALLED for a project and says
// nothing about a given run.

export interface SessionUsageFields {
  skills_used?: { name: string; count: number; errors?: number }[];
  mcp_usage?: Record<string, Record<string, number>>;
  mcp_errors?: Record<string, Record<string, number>>;
  tool_counts?: Record<string, number>;
  tool_errors?: Record<string, number>;
  delegation?: {
    by_type?: Record<string, { count?: number; failed?: number; tool_errors?: number }>;
  } | null;
}

export interface UsageRow {
  name: string;
  plugin: string | null;
  calls: number;
  errors: number;
}

export interface McpUsageRow extends UsageRow {
  tools: { name: string; calls: number; errors: number }[];
}

export interface SubagentUsageRow extends UsageRow {
  /** Runs where every tool call errored. */
  failed: number;
}

export interface SessionUsage {
  skills: UsageRow[];
  mcp: McpUsageRow[];
  subagents: SubagentUsageRow[];
  /** Failed calls to tools that are neither MCP nor Skill (Bash, Read, ...). */
  otherToolErrors: { name: string; errors: number }[];
  totalErrors: number;
}

/** Owning Claude Code plugin of a skill, subagent type or MCP server name.
 *  Mirrors backend `_plugin_of`: "<plugin>:<name>" for skills and subagent
 *  types, "plugin_<plugin>_<server>" for MCP servers (symmetric split first,
 *  since a plugin's one server usually shares its name). */
export function pluginOf(name: string | null | undefined): string | null {
  if (!name) return null;
  if (name.startsWith("plugin_")) {
    const rest = name.slice("plugin_".length);
    const half = (rest.length - 1) / 2;
    if (rest.length % 2 === 1 && rest[half] === "_" && rest.slice(0, half) === rest.slice(half + 1)) {
      return rest.slice(0, half) || null;
    }
    return rest.split("_")[0] || null;
  }
  if (name.includes(":")) return name.split(":")[0] || null;
  return null;
}

type Ranked = { name: string; calls: number; errors: number };
const byErrorsThenCalls = (a: Ranked, b: Ranked) =>
  b.errors - a.errors || b.calls - a.calls || a.name.localeCompare(b.name);

export function sessionUsage(s: SessionUsageFields | null | undefined): SessionUsage | null {
  if (!s) return null;
  const skills: UsageRow[] = (s.skills_used ?? []).map((sk) => ({
    name: sk.name,
    plugin: pluginOf(sk.name),
    calls: sk.count,
    errors: sk.errors ?? 0,
  }));
  const mcp: McpUsageRow[] = Object.entries(s.mcp_usage ?? {}).map(([server, tools]) => {
    const errs = s.mcp_errors?.[server] ?? {};
    const toolRows = Object.entries(tools).map(([name, calls]) => ({ name, calls, errors: errs[name] ?? 0 }));
    return {
      name: server,
      plugin: pluginOf(server),
      calls: toolRows.reduce((n, t) => n + t.calls, 0),
      errors: toolRows.reduce((n, t) => n + t.errors, 0),
      tools: toolRows.sort(byErrorsThenCalls),
    };
  });
  const subagents: SubagentUsageRow[] = Object.entries(s.delegation?.by_type ?? {}).map(([type, d]) => ({
    name: type,
    plugin: pluginOf(type),
    calls: d.count ?? 0,
    errors: d.tool_errors ?? 0,
    failed: d.failed ?? 0,
  }));
  const otherToolErrors = Object.entries(s.tool_errors ?? {})
    .filter(([name]) => name !== "Skill" && !name.startsWith("mcp_") && !name.startsWith("default_api:mcp_"))
    .map(([name, errors]) => ({ name, errors }))
    .sort((a, b) => b.errors - a.errors || a.name.localeCompare(b.name));
  const totalErrors = Object.values(s.tool_errors ?? {}).reduce((n, v) => n + v, 0);
  if (!skills.length && !mcp.length && !subagents.length && !totalErrors) return null;
  return {
    skills: skills.sort(byErrorsThenCalls),
    mcp: mcp.sort(byErrorsThenCalls),
    // A run that failed outright outranks one with a few tool errors.
    subagents: subagents.sort((a, b) => b.failed - a.failed || byErrorsThenCalls(a, b)),
    otherToolErrors,
    totalErrors,
  };
}

export interface PluginUsageItem {
  kind: "mcp" | "skill" | "subagent";
  name: string;
  calls: number;
  /** Failed calls (MCP / skill) or failed runs (subagent). */
  failed: number;
}

export interface PluginUsage {
  plugin: string;
  calls: number;
  failed: number;
  items: PluginUsageItem[];
}

/** Per-plugin pass/fail for one session: every MCP tool, skill and subagent
 *  type that came from a plugin, grouped by that plugin. A subagent counts
 *  as one call per spawn and fails only when the whole run failed. */
export function pluginUsage(u: SessionUsage | null): PluginUsage[] {
  if (!u) return [];
  const groups = new Map<string, PluginUsage>();
  const add = (plugin: string | null, item: PluginUsageItem) => {
    if (!plugin) return;
    const g = groups.get(plugin) ?? { plugin, calls: 0, failed: 0, items: [] };
    g.calls += item.calls;
    g.failed += item.failed;
    g.items.push(item);
    groups.set(plugin, g);
  };
  for (const r of u.mcp) {
    for (const t of r.tools) add(r.plugin, { kind: "mcp", name: t.name, calls: t.calls, failed: t.errors });
  }
  for (const r of u.skills) add(r.plugin, { kind: "skill", name: r.name, calls: r.calls, failed: r.errors });
  for (const r of u.subagents) add(r.plugin, { kind: "subagent", name: r.name, calls: r.calls, failed: r.failed });
  return [...groups.values()]
    .map((g) => ({ ...g, items: g.items.sort((a, b) => b.failed - a.failed || b.calls - a.calls) }))
    .sort((a, b) => b.failed - a.failed || b.calls - a.calls || a.plugin.localeCompare(b.plugin));
}
