import { api } from "@/lib/api";

/** A named grouping of sessions into a task, with aggregated stats computed
 *  server-side by joining session_ids against the live session list. */
export interface Workflow {
  id: string;
  name: string;
  description?: string;
  color: string;
  session_ids: string[];
  session_count: number;
  total_cost_usd: number;
  total_tokens: number;
  agent_types: string[];
  created_at: number;
  last_active?: number;
}

/** Preset colors shown as circles in the create form. */
export const WORKFLOW_COLORS = [
  "#6366f1", // indigo
  "#22c55e", // green
  "#f97316", // orange
  "#ec4899", // pink
  "#06b6d4", // cyan
  "#eab308", // amber
];

const jsonInit = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const getWorkflows = () => api<Workflow[]>("/workflows");

export const createWorkflow = (data: Partial<Workflow>) =>
  api<Workflow>("/workflows", jsonInit("POST", data));

export const updateWorkflow = (wfId: string, data: Partial<Workflow>) =>
  api<Workflow>(`/workflows/${wfId}`, jsonInit("PUT", data));

export const addSessionsToWorkflow = (wfId: string, sessionIds: string[]) =>
  api<Workflow>(`/workflows/${wfId}/sessions`, jsonInit("POST", { session_ids: sessionIds }));

export const removeSessionFromWorkflow = (wfId: string, sessionId: string) =>
  api<Workflow>(`/workflows/${wfId}/sessions/${sessionId}`, { method: "DELETE" });

export const deleteWorkflow = (wfId: string) =>
  api<{ ok: boolean }>(`/workflows/${wfId}`, { method: "DELETE" });
