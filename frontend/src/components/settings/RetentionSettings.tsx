"use client";

import { useEffect, useState } from "react";
import { Archive, Trash2, Loader2 } from "lucide-react";
import { cn } from "@/lib/cn";
import { CardTitle } from "@/components/ui";
import {
  getRetention, setArchive, deleteTranscripts,
  type RetentionState, type AgentRetention,
} from "@/lib/retention";

function fmtBytes(n: number): string {
  if (!n) return "0 B";
  const u = ["B", "KB", "MB", "GB"];
  let i = 0; let v = n;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${u[i]}`;
}

function retentionLabel(a: AgentRetention): string {
  if (a.effective_days == null) return "No automatic cleanup";
  const src = a.detected_override != null ? " (your setting)" : "";
  return `${a.effective_days} days, then auto-deleted${src}`;
}

function Toggle({ on, busy, disabled, onClick, label }: {
  on: boolean; busy: boolean; disabled?: boolean; onClick: () => void; label: string;
}) {
  return (
    <button
      onClick={onClick}
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={busy || disabled}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border transition-colors mt-0.5 border-[var(--tt-border)]",
        on ? "tt-tint-1" : "",
        busy || disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer",
      )}
    >
      <span className={cn(
        "absolute h-3.5 w-3.5 rounded-full transition-transform",
        on ? "translate-x-[18px] bg-[var(--tt-brand)]" : "translate-x-0.5 bg-[var(--tt-fg-muted)]",
      )} />
    </button>
  );
}

export function RetentionSettings() {
  const [state, setState] = useState<RetentionState | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getRetention().then(s => { if (!cancelled) setState(s); }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  if (!state) return null;

  const refresh = () => getRetention().then(setState).catch(() => {});

  const onToggle = async (agent: string, next: boolean) => {
    setBusy(agent);
    try { await setArchive(agent, next); await refresh(); }
    finally { setBusy(null); }
  };

  const onDelete = async (agent: string) => {
    setBusy(`del:${agent}`);
    try { await deleteTranscripts(agent); await refresh(); }
    finally { setBusy(null); }
  };

  const agents = Object.entries(state.agents);

  return (
    <div className="space-y-3">
      <p className="text-[12px] text-[var(--tt-fg-dim)] max-w-[640px]">
        Coding agents prune their own session transcripts on a schedule, after which they vanish from
        analytics. TokenTelemetry always keeps a tiny <span className="text-[var(--tt-fg)]">core summary</span> of
        every session (tokens, cost, model — used for history & charts). For agents below you can also
        keep the <span className="text-[var(--tt-fg)]">full transcript</span> so it survives past the agent&apos;s
        own cleanup. Deleting archived transcripts frees space but <span className="text-[var(--tt-fg)]">keeps the
        core stats</span> — your history stays intact.
      </p>

      {agents.map(([id, a]) => {
        const st = state.storage.by_agent[id];
        const tbytes = st?.transcript_bytes ?? 0;
        return (
          <div
            key={id}
            className="flex items-start justify-between gap-4 rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-sunken)] px-4 py-3"
          >
            <div className="min-w-0">
              <CardTitle className="text-[13px] mb-0.5">{a.label}</CardTitle>
              <p className="text-[11px] text-[var(--tt-fg-dim)]">
                Default retention: <span className="text-[var(--tt-fg-muted)]">{retentionLabel(a)}</span>
                {a.settings_hint && <span className="text-[var(--tt-fg-dim)]"> · {a.settings_hint}</span>}
              </p>
              <p className="text-[11px] text-[var(--tt-fg-dim)] mt-0.5">{a.note}</p>
              {st && (
                <p className="text-[10px] text-[var(--tt-fg-dim)] mt-1 tabular">
                  {st.sessions} sessions kept · {st.transcripts} transcripts ({fmtBytes(tbytes)}) · {st.summaries} summaries
                </p>
              )}
            </div>

            <div className="flex items-center gap-3 shrink-0">
              {a.archivable && tbytes > 0 && (
                <button
                  onClick={() => onDelete(id)}
                  disabled={busy === `del:${id}`}
                  className="inline-flex items-center gap-1 text-[11px] text-[var(--tt-fg-dim)] hover:text-[var(--tt-danger)] transition-colors disabled:opacity-50"
                  title="Delete archived transcripts (keeps core stats)"
                >
                  {busy === `del:${id}` ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                  Free space
                </button>
              )}
              <div className="flex items-center gap-1.5" title={a.archivable ? "Keep full transcripts in TokenTelemetry" : "Archiving not available for this agent yet"}>
                <Archive size={12} className="text-[var(--tt-fg-dim)]" />
                <Toggle
                  on={a.archive_enabled}
                  busy={busy === id}
                  disabled={!a.archivable}
                  onClick={() => onToggle(id, !a.archive_enabled)}
                  label={`Keep full transcripts for ${a.label}`}
                />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
