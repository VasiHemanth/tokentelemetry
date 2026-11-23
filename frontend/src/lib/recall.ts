import { api, apiFetch, artifactUrl } from "@/lib/api";
import type { SummaryErrorInfo } from "@/lib/summarizer";

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
  match?: RecallMatch;
  /** v3: absent or "session" for chat hits. */
  doc_type?: RecallDocType;
  doc_id?: string;
  /** Display path with `~`, for file documents. */
  path?: string;
  /** Images that came from a session link back to it. */
  session_id?: string;
}

export type RecallMode = "keyword" | "semantic" | "hybrid";
export type RecallMatch = "keyword" | "semantic" | "both";

export interface RecallSemanticCoverage {
  mode: RecallMode;
  model: string;
  indexed_sessions: number;
  unindexed_sessions: number;
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
  semantic?: RecallSemanticCoverage;
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
  mode?: RecallMode | null;
  types?: RecallDocType[];
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
      mode: p.mode,
      types: p.types && p.types.length ? p.types.join(",") : undefined,
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

// ---- v2: semantic settings, index, Ask agent (docs/design/cross-harness-recall-v2.md) ----

export interface RecallSettings {
  semantic: {
    enabled: boolean; model: string; ollama_url: string; default_mode?: RecallMode; dims?: number;
    // v3 (docs/design/cross-harness-recall-v3.md section 1). Optional so v2 backends still type-check.
    provider?: "ollama" | "api";
    ollama?: { url: string; model: string };
    api?: { format: ApiFormat; endpoint: string; model: string; api_key_set?: boolean };
    api_key_set?: boolean;
    images?: boolean;
  };
  ollama: { reachable: boolean; version: string | null; model_installed: boolean; error: string | null };
  index: { chunks: number; sessions: number; model: string | null; bytes: number; updated_at: string | null };
}

export interface RecallIndexStatus {
  run: string | null;
  state: "idle" | "running" | "done" | "error";
  project: RecallProjectRef | null;
  sessions_total: number;
  sessions_done: number;
  sessions_skipped: number;
  chunks_embedded: number;
  chunks_per_sec: number;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
}

const JSON_HEADERS = { "Content-Type": "application/json" };

export function fetchRecallSettings(signal?: AbortSignal): Promise<RecallSettings> {
  return api<RecallSettings>("/recall/settings", { signal });
}

export async function putRecallSettings(semantic: RecallSettingsPatch): Promise<RecallSettings> {
  const res = await apiFetch("/recall/settings", {
    method: "PUT", headers: JSON_HEADERS, body: JSON.stringify({ semantic }),
  });
  if (!res.ok) throw new Error(await errorDetail(res));
  return res.json() as Promise<RecallSettings>;
}

export function fetchRecallIndexStatus(signal?: AbortSignal): Promise<RecallIndexStatus> {
  return api<RecallIndexStatus>("/recall/index/status", { signal });
}

/** Start an index build. A 409 means one is already running; its status comes back as the body. */
export async function startRecallIndex(project: string | null): Promise<RecallIndexStatus> {
  const res = await apiFetch("/recall/index", {
    method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ project }),
  });
  if (res.ok || res.status === 409) {
    try { return (await res.json()) as RecallIndexStatus; } catch { /* fall through */ }
  }
  throw new Error(await errorDetail(res));
}

async function errorDetail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    const d = body?.detail ?? body?.message;
    if (typeof d === "string") return d;
    if (d && typeof d.message === "string") return d.message;
  } catch { /* not json */ }
  return `${res.status} ${res.statusText}`;
}

/** PUT body for `semantic`. `api.api_key` is write-only: the backend never returns it. */
export interface RecallSettingsPatch {
  enabled?: boolean;
  model?: string;
  ollama_url?: string;
  default_mode?: RecallMode;
  provider?: "ollama" | "api";
  ollama?: { url?: string; model?: string };
  api?: { format?: ApiFormat; endpoint?: string; model?: string; api_key?: string };
  dims?: number;
  images?: boolean;
}

export type RecallSemanticState =
  | { kind: "off" }
  | { kind: "unreachable"; message: string }
  | { kind: "model_missing"; message: string; command: string | null }
  | { kind: "indexing"; done: number; total: number }
  | { kind: "not_indexed" }
  | { kind: "ready"; chunks: number };

