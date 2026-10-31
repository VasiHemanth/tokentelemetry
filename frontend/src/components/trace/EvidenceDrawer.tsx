"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";

export default function EvidenceDrawer({ open, onClose, children }: { open: boolean; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    else if (!open && dialog.open) dialog.close();
  }, [open]);
  return <dialog ref={ref} aria-labelledby="evidence-title" onClose={onClose} onClick={e => { if (e.target === e.currentTarget) onClose(); }} className="fixed inset-y-0 left-auto right-0 m-0 h-dvh max-h-dvh w-full max-w-xl border-l border-[var(--tt-border-strong)] bg-[var(--tt-panel)] p-0 text-[var(--tt-fg)] shadow-xl backdrop:bg-black/50">
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 items-center justify-between border-b border-[var(--tt-border)] px-5 py-4"><h2 id="evidence-title" className="text-sm font-medium">Recorded evidence</h2><button type="button" autoFocus onClick={onClose} aria-label="Close evidence" className="rounded p-1.5 text-[var(--tt-fg-muted)] hover:bg-[var(--tt-raised)]"><X size={18} /></button></div>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-5 scrollbar-thin">{open && children}</div>
    </div>
  </dialog>;
}
