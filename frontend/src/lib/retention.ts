import { api } from "@/lib/api";

/** One agent's transcript-retention story + TT's durable-archive opt-in. */
export interface AgentRetention {
  label: string;
  /** Documented auto-cleanup window in days, or null if the agent never prunes. */
  default_days: number | null;
  /** The user's real configured window (e.g. Claude's cleanupPeriodDays), if read. */
  detected_override: number | null;
  /** Window actually in effect (override ?? default). */
  effective_days: number | null;
  configurable: boolean;
  settings_hint: string | null;
  note: string;
  /** Whether TT can archive this agent's transcripts (single-file transcript). */
  archivable: boolean;
  /** Whether the user opted into TT keeping full transcripts for this agent. */
  archive_enabled: boolean;
}

export interface RetentionStorage {
  total_sessions: number;
  transcript_bytes: number;
  by_agent: Record<
    string,
    { sessions: number; transcripts: number; transcript_bytes: number; summaries: number }
  >;
}

export interface RetentionState {
  agents: Record<string, AgentRetention>;
  storage: RetentionStorage;
  coverage: {
    earliest: string | null;
    total_sessions: number;
    by_agent: Record<string, { present: number; pruned: number; summarized: number }>;
  };
}

export function getRetention(): Promise<RetentionState> {
  return api<RetentionState>("/config/retention");
}

export function setArchive(agent: string, enabled: boolean): Promise<{ ok: boolean }> {
  return api("/config/retention", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agent, enabled }),
  });
}

export function deleteTranscripts(agent?: string): Promise<{ ok: boolean; deleted: number; storage: RetentionStorage }> {
  const q = agent ? `?agent=${encodeURIComponent(agent)}` : "";
  return api(`/history/transcripts${q}`, { method: "DELETE" });
}
