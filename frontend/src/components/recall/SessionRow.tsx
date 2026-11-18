import Link from "next/link";
import { AgentBadge, Badge } from "@/components/ui";
import { formatCost } from "@/lib/format";
import { formatLocalDateTime, recallSessionHref } from "@/lib/recall";
import { Highlight } from "./Highlight";

interface SessionHead {
  agent: string;
  id: string;
  title: string;
  model: string | null;
  cost: number | null;
  ts: string | null;
  project?: string | null;
}

export function SessionHeadLine({ s, showProject }: { s: SessionHead; showProject?: boolean }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 min-w-0">
      <AgentBadge agent={s.agent} />
      <Link
        href={recallSessionHref(s.agent, s.id)}
        className="min-w-0 flex-1 basis-48 truncate text-[13px] font-semibold text-[var(--tt-fg)] hover:text-[var(--tt-brand)] transition-colors"
        title={s.title}
      >
        {s.title || "(untitled session)"}
      </Link>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[var(--tt-fg-dim)] tabular">
        {showProject && s.project && <span className="text-[var(--tt-fg-muted)]">{s.project}</span>}
        {s.model && <span className="font-mono truncate max-w-[180px]">{s.model}</span>}
        {s.cost != null && <span>{formatCost(s.cost)}</span>}
        {s.ts && <span>{formatLocalDateTime(s.ts)}</span>}
      </div>
    </div>
  );
}

export interface HitGroup {
  agent: string;
  id: string;
  title: string;
  model: string | null;
  cost: number | null;
  last_ts: string | null;
  project: string | null;
  hits: { turn: number; kind: string; snippet: string; source: "live" | "archive" }[];
}

export function HitGroupCard({ g, needles, showProject }: { g: HitGroup; needles: string[]; showProject: boolean }) {
  return (
    <div className="rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] p-4 space-y-3">
      <SessionHeadLine
        s={{ agent: g.agent, id: g.id, title: g.title, model: g.model, cost: g.cost, ts: g.last_ts, project: g.project }}
        showProject={showProject}
      />
      <ul className="space-y-2">
        {g.hits.map((h, i) => (
          <li
            key={`${h.turn}-${i}`}
            className="rounded-[var(--tt-radius)] bg-[var(--tt-sunken)] border border-[var(--tt-border)] px-3 py-2"
          >
            <div className="flex items-center gap-2 mb-1">
              <span className="font-mono text-[11px] text-[var(--tt-fg-dim)]">[turn {h.turn}]</span>
              <Badge variant="outline">{h.kind}</Badge>
              {h.source === "archive" && <Badge variant="neutral">archived</Badge>}
            </div>
            <p className="text-[12.5px] leading-relaxed text-[var(--tt-fg-muted)] whitespace-pre-wrap break-words">
              <Highlight text={h.snippet} needles={needles} />
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}
