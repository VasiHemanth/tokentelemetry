"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { format } from "date-fns";
import { Activity, ClipboardList, Cpu, Terminal, Eye, EyeOff } from "lucide-react";

import {
  Card, CardTitle, AgentBadge, Button, EmptyState, Skeleton,
  Table, THead, TBody, TR, TH, TD,
} from "@/components/ui";
import { useProject } from "../_lib/project-context";
import { useScrollState } from "@/lib/useScrollState";
import { splitSubagents, subagentSummary } from "@/lib/subagents";
import { useShowSubagents } from "@/lib/subagentPref";
import { SubagentCount } from "@/components/SubagentCount";
import CopilotSourceBadge from "@/components/CopilotSourceBadge";
import AntigravitySourceBadge from "@/components/AntigravitySourceBadge";

export default function ActivityTab() {
  const pathname = usePathname();
  const { sessions, loading } = useProject();
  // Shared with the dashboard and Settings — one preference, several surfaces.
  const [showSubagents, setShowSubagents] = useShowSubagents();

  // Harnesses that write each delegated child as its own session file put those
  // children in the parent's project, so an unfiltered feed here is mostly
  // subagents (one Grok run in `quirky-borg` accounts for 158 rows). Totals on
  // the project header stay unfiltered — only this table collapses.
  const split = splitSubagents(sessions);
  const visibleSessions = showSubagents ? split.all : split.parents;
  const countLine = subagentSummary(sessions.length, split.hiddenCount);

  // Restore scroll position when data fetch is complete. The table key carries
  // the toggle state: collapsed and expanded are different-length lists, so a
  // pixel offset saved against one must never be restored into the other.
  useScrollState(`key_project_activity_page`, !loading);
  const { ref: sessionHistoryRef, onScroll: handleSessionHistoryScroll } = useScrollState(
    `key_project_activity_sessions_${showSubagents ? "all" : "parents"}`,
    !loading && sessions.length > 0,
  );

  return (
    <Card padding="none">
      <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-[var(--tt-border)]">
        <CardTitle><Activity size={14} className="text-[var(--tt-brand)]" /> Session history</CardTitle>
        <div className="flex items-center gap-3">
          {split.hiddenCount > 0 && (
            <Button
              variant="secondary"
              size="sm"
              aria-pressed={showSubagents}
              title={showSubagents ? "Collapse delegated sessions into their parent" : "List delegated sessions individually"}
              onClick={() => setShowSubagents(!showSubagents)}
            >
              {showSubagents ? <EyeOff size={12} /> : <Eye size={12} />}
              {showSubagents ? "Hide subagents" : "Show subagents"}
            </Button>
          )}
          <span className="text-[10px] uppercase tracking-[0.18em] text-[var(--tt-fg-dim)] tabular-nums">
            {countLine ?? `${sessions.length} sessions`}
          </span>
        </div>
      </div>

      {loading ? (
        <div className="p-5 space-y-3">
          {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-9 w-full" />)}
        </div>
      ) : sessions.length === 0 ? (
        <EmptyState
          icon={<Terminal size={20} />}
          title="No recorded activity"
          description="Once any agent runs in this workspace, sessions will appear here."
        />
      ) : (
        <div ref={sessionHistoryRef} onScroll={handleSessionHistoryScroll} className="max-h-[700px] overflow-y-auto">
          <Table>
            <THead>
              <TR>
                <TH className="pl-5">Agent</TH>
                <TH>Session intent</TH>
                <TH className="text-center">Insights</TH>
                <TH className="text-right pr-5">Timestamp</TH>
              </TR>
            </THead>
            <TBody>
              {visibleSessions.map((s) => (
                <TR key={`${s.agent}-${s.id}`} interactive>
                  <TD className="pl-5">
                    <Link href={`/sessions/${s.id}?agent=${s.agent}&from=${encodeURIComponent(pathname)}`} className="flex items-center gap-1.5">
                      <AgentBadge agent={s.agent} />
                      <SubagentCount count={split.childCounts.get(s.id) ?? 0} />
                      {s.agent === "copilot" && <CopilotSourceBadge source={s.copilot_source} size="xs" />}
                      {s.agent === "antigravity" && <AntigravitySourceBadge source={s.antigravity_source} size="xs" />}
                    </Link>
                  </TD>
                  <TD className="text-[var(--tt-fg)] max-w-[640px] truncate">
                    <Link href={`/sessions/${s.id}?agent=${s.agent}&from=${encodeURIComponent(pathname)}`} className="block truncate">
                      {s.display || s.text || (
                        <span className="italic text-[var(--tt-fg-faint)]">No prompt content</span>
                      )}
                    </Link>
                  </TD>
                  <TD className="text-center">
                    <div className="inline-flex items-center gap-2.5 opacity-60 group-hover:opacity-100 transition-opacity">
                      {s.has_plan && (
                        <span title="Plan detected" className="text-emerald-400"><ClipboardList size={13} /></span>
                      )}
                      {(s.mcp_tools?.length ?? 0) > 0 && (
                        <span title={`${s.mcp_tools.length} tools used`} className="text-[var(--tt-brand)]">
                          <Cpu size={13} />
                        </span>
                      )}
                    </div>
                  </TD>
                  <TD className="text-right pr-5 tabular text-[11px] text-[var(--tt-fg-muted)] group-hover:text-[var(--tt-brand)] transition-colors">
                    <Link href={`/sessions/${s.id}?agent=${s.agent}&from=${encodeURIComponent(pathname)}`} className="block">
                      <div>{format(new Date(s.timestamp), "HH:mm:ss")}</div>
                      <div className="text-[10px] uppercase tracking-wider text-[var(--tt-fg-faint)]">
                        {format(new Date(s.timestamp), "MMM d")}
                      </div>
                    </Link>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </div>
      )}
    </Card>
  );
}
