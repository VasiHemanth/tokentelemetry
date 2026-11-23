"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, X } from "lucide-react";
import { fetchRecallDocument, recallImageUrl, type RecallDocumentResponse, type RecallDocType } from "@/lib/recall";
import { DocTypeIcon, docTypeMeta } from "./docTypes";

export interface OpenDoc {
  docId: string;
  title: string;
  type: RecallDocType | string;
  path?: string;
}

/** Thumbnail of an indexed image, loaded through the token-aware image route. */
export function RecallImage({ docId, project, alt, className }: {
  docId: string; project: string; alt: string; className?: string;
}) {
  const [failed, setFailed] = useState(false);
  if (!project) return <span className="text-[11px] text-[var(--tt-fg-dim)]">Select a project to preview this image.</span>;
  if (failed) return <span className="text-[11px] text-[var(--tt-fg-dim)]">Image unavailable.</span>;
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={recallImageUrl(docId, project)}
      alt={alt}
      loading="lazy"
      onError={() => setFailed(true)}
      className={className ?? "max-h-40 max-w-full rounded-[var(--tt-radius)] border border-[var(--tt-border)] object-contain"}
    />
  );
}

/** Side drawer with the redacted text of a non-session document, or the image itself. */
export function DocumentDrawer({ doc, project, onClose }: {
  doc: OpenDoc | null; project: string; onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [state, setState] = useState<{ loading: boolean; error: string | null; data: RecallDocumentResponse | null }>(
    { loading: false, error: null, data: null },
  );

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (doc && !d.open) d.showModal();
    else if (!doc && d.open) d.close();
  }, [doc]);

  const docId = doc?.docId;
  const isImage = doc?.type === "image";
  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect */
    if (!docId || isImage) { setState({ loading: false, error: null, data: null }); return; }
    if (!project) { setState({ loading: false, error: "Select a project to open this document.", data: null }); return; }
    setState({ loading: true, error: null, data: null });
    /* eslint-enable react-hooks/set-state-in-effect */
    const ctl = new AbortController();
    fetchRecallDocument(docId, project, ctl.signal)
      .then((data) => setState({ loading: false, error: null, data }))
      .catch((e: unknown) => {
        if (ctl.signal.aborted) return;
        setState({ loading: false, error: e instanceof Error ? e.message : String(e), data: null });
      });
    return () => ctl.abort();
  }, [docId, isImage, project]);

  const meta = docTypeMeta(doc?.type);
  const text = state.data && state.data.type !== "image"
    ? (state.data.chunks ? state.data.chunks.join("\n\n") : state.data.text ?? "")
    : "";

  return (
    <dialog
      ref={ref}
      aria-labelledby="recall-doc-title"
      onClose={onClose}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      className="fixed inset-y-0 left-auto right-0 m-0 h-dvh max-h-dvh w-full max-w-xl border-l border-[var(--tt-border-strong)] bg-[var(--tt-panel)] p-0 text-[var(--tt-fg)] shadow-xl backdrop:bg-black/50"
    >
      <div className="flex h-full flex-col">
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-[var(--tt-border)] px-5 py-4">
          <div className="min-w-0 space-y-1">
            <h2 id="recall-doc-title" className="flex items-center gap-2 text-sm font-medium">
              <DocTypeIcon type={doc?.type} size={14} />
              <span className="truncate">{doc?.title || meta.label}</span>
            </h2>
            {doc?.path && <p className="font-mono text-[11px] text-[var(--tt-fg-dim)] break-all">{doc.path}</p>}
          </div>
          <button
            type="button" autoFocus onClick={onClose} aria-label="Close document"
            className="rounded p-1.5 text-[var(--tt-fg-muted)] hover:bg-[var(--tt-raised)]"
          >
            <X size={18} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-5 scrollbar-thin space-y-3">
          {doc && isImage && (
            <RecallImage docId={doc.docId} project={project} alt={doc.title || "Indexed image"} className="max-w-full rounded-[var(--tt-radius)] border border-[var(--tt-border)]" />
          )}
          {state.loading && (
            <div className="flex items-center gap-2 text-[12px] text-[var(--tt-fg-dim)]" role="status">
              <Loader2 size={13} className="animate-spin" /> Loading
            </div>
          )}
          {state.error && <p className="text-[12px] text-[var(--tt-danger-fg)]">{state.error}</p>}
          {text && (
            <>
              <pre className="whitespace-pre-wrap break-words font-mono text-[12px] leading-relaxed text-[var(--tt-fg-muted)]">{text}</pre>
              <p className="text-[11px] text-[var(--tt-fg-dim)]">Secrets are redacted in this view.</p>
            </>
          )}
        </div>
      </div>
    </dialog>
  );
}
