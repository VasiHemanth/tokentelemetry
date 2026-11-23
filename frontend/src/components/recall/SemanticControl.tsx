"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Sparkles, Copy, Check, Loader2 } from "lucide-react";
import { Button } from "@/components/ui";
import { cn } from "@/lib/cn";
import { embeddedWithText } from "@/lib/recallPure";
import {
  fetchRecallIndexStatus, fetchRecallSettings, putRecallSettings, semanticState, startRecallIndex,
  type RecallIndexStatus, type RecallSettings,
} from "@/lib/recall";

const POLL_MS = 2000;

/** Settings + index state for semantic search, shared with the page so results can react to it. */
export function useRecallSemantic() {
  const [settings, setSettings] = useState<RecallSettings | null>(null);
  const [index, setIndex] = useState<RecallIndexStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    const ctl = new AbortController();
    Promise.all([fetchRecallSettings(ctl.signal), fetchRecallIndexStatus(ctl.signal)])
      .then(([s, i]) => { if (alive.current) { setSettings(s); setIndex(i); } })
      .catch((e: unknown) => {
        if (ctl.signal.aborted || !alive.current) return;
        setError(e instanceof Error ? e.message : String(e));
      });
    return () => { alive.current = false; ctl.abort(); };
  }, []);

  const running = index?.state === "running";
  // Poll only while a build runs; the effect cleans up on unmount or when it stops.
  useEffect(() => {
    if (!running) return;
    const ctl = new AbortController();
    const timer = window.setInterval(() => {
      fetchRecallIndexStatus(ctl.signal)
        .then((i) => {
          if (!alive.current) return;
          setIndex(i);
          if (i.state !== "running") {
            fetchRecallSettings(ctl.signal).then((s) => { if (alive.current) setSettings(s); }).catch(() => {});
          }
        })
        .catch(() => { /* transient; next tick retries */ });
    }, POLL_MS);
    return () => { window.clearInterval(timer); ctl.abort(); };
  }, [running]);

  const setEnabled = useCallback(async (enabled: boolean) => {
    setBusy(true); setError(null);
    try { const s = await putRecallSettings({ enabled }); if (alive.current) setSettings(s); }
    catch (e) { if (alive.current) setError(e instanceof Error ? e.message : String(e)); }
    finally { if (alive.current) setBusy(false); }
  }, []);

  const build = useCallback(async (project: string | null) => {
    // The backend has no all-projects build (POST /recall/index 400s).
    if (!project) { setError("Select a project to index it."); return; }
    setBusy(true); setError(null);
    try { const i = await startRecallIndex(project); if (alive.current) setIndex(i); }
    catch (e) { if (alive.current) setError(e instanceof Error ? e.message : String(e)); }
    finally { if (alive.current) setBusy(false); }
  }, []);

  const refresh = useCallback(() => {
    fetchRecallSettings()
      .then((s) => { if (alive.current) setSettings(s); })
      .catch(() => { /* keep the last known settings */ });
  }, []);

  return { settings, setSettings, refresh, index, error, busy, setEnabled, build };
}

export type RecallSemantic = ReturnType<typeof useRecallSemantic>;

function CopyCommand({ command }: { command: string }) {
  const [done, setDone] = useState(false);
  const copy = () => {
    try {
      void navigator.clipboard.writeText(command).then(() => {
        setDone(true);
        window.setTimeout(() => setDone(false), 1500);
      });
    } catch { /* clipboard unavailable; the text is selectable */ }
  };
  return (
    <span className="inline-flex items-center gap-1.5 max-w-full">
      <code className="font-mono text-[11px] px-1.5 py-0.5 rounded bg-[var(--tt-sunken)] border border-[var(--tt-border)] select-all break-all">
        {command}
      </code>
      <button
        type="button" onClick={copy} aria-label="Copy command"
        className="p-1 rounded text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)] hover:tt-tint-2"
      >
        {done ? <Check size={12} /> : <Copy size={12} />}
      </button>
    </span>
  );
}

