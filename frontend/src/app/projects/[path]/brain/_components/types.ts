export interface BrainSummary {
  exists: boolean;
  kind: "plugin_wiki" | "okf_ish" | "obsidian_vault" | "markdown_wiki" | null;
  source: "default" | "registered" | "none";
  project_valid?: boolean;
  wiki_path?: string;
  page_count?: number;
  status?: "compiling" | "complete" | null;
  profile?: string | null;
  batches_done?: number | null;
  batches_total?: number | null;
  updated?: string | null;
  compiled_from_sha?: string | null;
}

export interface GraphNode {
  id: string;
  title: string;
  type: string | null;
  description: string | null;
  tags: string[];
  timestamp: string | null;
  resource: string | null;
  dir: string;
  degree: number;
  cluster: number;
}

export interface GraphEdge {
  source: string;
  target: string;
}

export interface GraphCluster {
  id: number;
  label: string;
  size: number;
}

export interface BrainGraphData {
  summary: BrainSummary;
  nodes: GraphNode[];
  edges: GraphEdge[];
  clusters: GraphCluster[];
  types: Record<string, number>;
}

export interface PageLink {
  id: string;
  title: string;
}

export interface PageDetail {
  id: string;
  title: string;
  type: string | null;
  description: string | null;
  tags: string[];
  timestamp: string | null;
  resource: string | null;
  status: string | null;
  body: string;
  outbound: PageLink[];
  inbound: PageLink[];
  staleness: { status: "fresh" | "stale" | "unknown"; reason?: string; diffstat?: string };
}

export interface WikiCandidate {
  path: string;
  kind: string;
  page_count: number;
}
