"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { format } from "date-fns";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ClipboardList, ArrowUpRight } from "lucide-react";

import { Card, CardTitle, AgentBadge, EmptyState } from "@/components/ui";
import { useProject } from "../_lib/project-context";

export default function PlansTab() {
  const pathname = usePathname();
  const { project } = useProject();
  const plans = project?.plans ?? [];

  if (plans.length === 0) {
    return (
      <Card>
        <EmptyState
          icon={<ClipboardList size={20} />}
          title="No architectural plans detected"
          description="Plans are extracted when an agent produces a structured plan (e.g. Claude's Plan mode). Run an agent in plan mode to populate this view."
        />
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      {plans.map((plan, i) => (
        <Card key={`${plan.session_id}-${i}`} padding="none" className="overflow-hidden">
          <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-[var(--tt-border)]">
            <div className="flex items-center gap-3 min-w-0">
              <AgentBadge agent={plan.agent} />
              <CardTitle className="!text-[13px]">
                Plan from session <span className="font-mono text-[var(--tt-fg-muted)] ml-1">{plan.session_id.slice(0, 8)}</span>
              </CardTitle>
            </div>
            <span className="text-[10px] uppercase tracking-[0.18em] text-[var(--tt-fg-dim)]">
              {format(new Date(plan.timestamp), "MMM d, HH:mm")}
            </span>
          </div>

          <div className="p-6 prose prose-sm max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{plan.content}</ReactMarkdown>
          </div>

          <div className="px-5 py-3 border-t border-[var(--tt-border)] bg-[var(--tt-sunken)] flex justify-end">
            <Link
              href={`/sessions/${plan.session_id}?agent=${plan.agent}&from=${encodeURIComponent(pathname)}`}
              className="inline-flex items-center gap-1.5 text-[11px] font-medium text-[var(--tt-fg-muted)] hover:text-[var(--tt-brand)] transition-colors uppercase tracking-[0.16em]"
            >
              View full session <ArrowUpRight size={12} />
            </Link>
          </div>
        </Card>
      ))}
    </div>
  );
}
