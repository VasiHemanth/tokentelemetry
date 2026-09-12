/**
 * Subagent classification, shared by the dashboard and the project pages so the
 * two can't disagree about what counts as a subagent.
 *
 * Some harnesses (Grok, Codex, OpenCode, Antigravity, Hermes) write each
 * delegated child as its OWN session file, carrying the parent's cwd. They
 * therefore land in the same project as their parent and, unfiltered, dominate
 * the activity feed — one Grok parent in `quirky-borg` has 158 children, which
 * is 158 near-identical rows for a single run. Claude Code does not do this
 * (its subagents live inside the parent transcript), so this only affects the
 * harnesses that emit child files.
 *
 * A row counts as a subagent only when its `parent_session_id` resolves to a
 * session in the SAME list. A dangling parent (pruned, or predating the store)
 * keeps the child visible, because hiding it would drop the run entirely.
 */

export interface SubagentAware {
  id: string;
  parent_session_id?: string | null;
}

export interface SubagentSplit<T> {
  /** Every row, untouched — totals and aggregates must keep reading this. */
  all: T[];
  /** Rows to render when subagents are collapsed. Preserves input order. */
  parents: T[];
  /** Rows classified as subagents, i.e. `all.length - parents.length`. */
  hiddenCount: number;
  /** Session id -> how many direct children of it are present in `all`. */
  childCounts: Map<string, number>;
}

export function splitSubagents<T extends SubagentAware>(sessions: T[]): SubagentSplit<T> {
  const ids = new Set(sessions.map((s) => s.id));
  const childCounts = new Map<string, number>();
  const parents: T[] = [];

  for (const s of sessions) {
    const pid = s.parent_session_id;
    // `pid && ids.has(pid)` is the whole rule: a child whose parent we can see.
    if (pid && ids.has(pid)) {
      childCounts.set(pid, (childCounts.get(pid) ?? 0) + 1);
    } else {
      parents.push(s);
    }
  }

  return { all: sessions, parents, hiddenCount: sessions.length - parents.length, childCounts };
}

/**
 * "268 · 43 real · 225 delegated" for a header. Returns null when nothing was
 * classified as a child, so ordinary projects keep their plain count.
 *
 * "delegated", not "subagents", on purpose: the project header already shows a
 * "Subagents" stat, and that one counts configured agent definitions on disk
 * plus in-transcript Task calls. Two different numbers under one word on the
 * same screen reads as a bug. This line counts child SESSIONS.
 */
export function subagentSummary(total: number, hidden: number): string | null {
  if (hidden <= 0) return null;
  return `${total} · ${total - hidden} real · ${hidden} delegated`;
}
