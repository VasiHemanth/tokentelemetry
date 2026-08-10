export type BaselineState = "learning" | "normal" | "unusual" | "extreme";

export interface PersonalBaseline {
  state: BaselineState;
  sample_count: number;
  typical: number | null;
  range_low: number | null;
  range_high: number | null;
  ratio_to_typical: number | null;
}

export interface HostImpactPoint {
  timestamp: number;
  memory_available_bytes: number | null;
  wired_bytes: number | null;
  agent_rss_bytes: number;
  active_agent_count: number;
  process_count: number;
}

export interface HostImpactHealth {
  current: HostImpactPoint & {
    memory_total_bytes: number;
    agents: string[];
  };
  series: HostImpactPoint[];
  baseline: {
    agent_rss_bytes: PersonalBaseline;
    memory_available_bytes: PersonalBaseline;
    comparison: string;
    scope: string;
  };
  collector: {
    kind: string;
    sampling: string;
    network: string;
  };
}

export function formatBytes(value: number | null | undefined): string {
  if (value === null || value === undefined || value <= 0) return "Not available";
  const mib = value / (1024 * 1024);
  return mib >= 1024 ? `${(mib / 1024).toFixed(1)} GB` : `${Math.round(mib)} MB`;
}
