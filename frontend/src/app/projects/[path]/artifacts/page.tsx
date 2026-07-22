"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { format } from "date-fns";
import { Globe, ArrowUpRight, ExternalLink } from "lucide-react";

import { Card, CardTitle, AgentBadge, EmptyState } from "@/components/ui";
import { useProject } from "../_lib/project-context";

/* Published artifacts: hosted claude.ai pages the agent created with the
   Artifact tool during sessions in this project (worktree publishes roll up
   to the repo-root card on the backend). */
export default function ArtifactsTab() {
  const pathname = usePathname();
  const { project } = useProject();
  const artifacts = project?.artifacts ?? [];

  if (artifacts.length === 0) {
    return (
      <Card>
        <EmptyState
          icon={<Globe size={20} />}
          title="No published artifacts"
          description="When Claude Code publishes an artifact (a hosted claude.ai page) during a session in this project, it shows up here with a link."
        />
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      {artifacts.map((a) => (
        <Card key={a.url} padding="none" className="overflow-hidden">
          <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-[var(--tt-border)]">
            <div className="flex items-center gap-3 min-w-0">
              {a.favicon && <span className="text-base leading-none shrink-0">{a.favicon}</span>}
              <AgentBadge agent={a.agent || "claude"} />
              <CardTitle className="!text-[13px] truncate" title={a.title || a.url}>
                {a.title || a.file_name || "Untitled artifact"}
              </CardTitle>
            </div>
            {a.timestamp && (
              <span className="text-[10px] uppercase tracking-[0.18em] text-[var(--tt-fg-dim)] shrink-0">
                {format(new Date(a.timestamp), "MMM d, HH:mm")}
              </span>
            )}
          </div>

          <div className="px-5 py-4 space-y-2">
            {a.description && (
              <p className="text-[12px] text-[var(--tt-fg-muted)] leading-relaxed">{a.description}</p>
            )}
            <a
              href={a.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-[11px] font-mono text-[var(--tt-brand)] hover:underline break-all"
            >
              {a.url} <ExternalLink size={11} className="shrink-0" />
            </a>
          </div>

          {a.session_id && (
            <div className="px-5 py-3 border-t border-[var(--tt-border)] bg-[var(--tt-sunken)] flex justify-end">
              <Link
                href={`/sessions/${a.session_id}?agent=${a.agent || "claude"}&from=${encodeURIComponent(pathname)}`}
                className="inline-flex items-center gap-1.5 text-[11px] font-medium text-[var(--tt-fg-muted)] hover:text-[var(--tt-brand)] transition-colors uppercase tracking-[0.16em]"
              >
                View session <ArrowUpRight size={12} />
              </Link>
            </div>
          )}
        </Card>
      ))}
    </div>
  );
}
