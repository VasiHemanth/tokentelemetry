/**
 * Pure helpers over a TraceSpan forest: lookups, rollups, row flattening for
 * the span table, agent activity bursts and concurrency. No React here.
 */
import type { SpanTokens, TraceSpan } from "./types";

export type TraceFilter = "all" | "agents" | "errors";

export const BURST_GAP_MS = 2 * 60 * 1000;

export interface TraceIndex {
  roots: TraceSpan[];
  all: TraceSpan[];
  byId: Map<string, TraceSpan>;
  parent: Map<string, TraceSpan | null>;
  depth: Map<string, number>;
  /** Every agent span at any depth, sorted by start. */
  agents: TraceSpan[];
  agentByChild: Map<string, TraceSpan>;
  /** childId -> notification turns started by that agent finishing. */
  reports: Map<string, TraceSpan[]>;
  /** childId -> tool spans that resumed that agent. */
  resumers: Map<string, TraceSpan[]>;
}

export function buildIndex(roots: TraceSpan[]): TraceIndex {
  const all: TraceSpan[] = [];
  const byId = new Map<string, TraceSpan>();
  const parent = new Map<string, TraceSpan | null>();
  const depth = new Map<string, number>();
  const walk = (s: TraceSpan, p: TraceSpan | null, d: number) => {
    all.push(s);
    byId.set(s.id, s);
    parent.set(s.id, p);
    depth.set(s.id, d);
    for (const c of s.children) walk(c, s, d + 1);
  };
  for (const r of roots) walk(r, null, 0);

  const agents = all.filter((s) => s.kind === "agent").sort((a, b) => a.start - b.start);
  const agentByChild = new Map<string, TraceSpan>();
  for (const a of agents) if (a.agent?.childId) agentByChild.set(a.agent.childId, a);

  const reports = new Map<string, TraceSpan[]>();
  const resumers = new Map<string, TraceSpan[]>();
  for (const s of all) {
    if (s.kind === "turn" && s.notifiedBy) pushTo(reports, s.notifiedBy, s);
    if (s.kind === "tool" && s.resumes) pushTo(resumers, s.resumes, s);
  }
  return { roots, all, byId, parent, depth, agents, agentByChild, reports, resumers };
}

function pushTo(m: Map<string, TraceSpan[]>, k: string, v: TraceSpan) {
  const list = m.get(k);
  if (list) list.push(v);
  else m.set(k, [v]);
}

export const tokenSum = (t?: SpanTokens): number => (t ? t.input + t.output + t.cacheRead + t.cacheWrite : 0);

export interface Rollup {
  tokens: number;
  llm: number;
  tools: number;
  errs: number;
  agents: number;
}

/** Subtree totals. An agent span reports its own totalTokens when set, so its children are not double counted. */
export function computeRollups(roots: TraceSpan[]): Map<string, Rollup> {
  const out = new Map<string, Rollup>();
  const visit = (s: TraceSpan): Rollup => {
    const r: Rollup = {
      tokens: s.kind === "llm" ? tokenSum(s.tokens) : 0,
      llm: s.kind === "llm" ? 1 : 0,
      tools: s.kind === "tool" ? 1 : 0,
      errs: s.error ? 1 : 0,
      agents: s.kind === "agent" ? 1 : 0,
    };
    for (const c of s.children) {
      const cr = visit(c);
      r.tokens += cr.tokens;
      r.llm += cr.llm;
      r.tools += cr.tools;
      r.errs += cr.errs;
      r.agents += cr.agents;
    }
    if (s.kind === "agent" && s.agent) {
      if (s.agent.totalTokens != null) r.tokens = s.agent.totalTokens;
      if (!s.agent.loaded && !s.children.length) {
        r.tools += s.agent.toolCalls ?? 0;
        r.errs += s.agent.toolErrors ?? 0;
      }
    }
    out.set(s.id, r);
    return r;
  };
  roots.forEach(visit);
  return out;
}

/** Work done by the agent that owns `span`, not descending into agent spans. */
export function ownWork(span: TraceSpan): { llm: number; tools: number; tokens: number } {
  const w = { llm: 0, tools: 0, tokens: 0 };
  const visit = (s: TraceSpan) => {
    if (s.kind === "llm") {
      w.llm++;
      w.tokens += tokenSum(s.tokens);
    } else if (s.kind === "tool") w.tools++;
    for (const c of s.children) if (c.kind !== "agent") visit(c);
  };
  visit(span);
  return w;
}

/** Agent spans reached from `span` without passing through another agent. */
export function directAgents(span: TraceSpan): TraceSpan[] {
  const out: TraceSpan[] = [];
  const visit = (s: TraceSpan) => {
    for (const c of s.children) {
      if (c.kind === "agent") out.push(c);
      else visit(c);
    }
  };
  visit(span);
  return out;
}

export function mainTokens(roots: TraceSpan[]): number {
  return roots.reduce((n, r) => n + ownWork(r).tokens, 0);
}

