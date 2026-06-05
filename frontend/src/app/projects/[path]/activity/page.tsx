"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { format } from "date-fns";
import { Activity, ClipboardList, Cpu, Terminal } from "lucide-react";

import {
  Card, CardTitle, AgentBadge, EmptyState, Skeleton,
  Table, THead, TBody, TR, TH, TD,
} from "@/components/ui";
import { useProject } from "../_lib/project-context";
import CopilotSourceBadge from "@/components/CopilotSourceBadge";
import AntigravitySourceBadge from "@/components/AntigravitySourceBadge";

export default function ActivityTab() {
  const pathname = usePathname();
  const { sessions, loading } = useProject();

  return (
    <Card padding="none">
      <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-[var(--tt-border)]">
        <CardTitle><Activity size={14} className="text-[var(--tt-brand)]" /> Session history</CardTitle>
        <span className="text-[10px] uppercase tracking-[0.18em] text-[var(--tt-fg-dim)]">{sessions.length} sessions</span>
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
        <div className="max-h-[700px] overflow-y-auto">
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
              {sessions.map((s, i) => (
                <TR key={`${s.agent}-${s.id}-${i}`} interactive>
                  <TD className="pl-5">
                    <Link href={`/sessions/${s.id}?agent=${s.agent}&from=${encodeURIComponent(pathname)}`} className="flex items-center gap-1.5">
                      <AgentBadge agent={s.agent} />
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
