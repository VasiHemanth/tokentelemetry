/**
 * Types for GET /agents/{agent}/panel — the per-agent harness view.
 *
 * The backend returns a uniform document whatever the agent is, so one renderer
 * draws all of them and adding an agent is backend-only work. `kind` selects the
 * renderer; the rest of a section is data for it.
 *
 * Three states are deliberately distinct and must stay that way in the UI:
 *   - not installed          → `installed: false`, tile stays inert
 *   - installed, no panel yet → `installed: false, planned: true`
 *   - installed, zero rows    → a section with `empty_reason`
 * Collapsing the third into "hide the section" would teach the user the feature
 * doesn't exist, when in fact they simply haven't used it.
 */

export type SectionKind =
  | "schedules" | "jobs" | "quota" | "meter" | "permissions" | "fields"
  | "todos" | "checkpoints" | "plans" | "subagents" | "tree" | "tools"
  | "chips" | "models" | "memory" | "table" | "disk";

export type Severity = "ok" | "warn" | "crit";

export interface PanelField {
  label: string;
  value: string | number | boolean | null;
  severity?: Severity;
  hint?: string;
}

export interface PanelMeter {
  label: string;
  /** 0–100, already clamped by the backend. */
  pct: number;
  detail?: string;
  resets_at?: string | null;
  severity?: Severity;
}

export interface PanelTreeNode {
  label: string;
  status?: string;
  children?: { label: string; status?: string }[];
}

export interface PanelSection {
  kind: SectionKind;
  title: string;
  /** Where the data came from, shown verbatim so a user can go look. */
  source: string;
  columns?: string[];
  rows?: (string | number | boolean | null)[][];
  fields?: PanelField[];
  meters?: PanelMeter[];
  tree?: PanelTreeNode[];
  /** Headline number for the card (e.g. "2 active"), not always rows.length. */
  count?: number;
  /** Rows that exist on disk. Larger than rows.length means the table is capped. */
  total?: number;
  severity?: Severity;
  note?: string;
  /** Set when the store exists but holds nothing yet. */
  empty_reason?: string;
}

export interface PanelUnavailable {
  kind: string;
  reason: string;
}

export interface PanelDiskPart {
  label: string;
  bytes: number;
}

export interface PanelDisk {
  total_bytes: number;
  total_human: string;
  parts?: PanelDiskPart[];
  /** false when the directory walk hit its cap — the total is a floor. */
  complete?: boolean;
  reclaimable_bytes?: number | null;
  reclaimable_note?: string | null;
}

export interface AgentPanel {
  agent: string;
  installed: boolean;
  /** True when TokenTelemetry supports the agent but no extractor exists yet. */
  planned?: boolean;
  root?: string;
  version?: string | null;
  last_active?: string | null;
  file_count?: number | null;
  disk?: PanelDisk | null;
  sections: PanelSection[];
  not_available: PanelUnavailable[];
}

/** Section count per agent key, from GET /agents/panels. */
export type PanelSummary = Record<string, number>;

const BYTE_UNITS = ["B", "KB", "MB", "GB", "TB"];

export function humanBytes(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "—";
  let v = n;
  for (let i = 0; i < BYTE_UNITS.length; i++) {
    if (Math.abs(v) < 1024 || i === BYTE_UNITS.length - 1) {
      return i <= 1 ? `${Math.round(v)} ${BYTE_UNITS[i]}` : `${v.toFixed(1)} ${BYTE_UNITS[i]}`;
    }
    v /= 1024;
  }
  return `${v.toFixed(1)} TB`;
}

/**
 * Render a cell without lying about it.
 *
 * Large integers get thousands separators; booleans become Yes/—; null becomes
 * an em dash rather than "null". Timestamps are left to the caller, which knows
 * whether a column is a date.
 */
export function cellText(v: string | number | boolean | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? "Yes" : "—";
  if (typeof v === "number") return Number.isInteger(v) ? v.toLocaleString() : String(v);
  return v;
}

/** True when a column holds ISO timestamps we should render as relative time. */
export function isDateColumn(name: string): boolean {
  return /^(when|updated|started|finished|last run|last used|last write|created)$/i.test(name);
}

/** True when a column is numeric and should be right-aligned with tabular figures. */
export function isNumericColumn(name: string): boolean {
  return /^(tokens|in|out|cache rd|reasoning|aiu|ttft|tok\/s|uses|files|snapshots|agents|tool calls|spawns|sessions)$/i.test(name);
}
