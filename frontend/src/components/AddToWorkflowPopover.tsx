"use client";

import { useEffect, useRef, useState } from "react";
import { Layers, Plus, Check, Loader2 } from "lucide-react";

import {
  type Workflow, WORKFLOW_COLORS,
  getWorkflows, createWorkflow, addSessionsToWorkflow, removeSessionFromWorkflow,
} from "@/lib/workflows";
import { cn } from "@/lib/cn";

/** Per-session "Add to workflow" control for the dashboard rows. Renders a
 *  small button that opens a popover listing workflows (checkbox = membership)
 *  plus an inline "New workflow" creator. Memberships come from the session's
 *  own workflow_ids (annotated by the backend) but we keep a local optimistic
 *  copy so toggles feel instant without a full sessions refetch. */
export default function AddToWorkflowPopover({
  sessionId,
  initialWorkflowIds = [],
}: {
  sessionId: string;
  initialWorkflowIds?: string[];
}) {
  const [open, setOpen] = useState(false);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(false);
  // Membership starts from the backend-annotated ids and is then reconciled
  // against the freshly loaded workflow list, with optimistic toggles applied
  // on top. We never sync the prop via an effect (that triggers cascading
  // renders) — the loaded list is authoritative once the popover is open.
  const [member, setMember] = useState<Set<string>>(new Set(initialWorkflowIds));
  const [pending, setPending] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  // Load workflows when the popover opens. setLoading(true) happens in the
  // open handler, not here, so the effect body never setStates synchronously.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    getWorkflows()
      .then((wf) => {
        if (cancelled) return;
        setWorkflows(wf);
        // Reconcile membership from authoritative server data for this session.
        setMember(new Set(wf.filter((w) => w.session_ids.includes(sessionId)).map((w) => w.id)));
      })
      .catch(() => { /* non-fatal — popover shows empty */ })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [open, sessionId]);

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const toggle = async (wf: Workflow) => {
    const isMember = member.has(wf.id);
    setPending(wf.id);
    try {
      if (isMember) {
        await removeSessionFromWorkflow(wf.id, sessionId);
        setMember((m) => { const n = new Set(m); n.delete(wf.id); return n; });
      } else {
        await addSessionsToWorkflow(wf.id, [sessionId]);
        setMember((m) => new Set(m).add(wf.id));
      }
    } catch { /* leave state unchanged on failure */ } finally {
      setPending(null);
    }
  };

  const create = async () => {
    const name = newName.trim();
    if (!name) return;
    setPending("__new__");
    try {
      const color = WORKFLOW_COLORS[workflows.length % WORKFLOW_COLORS.length];
      const wf = await createWorkflow({ name, color, session_ids: [sessionId] });
      setWorkflows((ws) => [wf, ...ws]);
      setMember((m) => new Set(m).add(wf.id));
      setNewName("");
      setCreating(false);
    } catch { /* non-fatal */ } finally {
      setPending(null);
    }
  };

  return (
    <div className="relative inline-block" ref={ref}>
      <button
        onClick={(e) => {
          e.preventDefault(); e.stopPropagation();
          if (!open) setLoading(true);
          setOpen((v) => !v);
        }}
        title="Add to workflow"
        aria-label="Add to workflow"
        className={cn(
          "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] transition-colors",
          member.size > 0
            ? "border-[var(--tt-brand)]/30 text-[var(--tt-brand)] bg-[color:var(--tt-brand-glow)]"
            : "border-[var(--tt-border)] text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)] hover:border-[var(--tt-border-strong)]",
        )}
      >
        <Layers size={11} />
        {member.size > 0 ? member.size : ""}
      </button>

      {open && (
        <div
          className="absolute right-0 z-[200] mt-1 w-60 rounded-[var(--tt-radius-lg)] border border-[var(--tt-border-strong)] bg-[var(--tt-panel)] shadow-[0_24px_60px_-20px_rgba(0,0,0,0.5)] p-1.5"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="px-2 py-1.5 text-[10px] uppercase tracking-[0.16em] text-[var(--tt-fg-dim)]">
            Add to workflow
          </div>

          <div className="max-h-56 overflow-y-auto">
            {loading ? (
              <div className="flex items-center gap-2 px-2 py-2 text-[12px] text-[var(--tt-fg-dim)]">
                <Loader2 size={13} className="animate-spin" /> Loading…
              </div>
            ) : workflows.length === 0 ? (
              <div className="px-2 py-2 text-[12px] text-[var(--tt-fg-dim)]">No workflows yet.</div>
            ) : (
              workflows.map((wf) => {
                const checked = member.has(wf.id);
                return (
                  <button
                    key={wf.id}
                    onClick={() => toggle(wf)}
                    disabled={pending === wf.id}
                    className="w-full flex items-center gap-2 rounded-[var(--tt-radius)] px-2 py-1.5 text-left text-[12px] text-[var(--tt-fg)] hover:tt-tint-1 transition-colors disabled:opacity-50"
                  >
                    <span
                      className={cn(
                        "grid place-items-center h-4 w-4 rounded border shrink-0",
                        checked ? "border-transparent" : "border-[var(--tt-border-strong)]",
                      )}
                      style={checked ? { backgroundColor: wf.color } : undefined}
                    >
                      {pending === wf.id
                        ? <Loader2 size={10} className="animate-spin text-[var(--tt-fg-dim)]" />
                        : checked ? <Check size={11} className="text-white" /> : null}
                    </span>
                    <span className="h-2 w-2 rounded-full shrink-0" style={{ backgroundColor: wf.color }} />
                    <span className="truncate">{wf.name}</span>
                  </button>
                );
              })
            )}
          </div>

          <div className="mt-1 border-t border-[var(--tt-border)] pt-1">
            {creating ? (
              <div className="flex items-center gap-1.5 px-1.5 py-1">
                <input
                  autoFocus
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") create(); if (e.key === "Escape") setCreating(false); }}
                  placeholder="Workflow name"
                  className="flex-1 min-w-0 rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-sunken)] px-2 py-1 text-[12px] text-[var(--tt-fg)] outline-none focus:border-[var(--tt-brand)]"
                />
                <button
                  onClick={create}
                  disabled={pending === "__new__" || !newName.trim()}
                  className="shrink-0 rounded-[var(--tt-radius)] bg-[var(--tt-brand-strong)] px-2 py-1 text-[11px] text-white disabled:opacity-50"
                >
                  {pending === "__new__" ? <Loader2 size={12} className="animate-spin" /> : "Add"}
                </button>
              </div>
            ) : (
              <button
                onClick={() => setCreating(true)}
                className="w-full flex items-center gap-2 rounded-[var(--tt-radius)] px-2 py-1.5 text-left text-[12px] text-[var(--tt-fg-muted)] hover:tt-tint-1 hover:text-[var(--tt-fg)] transition-colors"
              >
                <Plus size={13} /> New workflow
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
