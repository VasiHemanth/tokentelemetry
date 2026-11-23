import Link from "next/link";
import { AgentBadge, Badge, Button } from "@/components/ui";
import { recallSessionHref, type RecallHit } from "@/lib/recall";
import { DocTypeIcon, docTypeMeta } from "./docTypes";
import { Highlight } from "./Highlight";
import { RecallImage, type OpenDoc } from "./DocumentDrawer";

/** One non-session search hit: skill, command, agent, artifact, markdown, MCP or image. */
export function DocHitCard({ hit, needles, project, onOpen }: {
  hit: RecallHit; needles: string[]; project: string; onOpen: (d: OpenDoc) => void;
}) {
  const type = hit.doc_type ?? "markdown";
  const meta = docTypeMeta(type);
  const docId = hit.doc_id ?? "";
  const isImage = type === "image";
  return (
    <div className="rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] p-4 space-y-2.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 min-w-0">
        <Badge variant="outline"><DocTypeIcon type={type} size={11} />{meta.label}</Badge>
        <AgentBadge agent={hit.agent} />
        <span className="min-w-0 flex-1 basis-48 truncate text-[13px] font-semibold text-[var(--tt-fg)]" title={hit.title}>
          {hit.title || "(untitled)"}
        </span>
        {hit.match && hit.match !== "keyword" && (
          <Badge variant="brand" title="Matched by meaning">{hit.match}</Badge>
        )}
      </div>
      {hit.path && <p className="font-mono text-[11px] text-[var(--tt-fg-dim)] break-all">{hit.path}</p>}
      {isImage && docId && (
        <RecallImage docId={docId} project={project} alt={hit.title || "Indexed image"} />
      )}
      {hit.snippet && (
        <p className="text-[12.5px] leading-relaxed text-[var(--tt-fg-muted)] whitespace-pre-wrap break-words">
          <Highlight text={hit.snippet} needles={needles} />
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3">
        {docId && (
          <Button
            size="sm" variant="secondary"
            onClick={() => onOpen({ docId, title: hit.title, type, path: hit.path })}
          >
            {isImage ? "Open image" : "Open text"}
          </Button>
        )}
        {hit.session_id && (
          <Link
            href={recallSessionHref(hit.agent, hit.session_id)}
            className="text-[12px] text-[var(--tt-brand)] hover:underline"
          >
            From session
          </Link>
        )}
      </div>
    </div>
  );
}