/** Collapse settings plus index status into the single chip the UI shows. */
export function semanticState(s: RecallSettings, idx: RecallIndexStatus | null): RecallSemanticState {
  if (!s.semantic.enabled) return { kind: "off" };
  if (!s.ollama.reachable) {
    return { kind: "unreachable", message: s.ollama.error || "Ollama is not reachable." };
  }
  if (!s.ollama.model_installed) {
    const m = (s.ollama.error ?? "").match(/Run:\s*(.+)$/);
    return {
      kind: "model_missing",
      message: s.ollama.error || `Model ${s.semantic.model} is not installed.`,
      command: m ? m[1].trim() : `ollama pull ${s.semantic.model}`,
    };
  }
  if (idx && idx.state === "running") {
    return { kind: "indexing", done: idx.sessions_done + idx.sessions_skipped, total: idx.sessions_total };
  }
  if (s.index.chunks === 0) return { kind: "not_indexed" };
  return { kind: "ready", chunks: s.index.chunks };
}

export type AskEvent =
  | { type: "status"; summarizer: string; mode: RecallMode; project: RecallProjectRef | null }
  | { type: "step"; n: number; thought?: string; action: string; args: Record<string, unknown> }
  | { type: "observation"; n: number; summary: string; sessions?: string[] }
  | {
      type: "answer"; text: string; citations: AskCitation[]; steps: number; elapsed_s: number;
    }
  | { type: "error"; error_info: SummaryErrorInfo };

export interface AskCitation {
  label: string;
  agent: string;
  /** Session id, or the document id for D labels when `doc_id` is absent. */
  id: string;
  doc_id?: string;
  doc_type?: RecallDocType;
  path?: string;
  title: string;
  last_ts: string | null;
  turn?: number;
}

export interface RecallConversationSummary {
  id: string;
  title: string;
  project: string | null;
  project_name: string | null;
  agents: string[];
  updated_at: string;
}

export interface RecallConversation extends RecallConversationSummary {
  turns: {
    id: number;
    question: string;
    answer: Extract<AskEvent, { type: "answer" }> | null;
  }[];
}

export function fetchRecallConversation(id: string, signal?: AbortSignal): Promise<RecallConversation> {
  return api(`/recall/conversations/${encodeURIComponent(id)}`, { signal });
}