export function SemanticControl({ sem, project, projectName, showBuild = true }: {
  sem: RecallSemantic; project: string; projectName: string | null;
  /** The per-project index card owns building once a project is selected. */
  showBuild?: boolean;
}) {
  const { settings, index, error, busy, setEnabled, build } = sem;

  if (!settings) {
    return error ? (
      <div className="text-[12px] text-[var(--tt-danger-fg)]">Semantic search status unavailable: {error}</div>
    ) : (
      <div className="h-9 w-64 rounded-[var(--tt-radius)] tt-tint-1 animate-pulse" aria-busy />
    );
  }

  const st = semanticState(settings, index);
  const enabled = settings.semantic.enabled;
  const canBuild = enabled && settings.ollama.reachable && settings.ollama.model_installed && st.kind !== "indexing";

  let chip: { label: string; tone: "dim" | "warn" | "ok" | "busy" };
  switch (st.kind) {
    case "off": chip = { label: "Off", tone: "dim" }; break;
    case "unreachable": chip = { label: "Ollama not reachable", tone: "warn" }; break;
    case "model_missing": chip = { label: "Model missing", tone: "warn" }; break;
    case "indexing": chip = { label: `Indexing ${st.done}/${st.total}`, tone: "busy" }; break;
    case "not_indexed": chip = { label: "Not indexed", tone: "warn" }; break;
    default: chip = { label: "Ready", tone: "ok" };
  }
  const toneCls = {
    dim: "text-[var(--tt-fg-dim)] border-[var(--tt-border)]",
    warn: "text-[var(--tt-warn-fg)] border-[var(--tt-warn-bd)] bg-[var(--tt-warn-bg)]",
    ok: "text-[var(--tt-brand)] border-[color:var(--tt-brand)]/40 bg-[color:var(--tt-brand-glow)]",
    busy: "text-[var(--tt-brand)] border-[color:var(--tt-brand)]/40",
  }[chip.tone];

  const pct = st.kind === "indexing" && st.total > 0 ? Math.min(100, Math.round((st.done / st.total) * 100)) : 0;

  return (
    <div className="rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] px-4 py-3 space-y-2.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Sparkles size={14} className="text-[var(--tt-fg-dim)]" />
        <span className="text-[12px] font-semibold text-[var(--tt-fg)]">Semantic search</span>
        <span className={cn("inline-flex items-center gap-1.5 h-6 px-2 rounded-full border text-[11px] font-medium tabular", toneCls)} role="status">
          {chip.tone === "busy" && <Loader2 size={11} className="animate-spin" />}
          {chip.label}
        </span>
        <label className="ml-auto inline-flex items-center gap-2 text-[12px] text-[var(--tt-fg-muted)] cursor-pointer">
          <input
            type="checkbox" checked={enabled} disabled={busy}
            onChange={(e) => void setEnabled(e.target.checked)}
            className="accent-[var(--tt-brand)]"
          />
          Enable
        </label>
        {showBuild && canBuild && (project ? (
          <Button size="sm" disabled={busy} onClick={() => void build(project)}>
            {`Build index for ${projectName ?? "this project"}`}
          </Button>
        ) : (
          // Indexes are per project; the backend has no all-projects build.
          <span className="text-[12px] text-[var(--tt-fg-muted)]">Select a project to index it</span>
        ))}
      </div>

      {st.kind === "indexing" && (
        <div className="h-1 rounded-full tt-tint-2 overflow-hidden" aria-hidden>
          <div className="h-full bg-[var(--tt-brand)] transition-all" style={{ width: `${pct}%` }} />
        </div>
      )}

      {(st.kind === "unreachable" || st.kind === "model_missing") && (
        <div className="text-[12px] text-[var(--tt-fg-muted)] space-y-1.5">
          <p>
            {st.kind === "model_missing"
              ? `Model ${settings.semantic.model} is not installed.`
              : st.message}
          </p>
          {st.kind === "model_missing" && st.command && <CopyCommand command={st.command} />}
        </div>
      )}

      {st.kind === "ready" && (
        <p className="text-[11px] text-[var(--tt-fg-dim)] tabular">
          {settings.index.chunks.toLocaleString()} chunks from {settings.index.sessions.toLocaleString()} sessions.
          {embeddedWithText(settings.semantic)}.
        </p>
      )}
      {index?.state === "error" && index.error && (
        <p className="text-[12px] text-[var(--tt-danger-fg)]">Index build stopped: {index.error}</p>
      )}
      {error && <p className="text-[12px] text-[var(--tt-danger-fg)]">{error}</p>}
    </div>
  );
}
