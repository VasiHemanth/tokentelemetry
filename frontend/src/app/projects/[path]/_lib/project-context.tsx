"use client";

import { createContext, useContext } from "react";

export interface PlanSnippet {
  session_id: string;
  agent: string;
  timestamp: string;
  content: string;
}

export interface SessionRow {
  id: string;
  agent: string;
  project: string;
  timestamp: string;
  display?: string;
  text?: string;
  mcp_tools: string[];
  subagents: string[];
  has_plan: boolean;
  copilot_source?: string;
  antigravity_source?: string;
  tokens?: { input: number; output: number; cached: number; total: number };
}

export interface ProjectData {
  name: string;
  path: string;
  session_count: number;
  agents: string[];
  mcp_tools: string[];
  subagent_count: number;
  configured_subagent_count?: number;
  plan_count: number;
  plans: PlanSnippet[];
  tokens?: { input: number; output: number; cached: number; total: number };
}

interface ProjectCtx {
  decodedPath: string;
  projectName: string;
  project: ProjectData | undefined;
  sessions: SessionRow[];
  loading: boolean;
}

const Ctx = createContext<ProjectCtx | null>(null);

export function ProjectProvider({ value, children }: { value: ProjectCtx; children: React.ReactNode }) {
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useProject(): ProjectCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useProject must be used inside <ProjectProvider>");
  return v;
}