export async function deleteRecallConversation(id: string): Promise<void> {
  const res = await apiFetch(`/recall/conversations/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await errorDetail(res));
}

export class AskHttpError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

/** POST /recall/ask and yield NDJSON events as they arrive. Partial lines are buffered. */
export async function* streamRecallAsk(
  body: { question: string; project: string | null; agent: string | null; conversation_id?: string },
  signal: AbortSignal,
): AsyncGenerator<AskEvent> {
  const res = await apiFetch("/recall/ask", {
    method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body), signal,
  });
  if (!res.ok) throw new AskHttpError(res.status, await errorDetail(res));
  if (!res.body) throw new Error("The server returned no body.");
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  const parse = (line: string): AskEvent | null => {
    const t = line.trim();
    if (!t) return null;
    try { return JSON.parse(t) as AskEvent; } catch { return null; }
  };
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let nl: number;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const ev = parse(buf.slice(0, nl));
        buf = buf.slice(nl + 1);
        if (ev) yield ev;
      }
    }
    buf += dec.decode();
    const last = parse(buf);
    if (last) yield last;
  } finally {
    reader.cancel().catch(() => {});
  }
}

const MONTH_DAY = { month: "short", day: "numeric" } as const;

/** One compact line per agent step, e.g. Searching "x" or Reading Codex session "t" · Mar 17. */
export function describeStep(
  ev: Extract<AskEvent, { type: "step" }>,
  titleFor?: (agent: string, id: string) => { title: string; ts: string | null } | null,
  agentLabel: (a: string) => string = (a) => a,
): string {
  const a = ev.args ?? {};
  if (ev.action === "search") {
    const q = typeof a.query === "string" ? a.query : "";
    return `Searching "${q}"`;
  }
  if (ev.action === "read_session") {
    const agent = typeof a.agent === "string" ? a.agent : "";
    const sid = typeof a.session_id === "string" ? a.session_id : "";
    const info = titleFor?.(agent, sid) ?? null;
    const who = agent ? `${agentLabel(agent)} session` : "session";
    const title = info?.title ? ` "${info.title}"` : sid ? ` ${sid.slice(0, 8)}` : "";
    const when = info?.ts ? new Date(info.ts) : null;
    const date = when && !Number.isNaN(when.getTime()) ? ` · ${when.toLocaleDateString(undefined, MONTH_DAY)}` : "";
    return `Reading ${who}${title}${date}`;
  }
  if (ev.action === "read_document") {
    // doc_id is "<type>:<agent>:<scope>:<key>", e.g. "skill:claude:user:bug-audit".
    const id = typeof a.doc_id === "string" ? a.doc_id : "";
    const [type = "", agent = "", , ...rest] = id.split(":");
    const key = rest.join(":");
    const name = key.split("/").filter(Boolean).pop() || key || id;
    const kind = type === "markdown" ? "file" : type === "mcp" ? "MCP server" : type || "document";
    return `Reading ${agent ? `${agentLabel(agent)} ` : ""}${kind} "${name}"`;
  }
  return ev.action === "answer" ? "Writing the answer" : ev.action;
}

// ---- v3: project knowledge index (docs/design/cross-harness-recall-v3.md) ----

export type RecallDocType = "session" | "image" | "skill" | "command" | "agent" | "artifact" | "markdown" | "mcp";
export const RECALL_DOC_TYPES: RecallDocType[] =
  ["session", "image", "skill", "command", "agent", "artifact", "markdown", "mcp"];
export type ApiFormat = "openai" | "gemini" | "voyage";
export type TypeCounts = Partial<Record<RecallDocType, number>>;

export type DeltaState = "never_indexed" | "up_to_date" | "stale" | "model_changed" | "unavailable";

export interface RecallDelta {
  state: DeltaState;
  last_indexed_at?: string | null;
  lock?: { model: string; provider: string } | null;
  new?: TypeCounts;
  changed?: TypeCounts;
  removed?: TypeCounts;
  new_chunks_estimate?: number;
  estimate_seconds?: number | null;
}

export interface CapabilityReason { code: string; text: string; fix: string }
export interface RecallCapability {
  provider: "ollama" | "api";
  status: "ready" | "slow" | "blocked" | "unknown";
  platform?: { host?: string; [k: string]: unknown };
  memory?: { total: number | null; available: number | null; needed: number };
  disk?: { free: number | null; needed: number };
  ollama?: { reachable?: boolean; version?: string | null; too_old?: boolean; model_installed?: boolean };
  estimate: { seconds: number; label: string; chunks: number } | null;
  reasons: CapabilityReason[];
}

export function fetchRecallDelta(project: string, signal?: AbortSignal): Promise<RecallDelta> {
  return api<RecallDelta>(`/recall/index/delta${qs({ project })}`, { signal });
}

export function fetchRecallCapability(project: string | null, signal?: AbortSignal, sampleProject = false): Promise<RecallCapability> {
  return api<RecallCapability>(`/recall/capability${qs({ project, sample_project: sampleProject ? "true" : undefined })}`, { signal });
}

/** POST /recall/index. A 409 means a run is already going; that is not an error for the caller. */
export async function startRecallIndexRun(
  project: string, full: boolean,
): Promise<{ started: boolean; project: string | null; run: string | null }> {
  const res = await apiFetch("/recall/index", {
    method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ project, full }),
  });
  if (res.ok || res.status === 409) {
    const status: RecallIndexStatus = await res.json();
    return { started: res.ok, project: status.project?.key ?? null, run: status.run };
  }
  throw new Error(await errorDetail(res));
}

/** Read an NDJSON response body, yielding one parsed object per line. Partial lines are buffered. */
export async function* readNdjson<T>(res: Response): AsyncGenerator<T> {
  if (!res.body) throw new Error("The server returned no body.");
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  const parse = (line: string): T | null => {
    const t = line.trim();
    if (!t) return null;
    try { return JSON.parse(t) as T; } catch { return null; }
  };
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let nl: number;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const ev = parse(buf.slice(0, nl));
        buf = buf.slice(nl + 1);
        if (ev) yield ev;
      }
    }
    buf += dec.decode();
    const last = parse(buf);
    if (last) yield last;
  } finally {
    reader.cancel().catch(() => {});
  }
}

export type PullEvent =
  | { status: string; completed?: number; total?: number; percent?: number; type?: undefined }
  | { type: "error"; message?: string; fix?: string };

/** POST /recall/setup/pull. Only call from an explicit user click. */
export async function* streamModelPull(signal: AbortSignal): AsyncGenerator<PullEvent> {
  const res = await apiFetch("/recall/setup/pull", { method: "POST", headers: JSON_HEADERS, body: "{}", signal });
  if (!res.ok) throw new Error(await errorDetail(res));
  yield* readNdjson<PullEvent>(res);
}

export interface IndexStartEvent {
  seq: number; type: "start";
  project: RecallProjectRef | null;
  totals: { documents: number; by_type?: TypeCounts };
}
export interface RecallMapPoint {
  doc_id: string; doc_type: RecallDocType; agent: string; title: string; xy: [number, number];
}

export function fetchRecallMap(project: string, signal?: AbortSignal): Promise<{ points: RecallMapPoint[] }> {
  return api(`/recall/index/map${qs({ project })}`, { signal });
}

export interface IndexDocEvent extends Omit<RecallMapPoint, "xy"> {
  seq: number; type: "doc"; chunks: number; reused: number; xy: [number, number] | null;
}
export interface IndexVectorEvent {
  seq: number; type: "vector"; doc_id: string; doc_type: RecallDocType;
  preview: number[]; xy: [number, number];
}
export interface IndexProgress {
  documents_done: number; chunks_embedded: number; chunks_reused: number; tokens: number; per_sec: number;
  by_type: Record<string, number>; by_agent: Record<string, number>;
}
export type IndexProgressEvent = { seq: number; type: "progress" } & IndexProgress;
export interface IndexDoneEvent { seq: number; type: "done"; elapsed_s: number; summary?: Record<string, unknown> }
export interface IndexErrorEvent { seq: number; type: "error"; message: string; fix?: string }
export type IndexEvent =
  | IndexStartEvent | IndexDocEvent | IndexVectorEvent | IndexProgressEvent | IndexDoneEvent | IndexErrorEvent;

/** One connection to /recall/index/events. The caller reconnects with the last seq on a drop. */
export async function* streamIndexEvents(runId: string, since: number, signal: AbortSignal): AsyncGenerator<IndexEvent> {
  const res = await apiFetch(`/recall/index/events${qs({ run_id: runId, since })}`, { signal });
  if (!res.ok) throw new Error(await errorDetail(res));
  yield* readNdjson<IndexEvent>(res);
}

export interface RecallDocumentText {
  type?: "text";
  doc_id?: string;
  title?: string;
  path?: string;
  chunks?: string[];
  text?: string;
  next?: number | null;
  total?: number;
}
export interface RecallDocumentImage { type: "image"; url: string }
export type RecallDocumentResponse = RecallDocumentText | RecallDocumentImage;

export function recallDocumentPath(docId: string, project: string): string {
  return `/recall/document/${encodeURIComponent(docId)}${qs({ project })}`;
}

export function fetchRecallDocument(docId: string, project: string, signal?: AbortSignal): Promise<RecallDocumentResponse> {
  return api<RecallDocumentResponse>(recallDocumentPath(docId, project), { signal });
}

/** Image bytes URL carrying the access token, for <img src>. The project is required server side. */
export function recallImageUrl(docId: string, project: string): string {
  return artifactUrl(`/recall/document/${encodeURIComponent(docId)}/image${qs({ project })}`);
}

/** Preselect target: the Recall page for a project (key or path). */
export function recallProjectHref(project: string): string {
  return `/recall${qs({ project })}`;
}

export function effectiveModelName(s: RecallSettings | null): string {
  if (!s) return "the new model";
  const sem = s.semantic;
  if (sem.provider === "api" && sem.api?.model) return sem.api.model;
  return sem.ollama?.model ?? sem.model ?? "the new model";
}

export function formatEstimate(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "";
  if (seconds < 90) return `~${Math.max(1, Math.round(seconds))} s`;
  return `~${Math.round(seconds / 60)} min`;
}

export function formatShortDate(ts: string | null | undefined): string {
  if (!ts) return "";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
