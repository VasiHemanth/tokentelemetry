import { AlertTriangle, Info } from "lucide-react";
import { Button } from "@/components/ui";
import type { RecallCapability } from "@/lib/recall";

function isRemoteView(): boolean {
  if (typeof window === "undefined") return false;
  return !["localhost", "127.0.0.1", "[::1]", "::1"].includes(window.location.hostname);
}

/** Reasons and fixes from the capability check. Renders nothing when the machine is ready. */
export function CapabilityNote({ cap, onIndexAnyway, busy }: {
  cap: RecallCapability | null; onIndexAnyway?: () => void; busy?: boolean;
}) {
  if (!cap || cap.status === "ready") return null;
  const host = typeof cap.platform?.host === "string" ? cap.platform.host : "";
  const remote = isRemoteView() && host;
  const blocked = cap.status === "blocked";
  const heading = cap.provider === "api"
    ? blocked ? "The embedding API could not be reached or used" : "Indexing through the embedding API will be slow"
    : blocked
    ? "This machine cannot run local embeddings right now"
    : cap.status === "slow"
      ? "Local embeddings will be slow on this machine"
      : "Indexing speed is unmeasured";
  const Icon = blocked ? AlertTriangle : Info;
  const tone = blocked
    ? "border-[var(--tt-danger-bd)] bg-[var(--tt-danger-bg)] text-[var(--tt-danger-fg)]"
    : "border-[var(--tt-warn-bd)] bg-[var(--tt-warn-bg)] text-[var(--tt-warn-fg)]";
  return (
    <div role="status" className={`flex items-start gap-3 rounded-[var(--tt-radius)] border px-3 py-2.5 text-[12px] ${tone}`}>
      <Icon size={14} className="mt-0.5 shrink-0" />
      <div className="flex-1 min-w-0 space-y-1.5">
        <p className="font-medium">
          {heading}{remote ? <> (checked on <span className="font-mono">{host}</span>, where the backend runs)</> : null}
        </p>
        {cap.reasons.length > 0 ? (
          <ul className="space-y-1">
            {cap.reasons.map((r) => (
              <li key={r.code}>
                <span>{r.text}</span>{" "}
                <span className="opacity-90">{r.fix}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p>Use Embedding setup to check indexing speed. You can also start indexing now.</p>
        )}
        {cap.estimate && (
          <p className="tabular">Estimated time: {cap.estimate.label} for {cap.estimate.chunks.toLocaleString()} chunks.</p>
        )}
      </div>
      {cap.status === "slow" && onIndexAnyway && (
        <Button size="sm" onClick={onIndexAnyway} disabled={busy}>Index anyway</Button>
      )}
    </div>
  );
}
