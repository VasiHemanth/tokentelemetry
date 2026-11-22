"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, Brain, Settings2 } from "lucide-react";
import { Button, Card, CardTitle } from "@/components/ui";
import { useResource } from "@/lib/api";
import {
  formatShortDate, recallProjectHref, type RecallDelta,
} from "@/lib/recall";
import { staleSummary } from "./DeltaBanner";
import { ProjectKnowledge } from "./ProjectKnowledge";
import { useRecallSemantic } from "./SemanticControl";

function describe(d: RecallDelta): string {
  switch (d.state) {
    case "never_indexed": return "Not indexed yet. Index it to search skills, commands, plans and images by meaning.";
    case "stale": return staleSummary(d);
    case "model_changed": return `Indexed with ${d.lock?.model ?? "another model"}. Re-index to use the current model.`;
    case "up_to_date": return `Indexed ${formatShortDate(d.last_indexed_at)}${d.lock?.model ? ` with ${d.lock.model}` : ""}.`;
    default: return "Indexing is not available for this project right now.";
  }
}

/** Index overview and controls on the project activity page. */
export function ProjectKnowledgeCard({ project }: { project: string }) {
  const [expanded, setExpanded] = useState(false);
  const path = project ? `/recall/index/delta?project=${encodeURIComponent(project)}` : null;
  const { data, loading, error, refetch } = useResource<RecallDelta>(path);
  return (
    <Card padding="sm" className="mb-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <CardTitle><Brain size={14} className="text-[var(--tt-brand)]" /> Project knowledge</CardTitle>
        <p className="flex-1 min-w-[220px] text-[12px] text-[var(--tt-fg-muted)]">
          {loading && !data ? "Checking the index" : error || !data ? "Index status unavailable." : describe(data)}
        </p>
        <Button size="sm" variant="ghost" aria-expanded={expanded} onClick={() => {
          if (expanded) refetch();
          setExpanded(!expanded);
        }}>
          <Settings2 size={12} /> {expanded ? "Hide indexing controls" : "Manage index"}
        </Button>
        <Link
          href={recallProjectHref(project)}
          className="inline-flex items-center gap-1.5 text-[12px] font-medium text-[var(--tt-brand)] hover:underline"
        >
          Open in Recall <ArrowRight size={12} />
        </Link>
      </div>
      {expanded && <div className="mt-3"><ProjectIndexControls key={project} project={project} /></div>}
    </Card>
  );
}

function ProjectIndexControls({ project }: { project: string }) {
  const sem = useRecallSemantic();
  return <ProjectKnowledge project={project} projectName={null} sem={sem} />;
}
