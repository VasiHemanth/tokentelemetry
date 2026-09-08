// Org mode (self-hosted team roll-up) response shapes. These mirror the backend
// /org/status and /org/summary endpoints exactly; keep field names in sync with
// backend/main.py or the two sides silently drift (tsc can't see the backend).
//
// The summary arrays and totals are ALWAYS present, even when org mode is off:
// the backend returns empty totals/arrays so the frontend never branches on
// missing keys — only on `enabled`.

import { api } from "./api";

export interface OrgStatus {
  enabled: boolean;
  machines: number; // count of configured machine entries
  sessions: number; // total sessions ingested across all machines
}

export interface OrgMachineRow {
  machine: string;
  sessions: number;
  tokens: number;
  cost: number;
  last_seen: string | null; // ISO8601, or null if nothing ingested yet
}

export interface OrgAgentRow {
  agent: string;
  sessions: number;
  tokens: number;
  cost: number;
}

export interface OrgProjectRow {
  project: string;
  sessions: number;
  tokens: number;
  cost: number;
}

export interface OrgRecentSession {
  id: string;
  machine: string;
  agent: string;
  project: string;
  timestamp: string; // ISO8601
  tokens_total: number;
  cost: number | null;
}

export interface OrgSummary {
  enabled: boolean;
  totals: { sessions: number; tokens: number; cost: number };
  by_machine: OrgMachineRow[];
  by_agent: OrgAgentRow[];
  by_project: OrgProjectRow[];
  recent: OrgRecentSession[]; // newest 20
}

export function getOrgStatus(): Promise<OrgStatus> {
  return api<OrgStatus>("/org/status");
}

export function getOrgSummary(): Promise<OrgSummary> {
  return api<OrgSummary>("/org/summary");
}
