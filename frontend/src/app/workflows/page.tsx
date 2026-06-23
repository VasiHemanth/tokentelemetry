"use client";

import { useCallback, useEffect, useState } from "react";
import { formatDistanceToNow } from "date-fns";
import {
  Layers, Plus, Trash2, ChevronDown, ChevronRight, X, Coins, Hash, Boxes,
} from "lucide-react";

import { formatCost, formatTokens } from "@/lib/format";
import {
  type Workflow, WORKFLOW_COLORS,
  getWorkflows, createWorkflow, deleteWorkflow, removeSessionFromWorkflow,
} from "@/lib/workflows";
import {
  PageHeader, Section, Card, Button, EmptyState, Skeleton, AgentBadge,
} from "@/components/ui";
import { cn } from "@/lib/cn";

export default function WorkflowsPage() {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  const refresh = useCallback(() => {
    return getWorkflows()
      .then((data) => { setWorkflows(data); setError(null); })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    let cancelled = false;
    getWorkflows()
      .then((data) => { if (!cancelled) { setWorkflows(data); setError(null); } })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="px-8 py-8 max-w-[1200px] mx-auto space-y-8 pb-20">
      <PageHeader
        eyebrow="Cost legibility"
        title="Workflows"
        description="Group sessions into named tasks and read the total cost across every agent that worked on them."
        icon={<Layers size={20} strokeWidth={2.25} />}
        actions={
          <Button variant="primary" size="md" onClick={() => setShowForm((v) => !v)}>
            <Plus size={14} /> New Workflow
          </Button>
        }
      />

      {showForm && (
        <NewWorkflowForm
          onCreated={() => { setShowForm(false); refresh(); }}
          onCancel={() => setShowForm(false)}
        />
      )}

      <Section title="Your workflows">
        {loading ? (
          <div className="space-y-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-28 w-full rounded-[var(--tt-radius-lg)]" />
            ))}
          </div>
        ) : error ? (
          <Card><div className="text-[13px] text-[var(--tt-danger-fg)]">Failed to load workflows: {error}</div></Card>
        ) : workflows.length === 0 ? (
          <EmptyState
            icon={<Boxes size={20} />}
            title="No workflows yet"
            description="Create a workflow, then add sessions to it from the Dashboard using the “Add to workflow” button on each session row."
            action={
              <Button variant="primary" size="md" onClick={() => setShowForm(true)}>
                <Plus size={14} /> New Workflow
              </Button>
            }
          />
        ) : (
          <div className="space-y-4">
            {workflows.map((wf) => (
              <WorkflowCard key={wf.id} wf={wf} onChange={refresh} />
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}

function NewWorkflowForm({ onCreated, onCancel }: { onCreated: () => void; onCancel: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [color, setColor] = useState(WORKFLOW_COLORS[0]);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    if (!name.trim()) { setErr("Name is required"); return; }
    setSaving(true); setErr(null);
    try {
      await createWorkflow({ name: name.trim(), description: description.trim(), color });
      onCreated();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setSaving(false);
    }
  };

  return (
    <Card tone="raised">
      <div className="space-y-3">
        <div>
          <label className="block text-[11px] uppercase tracking-[0.16em] text-[var(--tt-fg-dim)] mb-1.5">Name</label>
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
            placeholder="Auth refactor"
            className="w-full rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-sunken)] px-3 py-2 text-[13px] text-[var(--tt-fg)] outline-none focus:border-[var(--tt-brand)]"
          />
        </div>
        <div>
          <label className="block text-[11px] uppercase tracking-[0.16em] text-[var(--tt-fg-dim)] mb-1.5">Description</label>
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Rewriting the auth middleware (optional)"
            className="w-full rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-sunken)] px-3 py-2 text-[13px] text-[var(--tt-fg)] outline-none focus:border-[var(--tt-brand)]"
          />
        </div>
        <div>
          <label className="block text-[11px] uppercase tracking-[0.16em] text-[var(--tt-fg-dim)] mb-1.5">Color</label>
          <div className="flex items-center gap-2">
            {WORKFLOW_COLORS.map((c) => (
              <button
                key={c}
                type="button"
                aria-label={`Color ${c}`}
                onClick={() => setColor(c)}
                className={cn(
                  "h-6 w-6 rounded-full transition-transform",
                  color === c ? "ring-2 ring-offset-2 ring-offset-[var(--tt-raised)] scale-110" : "hover:scale-105",
                )}
                style={{ backgroundColor: c, boxShadow: color === c ? `0 0 0 2px ${c}` : undefined }}
              />
            ))}
          </div>
        </div>
        {err && <div className="text-[12px] text-[var(--tt-danger-fg)]">{err}</div>}
        <div className="flex items-center gap-2 pt-1">
          <Button variant="primary" size="md" onClick={submit} disabled={saving}>
            {saving ? "Creating…" : "Create workflow"}
          </Button>
          <Button variant="ghost" size="md" onClick={onCancel} disabled={saving}>Cancel</Button>
        </div>
      </div>
    </Card>
  );
}

function WorkflowCard({ wf, onChange }: { wf: Workflow; onChange: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);

  const onDelete = async () => {
    if (!confirm(`Delete workflow “${wf.name}”? This removes the grouping, not the sessions.`)) return;
    setBusy(true);
    try { await deleteWorkflow(wf.id); onChange(); } finally { setBusy(false); }
  };

  const onRemoveSession = async (sid: string) => {
    setBusy(true);
    try { await removeSessionFromWorkflow(wf.id, sid); onChange(); } finally { setBusy(false); }
  };

  return (
    <Card
      padding="none"
      className="overflow-hidden border-l-2"
      style={{ borderLeftColor: wf.color }}
    >
      <div className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full shrink-0" style={{ backgroundColor: wf.color }} />
              <h3 className="text-[15px] font-semibold tracking-tight text-[var(--tt-fg)] truncate">{wf.name}</h3>
            </div>
            {wf.description && (
              <p className="mt-1 text-[13px] text-[var(--tt-fg-muted)] leading-relaxed">{wf.description}</p>
            )}
          </div>
          <Button variant="danger" size="sm" onClick={onDelete} disabled={busy} title="Delete workflow">
            <Trash2 size={13} />
          </Button>
        </div>

        {/* Stats */}
        <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-[12px]">
          <Stat icon={<Boxes size={13} />} label={`${wf.session_count} ${wf.session_count === 1 ? "session" : "sessions"}`} />
          <Stat icon={<Coins size={13} />} label={`${formatCost(wf.total_cost_usd)} total`} />
          <Stat icon={<Hash size={13} />} label={`${formatTokens(wf.total_tokens)} tokens`} />
          {wf.agent_types.length > 0 && (
            <span className="flex items-center gap-1.5 flex-wrap">
              <span className="text-[var(--tt-fg-dim)]">agents:</span>
              {wf.agent_types.map((a) => <AgentBadge key={a} agent={a} size="xs" />)}
            </span>
          )}
        </div>

        <div className="mt-3 flex items-center justify-between">
          <span className="text-[11px] text-[var(--tt-fg-dim)]">
            {wf.last_active
              ? `Last active ${formatDistanceToNow(new Date(wf.last_active * 1000), { addSuffix: true })}`
              : "No active sessions"}
          </span>
          {wf.session_count > 0 && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="flex items-center gap-1 text-[11px] text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] transition-colors"
            >
              {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
              {expanded ? "Hide sessions" : "Show sessions"}
            </button>
          )}
        </div>
      </div>

      {expanded && wf.session_ids.length > 0 && (
        <div className="border-t border-[var(--tt-border)] bg-[var(--tt-sunken)] p-4 space-y-2">
          {wf.session_ids.map((sid) => (
            <SessionPill key={sid} sessionId={sid} onRemove={() => onRemoveSession(sid)} disabled={busy} />
          ))}
        </div>
      )}
    </Card>
  );
}

function Stat({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <span className="flex items-center gap-1.5 text-[var(--tt-fg-muted)]">
      <span className="text-[var(--tt-fg-dim)]">{icon}</span>
      <span className="tabular">{label}</span>
    </span>
  );
}

/** A single session in the expanded list. Workflows store only session ids
 *  (stats are aggregated server-side and the per-session agent isn't carried
 *  here), so the pill shows the id and a remove control. */
function SessionPill({ sessionId, onRemove, disabled }: { sessionId: string; onRemove: () => void; disabled: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2 rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-panel)] px-3 py-1.5">
      <span className="font-mono text-[11px] text-[var(--tt-fg-muted)] truncate" title={sessionId}>
        {sessionId.slice(0, 28)}{sessionId.length > 28 ? "…" : ""}
      </span>
      <button
        onClick={onRemove}
        disabled={disabled}
        aria-label="Remove session from workflow"
        className="shrink-0 text-[var(--tt-fg-dim)] hover:text-[var(--tt-danger-fg)] transition-colors disabled:opacity-50"
      >
        <X size={13} />
      </button>
    </div>
  );
}