export function turnOf(index: TraceIndex, span: TraceSpan): TraceSpan {
  let p = span;
  for (let up = index.parent.get(p.id); up; up = index.parent.get(p.id)) p = up;
  return p;
}

/** Nearest agent span above `span`, or null when it belongs to the main agent. */
export function ownerAgent(index: TraceIndex, span: TraceSpan): TraceSpan | null {
  for (let p = index.parent.get(span.id); p; p = index.parent.get(p.id)) {
    if (p.kind === "agent") return p;
  }
  return null;
}

/**
 * Activity bursts of an agent as [start, end] pairs. Model calls closer than
 * gapMs merge; a longer silence leaves an idle stretch between bursts (a
 * resumed subagent). The first and last burst extend to the span's edges.
 */
export function agentBursts(span: TraceSpan, gapMs = BURST_GAP_MS): Array<[number, number]> {
  const calls = span.children
    .filter((c) => c.kind === "llm")
    .map((c): [number, number] => [c.start, c.end])
    .sort((a, b) => a[0] - b[0]);
  if (!calls.length) return [[span.start, span.end]];
  const out: Array<[number, number]> = [];
  for (const [a, b] of calls) {
    const last = out[out.length - 1];
    if (last && a - last[1] <= gapMs) last[1] = Math.max(last[1], b);
    else out.push([a, b]);
  }
  out[0][0] = Math.min(out[0][0], span.start);
  out[out.length - 1][1] = Math.max(out[out.length - 1][1], span.end);
  return out;
}

/** Most agents running at the same moment. */
export function peakConcurrency(agents: TraceSpan[]): number {
  const ev: Array<[number, number]> = [];
  for (const a of agents) {
    ev.push([a.start, 1], [Math.max(a.end, a.start + 1), -1]);
  }
  ev.sort((x, y) => x[0] - y[0] || x[1] - y[1]);
  let cur = 0;
  let peak = 0;
  for (const [, d] of ev) {
    cur += d;
    if (cur > peak) peak = cur;
  }
  return peak;
}

export function overlappingAgents(index: TraceIndex, span: TraceSpan): TraceSpan[] {
  return index.agents.filter((o) => o !== span && o.start < span.end && o.end > span.start);
}

/** Prompt turns open, plus model calls that spawned a subagent. */
export function defaultExpanded(roots: TraceSpan[]): Set<string> {
  const out = new Set<string>();
  const visit = (s: TraceSpan) => {
    if (s.kind === "turn" && s.turnKind !== "notification") out.add(s.id);
    if (s.kind === "llm" && s.children.some((c) => c.kind === "agent")) out.add(s.id);
    s.children.forEach(visit);
  };
  roots.forEach(visit);
  return out;
}

/** Every span with children, except model calls inside subagents (those make thousands of rows). */
export function expandAllIds(roots: TraceSpan[]): Set<string> {
  const out = new Set<string>();
  const visit = (s: TraceSpan, inAgent: boolean) => {
    const skip = s.kind === "llm" && inAgent;
    if (s.children.length && !skip) out.add(s.id);
    for (const c of s.children) visit(c, inAgent || s.kind === "agent");
  };
  for (const r of roots) visit(r, false);
  return out;
}

export interface Row {
  span: TraceSpan;
  depth: number;
}

export function matchesFilter(span: TraceSpan, filter: TraceFilter): boolean {
  if (filter === "agents") return span.kind === "agent";
  if (filter === "errors") return !!span.error;
  return true;
}

/**
 * Rows to render, top-down. With a filter, a span stays when it or any
 * descendant matches, and non-matching ancestors of a match are forced open so
 * the path to it is visible.
 */
export function flattenVisible(roots: TraceSpan[], expanded: ReadonlySet<string>, filter: TraceFilter): Row[] {
  const out: Row[] = [];
  if (filter === "all") {
    const walk = (s: TraceSpan, depth: number) => {
      out.push({ span: s, depth });
      if (expanded.has(s.id)) for (const c of s.children) walk(c, depth + 1);
    };
    roots.forEach((r) => walk(r, 0));
    return out;
  }
  const memo = new Map<string, boolean>();
  const hasMatch = (s: TraceSpan): boolean => {
    let v = memo.get(s.id);
    if (v === undefined) {
      v = matchesFilter(s, filter) || s.children.some(hasMatch);
      memo.set(s.id, v);
    }
    return v;
  };
  const walk = (s: TraceSpan, depth: number) => {
    if (!hasMatch(s)) return;
    out.push({ span: s, depth });
    const forced = !matchesFilter(s, filter) && s.children.some(hasMatch);
    if (expanded.has(s.id) || forced) for (const c of s.children) walk(c, depth + 1);
  };
  roots.forEach((r) => walk(r, 0));
  return out;
}

/** An agent span whose own trace has not been fetched yet and can be. */
export function isLazyAgent(span: TraceSpan, canLoad: boolean): boolean {
  return canLoad && span.kind === "agent" && span.agent?.loaded === false && span.children.length === 0;
}
