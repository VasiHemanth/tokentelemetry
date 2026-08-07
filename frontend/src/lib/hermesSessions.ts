export interface HermesSession {
  id: string;
  agent: "hermes";
  project: string;
  timestamp: string;
  display?: string;
  text?: string;
  model?: string;
  source_subtype?: string;
  cost?: number;
  cost_anomaly?: boolean;
  tokens?: {
    input: number;
    output: number;
    cached: number;
    reasoning?: number;
    total: number;
  };
}

export type HermesSessionSort = "newest" | "oldest" | "cost" | "tokens";

export interface HermesSessionPage {
  sessions: HermesSession[];
  pagination: {
    page: number;
    page_size: number;
    total: number;
    total_pages: number;
  };
}

export interface HermesSessionQuery {
  page?: number;
  pageSize?: number;
  search?: string;
  project?: string;
  source?: string;
  model?: string;
  sort?: HermesSessionSort;
}

export function buildHermesSessionsPath(query: HermesSessionQuery): string {
  const params = new URLSearchParams();
  const page = query.page ?? 1;
  const pageSize = query.pageSize ?? 50;

  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  if (query.search?.trim()) params.set("search", query.search.trim());
  if (query.project) params.set("project", query.project);
  if (query.source) params.set("source", query.source);
  if (query.model) params.set("model", query.model);
  if (query.sort && query.sort !== "newest") {
    params.set("sort", query.sort === "cost" ? "cost_desc" : query.sort === "tokens" ? "tokens_desc" : query.sort);
  }

  return `/hermes/sessions?${params.toString()}`;
}

export function formatHermesProject(project: string): string {
  if (!project || project === "unknown") return "No project";
  const parts = project.split(/[\\/]/).filter(Boolean);
  return parts.at(-1) || project;
}
