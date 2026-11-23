"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Settings2 } from "lucide-react";
import { Button } from "@/components/ui";
import {
  effectiveModelName, fetchRecallCapability, fetchRecallProjects, fetchRecallDelta, fetchRecallIndexStatus, startRecallIndexRun,
  type RecallCapability, type RecallDelta,
} from "@/lib/recall";
import { resolveRecallProject, sameRecallProject } from "@/lib/recallPure";
import type { RecallSemantic } from "./SemanticControl";
import { CapabilityNote } from "./CapabilityNote";
import { DeltaBanner } from "./DeltaBanner";
import { EmbedNote } from "./EmbedNote";
import { IndexingTheater } from "./IndexingTheater";
import { SetupCard } from "./SetupCard";

/** Per-project index panel on the Recall page: delta banner, setup, capability note, live indexing. */
export function ProjectKnowledge({ project, projectName, sem }: {
  project: string; projectName: string | null; sem: RecallSemantic;
}) {
  const { settings, setSettings } = sem;
  const [delta, setDelta] = useState<RecallDelta | null>(null);
  const [deltaLoading, setDeltaLoading] = useState(true);
  const [deltaError, setDeltaError] = useState<string | null>(null);
  const [cap, setCap] = useState<RecallCapability | null>(null);
  const [capLoading, setCapLoading] = useState(true);
  const [showSetup, setShowSetup] = useState(false);
  const [run, setRun] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [slowOk, setSlowOk] = useState(false);
  // The backend keys runs by canonical project key; `project` may be a path. null until resolved.
  const [canon, setCanon] = useState<string | null>(null);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCanon(null);
    fetchRecallProjects()
      .then((r) => { if (!cancelled) setCanon(resolveRecallProject(r.projects, project)?.key ?? project); })
      .catch(() => { if (!cancelled) setCanon(project); });
    return () => { cancelled = true; };
  }, [project]);

  const loadDelta = useCallback((signal?: AbortSignal) => {
    setDeltaLoading(true);
    return fetchRecallDelta(project, signal)
      .then((d) => { if (alive.current && !signal?.aborted) { setDelta(d); setDeltaError(null); } })
      .catch((e: unknown) => {
        if (signal?.aborted || !alive.current) return;
        setDeltaError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => { if (alive.current && !signal?.aborted) setDeltaLoading(false); });
  }, [project]);

  const loadCap = useCallback((signal?: AbortSignal, sampleProject = false) => {
    setCapLoading(true);
    return fetchRecallCapability(project, signal, sampleProject)
      .then((c) => { if (alive.current && !signal?.aborted) setCap(c); })
      .catch(() => { if (alive.current && !signal?.aborted) setCap(null); })
      .finally(() => { if (alive.current && !signal?.aborted) setCapLoading(false); });
  }, [project]);

  // Project change: reset, check the delta and the machine, and reattach to a run already in progress.
  useEffect(() => {
    const ctl = new AbortController();
    /* eslint-disable react-hooks/set-state-in-effect */
    setDelta(null); setCap(null); setError(null); setSlowOk(false); setRun(null); setRunning(false);
    /* eslint-enable react-hooks/set-state-in-effect */
    void loadDelta(ctl.signal);
    void loadCap(ctl.signal);
    if (canon === null) return () => ctl.abort();
    fetchRecallIndexStatus(ctl.signal)
      .then((s) => {
        if (!ctl.signal.aborted && sameRecallProject(s.project?.key, canon, project) &&["running", "done"].includes(s.state)) {
          setRunning(s.state === "running"); setRun(s.run);
        }
      })
      .catch(() => { /* no run to reattach to */ });
    return () => ctl.abort();
  }, [project, canon, loadDelta, loadCap]);

  const sset = settings?.semantic;
  const isApi = sset?.provider === "api";
  const installed = settings?.ollama.model_installed ?? false;
  const ready = !!sset?.enabled && (isApi || installed);
  const capBlocked = cap?.status === "blocked";
  const capSlow = cap?.status === "slow" && !slowOk;
  const canIndex = ready && !capBlocked && !capSlow;
  const blockedReason = !sset?.enabled
    ? "Set up semantic search first."
    : !isApi && !installed ? "Download the model first."
    : capBlocked ? "Check the embedding provider in the note above."
    : capSlow ? "Choose Index anyway in the capability note." : undefined;
  const setupOpen = showSetup || !ready;

  const index = async (full: boolean) => {
    setBusy(true); setError(null);
    try {
      const r = await startRecallIndexRun(project, full);
      if (!alive.current) return;
      if (r.started || sameRecallProject(r.project, canon ?? project, project)) {
        setRunning(true); setRun(r.run);
      } else {
        setError("Another project is indexing. Try again once that run finishes.");
      }
    } catch (e) {
      if (alive.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  const onFinished = useCallback(() => {
    setRunning(false);
    void loadDelta();
    fetchRecallIndexStatus().catch(() => null);
  }, [loadDelta]);

  return (
    <div className="space-y-3" aria-label={`Project knowledge${projectName ? ` for ${projectName}` : ""}`}>
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--tt-fg-dim)]">Project knowledge</h2>
        <Button size="sm" variant="ghost" className="ml-auto" aria-expanded={setupOpen} onClick={() => setShowSetup((v) => !v)}>
          <Settings2 size={12} /> Embedding setup
        </Button>
      </div>

      <DeltaBanner
        delta={delta} loading={deltaLoading} error={deltaError}
        newModel={effectiveModelName(settings)}
        canIndex={canIndex} blockedReason={blockedReason}
        busy={busy} running={running}
        onIndex={(full) => void index(full)}
      />
      {error && <p className="text-[12px] text-[var(--tt-danger-fg)]">{error}</p>}

      {sset && (
        <CapabilityNote cap={cap} busy={busy || running} onIndexAnyway={() => setSlowOk(true)} />
      )}

      {setupOpen && (
        <SetupCard
          settings={settings}
          capability={cap}
          capabilityLoading={capLoading}
          onChanged={(s) => { if (s) setSettings(s); void loadCap(); void loadDelta(); }}
          onRecheck={(sampleProject = false) => {
            void loadCap(undefined, sampleProject);
            sem.refresh();
          }}
        />
      )}

      <EmbedNote />

      <IndexingTheater project={project} enabled={!!sset?.enabled} images={!!sset?.images} runId={run} onFinished={onFinished} />
    </div>
  );
}
