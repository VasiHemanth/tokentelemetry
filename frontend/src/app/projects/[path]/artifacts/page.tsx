"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { format } from "date-fns";
import { Globe, ArrowUpRight, ExternalLink, FileText } from "lucide-react";

import { Card, CardTitle, AgentBadge, EmptyState } from "@/components/ui";
import { artifactUrl } from "@/lib/api";
import { useProject } from "../_lib/project-context";

/* Deliverable artifacts from sessions in this project (worktree publishes
   roll up to the repo-root card on the backend). Two kinds: "page" — hosted
   claude.ai pages from Claude Code's Artifact tool, linked externally;
   "document" — local docs like Antigravity's task/plan/walkthrough, linked
   into the session inspector and served raw via /artifacts?path=. */
export default function ArtifactsTab() {
  const pathname = usePathname();
  const { project } = useProject();
  const artifacts = project?.artifacts ?? [];

  if (artifacts.length === 0) {
    return (
      <Card>
        <EmptyState
          icon={<Globe size={20} />}
          title="No artifacts"
          description="When an agent produces a deliverable artifact — Claude Code publishing a hosted page, or Antigravity writing a task list, implementation plan, or walkthrough — it shows up here."
        />
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      {artifacts.map((a) => {
        const isPage = !!a.url;
        const sessionHref = a.session_id
          ? `/sessions/${a.session_id}?agent=${a.agent || "claude"}&tab=artifacts&from=${encodeURIComponent(pathname)}`
          : null;
        return (
          <Card key={a.url || a.path} padding="none" className="overflow-hidden">
            <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-[var(--tt-border)]">
              <div className="flex items-center gap-3 min-w-0">
                {!isPage && <FileText size={14} className="shrink-0 text-[var(--tt-fg-muted)]" />}
                <AgentBadge agent={a.agent || "claude"} />
                <CardTitle className="!text-[13px] truncate" title={a.title || a.url || a.file_name || undefined}>
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
              {isPage ? (
                <a
                  href={a.url!}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-[11px] font-mono text-[var(--tt-brand)] hover:underline break-all"
                >
                  {a.url} <ExternalLink size={11} className="shrink-0" />
                </a>
              ) : a.path && (
                <a
                  href={artifactUrl(`/artifacts?path=${encodeURIComponent(a.path)}`)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-[11px] font-mono text-[var(--tt-brand)] hover:underline"
                >
                  {a.file_name || "open file"} <ExternalLink size={11} className="shrink-0" />
                </a>
              )}
            </div>

            {sessionHref && (
              <div className="px-5 py-3 border-t border-[var(--tt-border)] bg-[var(--tt-sunken)] flex justify-end">
                <Link
                  href={sessionHref}
                  className="inline-flex items-center gap-1.5 text-[11px] font-medium text-[var(--tt-fg-muted)] hover:text-[var(--tt-brand)] transition-colors uppercase tracking-[0.16em]"
                >
                  View session <ArrowUpRight size={12} />
                </Link>
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}
