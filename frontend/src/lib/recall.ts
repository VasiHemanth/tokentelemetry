import { api } from "@/lib/api";

// Types mirror docs/design/cross-harness-recall.md. Keep them in step with it.

export interface RecallProjectRef {
  key: string;
  name: string;
}

export interface RecallProject extends RecallProjectRef {
  agents: string[];
  session_count: number;
  cost: number;
  last_ts: string | null;
}

export interface RecallProjectsResponse {
  projects: RecallProject[];
}

export interface RecallSession {
  agent: string;
  id: string;
  project_key: string | null;
  project: string | null;
  title: string;
  model: string | null;
  start_ts: string | null;
  last_ts: string | null;
  tokens: number;
  cost: number | null;
  source_present: boolean;
}

export interface RecallSessionsResponse {
  project: RecallProjectRef | null;
  sessions: RecallSession[];
  total: number;
}

export type RecallChunkKind = "user" | "assistant" | "tool" | "result";

export interface RecallHit {
  agent: string;
  id: string;
  project: string | null;
  title: string;
  model: string | null;
  last_ts: string | null;
  cost: number | null;
  turn: number;
  kind: RecallChunkKind;
  snippet: string;
  score: number;
  source: "live" | "archive";
}

export interface RecallCoverage {
  candidates: number;
  sessions_scanned: number;
  sessions_skipped: number;
  skipped_reason: "max_sessions" | "timeout" | null;
  unreadable: number;
  truncated: number;
  timed_out: boolean;
  agents_scanned: string[];
}

export interface RecallSearchResponse {
  query: string;
  project: RecallProjectRef | null;
  hits: RecallHit[];
  by_agent: Record<string, number>;
  coverage: RecallCoverage;
}

export interface RecallSearchParams {
  q: string;
  project?: string | null;
  agents?: string[];
  limit?: number;
  maxSessions?: number;
}

export const RECALL_DEFAULT_MAX_SESSIONS = 60;
export const RECALL_WIDE_MAX_SESSIONS = 300;

function qs(params: Record<string, string | number | undefined | null>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") u.set(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
}

export function fetchRecallProjects(): Promise<RecallProjectsResponse> {
  return api<RecallProjectsResponse>("/recall/projects");
}

export function recallSessionsPath(project: string | null, agents: string[], limit = 30): string {
  return `/recall/sessions${qs({
    project,
    agent: agents.length ? agents.join(",") : undefined,
    limit,
  })}`;
}

export function fetchRecallSearch(p: RecallSearchParams, signal?: AbortSignal): Promise<RecallSearchResponse> {
  return api<RecallSearchResponse>(
    `/recall/search${qs({
      q: p.q,
      project: p.project,
      agent: p.agents && p.agents.length ? p.agents.join(",") : undefined,
      limit: p.limit,
      max_sessions: p.maxSessions,
    })}`,
    { signal },
  );
}

/** Split a query into highlight needles: quoted phrases whole, other words alone. */
export function queryNeedles(q: string): string[] {
  const out: string[] = [];
  const re = /"([^"]+)"|(\S+)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(q)) !== null) {
    const t = (m[1] ?? m[2] ?? "").trim();
    if (t.length >= 2) out.push(t.toLowerCase());
  }
  return Array.from(new Set(out));
}

/** Split text into alternating plain / matched segments for React rendering. */
export function highlightSegments(text: string, needles: string[]): { text: string; hit: boolean }[] {
  if (!needles.length) return [{ text, hit: false }];
  const pattern = needles
    .slice()
    .sort((a, b) => b.length - a.length)
    .map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join("|");
  const parts = text.split(new RegExp(`(${pattern})`, "gi"));
  return parts.filter((p) => p !== "").map((p) => ({
    text: p,
    hit: needles.includes(p.toLowerCase()),
  }));
}

/** Local-time date + time, e.g. "Nov 17, 2026, 1:30 PM". Empty for missing/invalid. */
export function formatLocalDateTime(ts: string | null | undefined): string {
  if (!ts) return "";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}

function dayKeyOf(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** Local day key (YYYY-MM-DD) built from local components, never toISOString(). */
export function localDayKey(ts: string | null | undefined): string {
  if (!ts) return "";
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? "" : dayKeyOf(d);
}

/** Heading for a local-day group: Today / Yesterday / "Mon, Nov 17, 2026". */
export function localDayLabel(ts: string | null | undefined): string {
  const key = localDayKey(ts);
  if (!key) return "Undated";
  const now = new Date();
  if (key === dayKeyOf(now)) return "Today";
  if (key === dayKeyOf(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1))) return "Yesterday";
  return new Date(ts as string).toLocaleDateString(undefined, {
    weekday: "short", year: "numeric", month: "short", day: "numeric",
  });
}

export function recallSessionHref(agent: string, id: string): string {
  return `/sessions/${encodeURIComponent(id)}?agent=${encodeURIComponent(agent)}&from=${encodeURIComponent("/recall")}`;
}
