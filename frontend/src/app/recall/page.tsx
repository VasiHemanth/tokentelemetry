"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { History, Search, AlertTriangle, RotateCw, MessageSquare } from "lucide-react";

import { useResource } from "@/lib/api";
import { getAgent } from "@/lib/agents";
import { cn } from "@/lib/cn";
import {
  PageHeader, Card, Button, EmptyState, Skeleton, AgentBadge,
} from "@/components/ui";
import { AskPanel } from "@/components/recall/AskPanel";
import { SemanticControl, useRecallSemantic, type RecallSemantic } from "@/components/recall/SemanticControl";
import { HitGroupCard, SessionHeadLine, type HitGroup } from "@/components/recall/SessionRow";
import {
  RECALL_DEFAULT_MAX_SESSIONS, RECALL_WIDE_MAX_SESSIONS,
  fetchRecallSearch, queryNeedles, recallSessionsPath, localDayKey, localDayLabel,
  type RecallProjectsResponse, type RecallSessionsResponse, type RecallSearchResponse,
  type RecallSession, type RecallMode,
} from "@/lib/recall";

const STORAGE_KEY = "tt-recall-project";
const ALL = "";

function readStoredProject(): string {
  try { return window.localStorage.getItem(STORAGE_KEY) ?? ALL; } catch { return ALL; }
}
function storeProject(v: string) {
  try { window.localStorage.setItem(STORAGE_KEY, v); } catch { /* storage unavailable */ }
}

interface Submitted { q: string; maxSessions: number; nonce: number }
type Tab = "search" | "ask";

export default function RecallPage() {
  const { data: projectsData, loading: projectsLoading, error: projectsError, refetch } =
    useResource<RecallProjectsResponse>("/recall/projects");
  const projects = useMemo(() => projectsData?.projects ?? [], [projectsData]);

  const [project, setProject] = useState<string>(ALL);
  const [hydrated, setHydrated] = useState(false);
  const [agents, setAgents] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [submitted, setSubmitted] = useState<Submitted | null>(null);
  const [tab, setTab] = useState<Tab>("search");
  // Empty means "server default".
  const [mode, setMode] = useState<RecallMode | "">("");
  const sem = useRecallSemantic();
  const semEnabled = !!sem.settings?.semantic.enabled;
  const defaultMode: RecallMode = sem.settings?.semantic.default_mode ?? "keyword";
  const effectiveMode: RecallMode | null = semEnabled ? (mode || defaultMode) : null;

  useEffect(() => {
    // Restore after mount so server and client markup match.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setProject(readStoredProject());
    setHydrated(true);
  }, []);

  // A stored project that no longer exists falls back to All projects.
  const selected = projects.find((p) => p.key === project) ?? null;
  const effectiveProject = selected ? selected.key : ALL;

  const agentOptions = useMemo(() => {
    const set = new Set<string>();
    (selected ? [selected] : projects).forEach((p) => p.agents.forEach((a) => set.add(a)));
    return Array.from(set).sort();
  }, [selected, projects]);
  const activeAgents = agents.filter((a) => agentOptions.includes(a));

  const pickProject = (key: string) => {
    setProject(key);
    storeProject(key);
    setAgents([]);
    setSubmitted((s) => (s ? { ...s, nonce: s.nonce + 1, maxSessions: RECALL_DEFAULT_MAX_SESSIONS } : s));
  };
  const toggleAgent = (a: string) => {
    setAgents((cur) => (cur.includes(a) ? cur.filter((x) => x !== a) : [...cur, a]));
    setSubmitted((s) => (s ? { ...s, nonce: s.nonce + 1 } : s));
  };
  const submit = () => {
    const q = input.trim();
    if (!q) { setSubmitted(null); return; }
    setSubmitted({ q, maxSessions: RECALL_DEFAULT_MAX_SESSIONS, nonce: Date.now() });
  };
  const searchMore = () =>
    setSubmitted((s) => (s ? { ...s, maxSessions: RECALL_WIDE_MAX_SESSIONS, nonce: s.nonce + 1 } : s));

  return (
    <div className="px-4 sm:px-8 py-8 max-w-[1100px] mx-auto space-y-6 pb-20">
      <PageHeader
        eyebrow="Cross-harness"
        title="Recall"
        description="Search past sessions from every connected agent as one corpus, scoped to a project."
        icon={<History size={20} strokeWidth={2.25} />}
      />

      <div role="tablist" aria-label="Recall mode" className="flex gap-1 border-b border-[var(--tt-border)]">
        {([["search", "Search", Search], ["ask", "Ask", MessageSquare]] as const).map(([id, label, Icon]) => (
          <button
            key={id}
            role="tab"
            type="button"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className={cn(
              "inline-flex items-center gap-1.5 h-9 px-3 -mb-px border-b-2 text-[13px] font-medium transition-colors",
              tab === id
                ? "border-[var(--tt-brand)] text-[var(--tt-fg)]"
                : "border-transparent text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)]",
            )}
          >
            <Icon size={13} /> {label}
          </button>
        ))}
      </div>

      {projectsError ? (
        <Card>
          <EmptyState
            icon={<AlertTriangle size={20} />}
            title="Could not load projects"
            description={projectsError.message}
            action={<Button onClick={refetch}><RotateCw size={14} /> Retry</Button>}
          />
        </Card>
      ) : (
        <>
          <div className="flex flex-col sm:flex-row gap-3">
            <select
              aria-label="Project"
              value={effectiveProject}
              disabled={projectsLoading || !hydrated}
              onChange={(e) => pickProject(e.target.value)}
              className="h-9 sm:w-[300px] shrink-0 px-3 rounded-[var(--tt-radius)] bg-[var(--tt-panel)] border border-[var(--tt-border)] text-[13px] text-[var(--tt-fg)] hover:border-[var(--tt-border-strong)] focus:outline-none focus:ring-1 focus:ring-[color:var(--tt-brand)]/30"
            >
              <option value={ALL}>All projects</option>
              {projects.map((p) => (
                <option key={p.key} value={p.key}>
                  {p.name} ({p.agents.join(", ")}) · {p.session_count}
                </option>
              ))}
            </select>
            {tab === "search" && (<div className="relative flex-1">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--tt-fg-dim)] pointer-events-none" />
              <input
                type="text"
                maxLength={300}
                value={input}
                placeholder='Search past sessions, e.g. render pipeline or "exact phrase"'
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
                className="w-full h-9 pl-9 pr-3 rounded-[var(--tt-radius)] bg-[var(--tt-panel)] border border-[var(--tt-border)] text-[13px] text-[var(--tt-fg)] placeholder:text-[var(--tt-fg-faint)] hover:border-[var(--tt-border-strong)] focus:border-[color:var(--tt-brand)]/40 focus:outline-none focus:ring-1 focus:ring-[color:var(--tt-brand)]/30 transition-colors"
              />
            </div>)}
          </div>
          {tab === "search" && (<p className="text-[11px] text-[var(--tt-fg-dim)] -mt-3">
            Press Enter to search. Put a phrase in double quotes to require it verbatim. Secrets are redacted in results.
          </p>)}

          {selected && (
            <div className="flex flex-wrap items-center gap-2 text-[11px] text-[var(--tt-fg-dim)]">
              {selected.agents.map((a) => <AgentBadge key={a} agent={a} />)}
              <span className="tabular">{selected.session_count} sessions</span>
            </div>
          )}

          {agentOptions.length > 1 && (
            <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filter by agent">
              <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--tt-fg-dim)]">Agents</span>
              {agentOptions.map((a) => {
                const on = activeAgents.includes(a);
                return (
                  <button
                    key={a}
                    type="button"
                    aria-pressed={on}
                    onClick={() => toggleAgent(a)}
                    className={cn(
                      "h-7 px-2.5 rounded-full border text-[12px] font-medium transition-colors",
                      on
                        ? "border-[color:var(--tt-brand)]/40 text-[var(--tt-brand)] bg-[color:var(--tt-brand-glow)]"
                        : "border-[var(--tt-border)] text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] hover:tt-tint-1",
                    )}
                  >
                    {getAgent(a).label}
                  </button>
                );
              })}
            </div>
          )}

          <SemanticControl sem={sem} project={effectiveProject} projectName={selected?.name ?? null} />

          {tab === "search" && semEnabled && (
            <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Search mode">
              <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--tt-fg-dim)]">Mode</span>
              {(["keyword", "hybrid", "semantic"] as const).map((m) => {
                const on = effectiveMode === m;
                return (
                  <button
                    key={m}
                    type="button"
                    aria-pressed={on}
                    onClick={() => {
                      setMode(m);
                      setSubmitted((s) => (s ? { ...s, nonce: s.nonce + 1 } : s));
                    }}
                    className={cn(
                      "h-7 px-2.5 rounded-full border text-[12px] font-medium capitalize transition-colors",
                      on
                        ? "border-[color:var(--tt-brand)]/40 text-[var(--tt-brand)] bg-[color:var(--tt-brand-glow)]"
                        : "border-[var(--tt-border)] text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] hover:tt-tint-1",
                    )}
                  >
                    {m}
                  </button>
                );
              })}
            </div>
          )}

          {tab === "ask" ? (
            <AskPanel project={effectiveProject} agents={activeAgents} />
          ) : submitted ? (
            <SearchResults
              submitted={submitted}
              project={effectiveProject}
              agents={activeAgents}
              showProject={!selected}
              onSearchMore={searchMore}
              mode={effectiveMode}
              sem={sem}
              projectName={selected?.name ?? null}
            />
          ) : (
            <Timeline
              ready={hydrated && !projectsLoading}
              project={effectiveProject}
              agents={activeAgents}
              showProject={!selected}
              hasProjects={projects.length > 0}
            />
          )}
        </>
      )}
    </div>
  );
}

function ListSkeleton() {
  return (
    <div className="space-y-3">
      {[0, 1, 2].map((i) => <Skeleton key={i} className="h-20 w-full" />)}
    </div>
  );
}

function Timeline({ ready, project, agents, showProject, hasProjects }: {
  ready: boolean; project: string; agents: string[]; showProject: boolean; hasProjects: boolean;
}) {
  const path = ready ? recallSessionsPath(project || null, agents) : null;
  const { data, loading, error, refetch } = useResource<RecallSessionsResponse>(path);

  if (!ready || loading) return <ListSkeleton />;
  if (error) {
    return (
      <Card>
        <EmptyState
          icon={<AlertTriangle size={20} />}
          title="Could not load sessions"
          description={error.message}
          action={<Button onClick={refetch}><RotateCw size={14} /> Retry</Button>}
        />
      </Card>
    );
  }
  const sessions = data?.sessions ?? [];
  if (!sessions.length) {
    return (
      <Card>
        <EmptyState
          icon={<History size={20} />}
          title="No sessions yet"
          description={hasProjects
            ? "No sessions match this project and agent filter."
            : "Once your agents log activity, their sessions will appear here."}
        />
      </Card>
    );
  }

  const days: { key: string; label: string; items: RecallSession[] }[] = [];
  for (const s of sessions) {
    const key = localDayKey(s.last_ts) || "none";
    const last = days[days.length - 1];
    if (last && last.key === key) last.items.push(s);
    else days.push({ key, label: localDayLabel(s.last_ts), items: [s] });
  }

  return (
    <div className="space-y-5">
      <div className="text-[11px] text-[var(--tt-fg-dim)] tabular">
        Recent sessions{data ? ` (${sessions.length} of ${data.total})` : ""}
      </div>
      {days.map((d) => (
        <section key={d.key} className="space-y-2">
          <h2 className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--tt-fg-dim)]">{d.label}</h2>
          <div className="rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] divide-y divide-[var(--tt-border)]">
            {d.items.map((s) => (
              <div key={`${s.agent}:${s.id}`} className="px-4 py-3">
                <SessionHeadLine
                  s={{ agent: s.agent, id: s.id, title: s.title, model: s.model, cost: s.cost, ts: s.last_ts, project: s.project }}
                  showProject={showProject}
                />
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function SearchResults({ submitted, project, agents, showProject, onSearchMore, mode, sem, projectName }: {
  submitted: Submitted; project: string; agents: string[]; showProject: boolean; onSearchMore: () => void;
  mode: RecallMode | null; sem: RecallSemantic; projectName: string | null;
}) {
  const [state, setState] = useState<{
    loading: boolean; error: string | null; data: RecallSearchResponse | null;
  }>({ loading: true, error: null, data: null });
  const agentsKey = agents.join(",");
  const seq = useRef(0);

  useEffect(() => {
    const ctl = new AbortController();
    const mine = ++seq.current;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState((s) => ({ ...s, loading: true, error: null }));
    fetchRecallSearch(
      {
        q: submitted.q,
        project: project || null,
        agents: agentsKey ? agentsKey.split(",") : [],
        maxSessions: submitted.maxSessions,
        mode,
      },
      ctl.signal,
    )
      .then((data) => { if (seq.current === mine) setState({ loading: false, error: null, data }); })
      .catch((e: unknown) => {
        if (ctl.signal.aborted || seq.current !== mine) return;
        setState({ loading: false, error: e instanceof Error ? e.message : String(e), data: null });
      });
    return () => ctl.abort();
  }, [submitted.q, submitted.maxSessions, submitted.nonce, project, agentsKey, mode]);

  const needles = useMemo(() => queryNeedles(submitted.q), [submitted.q]);
  const { loading, error, data } = state;

  const groups = useMemo<HitGroup[]>(() => {
    if (!data) return [];
    const map = new Map<string, HitGroup>();
    for (const h of data.hits) {
      const k = `${h.agent}:${h.id}`;
      let g = map.get(k);
      if (!g) {
        g = {
          agent: h.agent, id: h.id, title: h.title, model: h.model, cost: h.cost,
          last_ts: h.last_ts, project: h.project, hits: [],
        };
        map.set(k, g);
      }
      g.hits.push({ turn: h.turn, kind: h.kind, snippet: h.snippet, source: h.source, match: h.match });
    }
    return Array.from(map.values());
  }, [data]);

  if (error) {
    return (
      <Card>
        <EmptyState icon={<AlertTriangle size={20} />} title="Search failed" description={error} />
      </Card>
    );
  }
  if (loading && !data) return <ListSkeleton />;
  if (!data) return null;

  const cov = data.coverage;
  const incomplete = cov.sessions_skipped > 0 || cov.timed_out || cov.truncated > 0;
  const byAgent = Object.entries(data.by_agent).sort((a, b) => b[1] - a[1]);
  const unindexed = cov.semantic && cov.semantic.mode !== "keyword" ? cov.semantic.unindexed_sessions : 0;
  const canWiden = submitted.maxSessions < RECALL_WIDE_MAX_SESSIONS && cov.skipped_reason === "max_sessions";

  return (
    <div className={cn("space-y-4", loading && "opacity-60 transition-opacity")} aria-busy={loading}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-[var(--tt-fg-muted)]">
        <span className="tabular">{data.hits.length} {data.hits.length === 1 ? "hit" : "hits"}</span>
        {byAgent.length > 0 && (
          <span className="tabular text-[var(--tt-fg-dim)]">
            {byAgent.map(([a, n]) => `${a} ${n}`).join(" · ")}
          </span>
        )}
      </div>

      {incomplete && (
        <div
          role="status"
          className="flex flex-wrap items-start gap-3 rounded-[var(--tt-radius)] border border-[var(--tt-warn-bd)] bg-[var(--tt-warn-bg)] px-3 py-2.5 text-[12px] text-[var(--tt-warn-fg)]"
        >
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <div className="flex-1 min-w-[220px] space-y-0.5">
            {cov.sessions_skipped > 0 && (
              <div className="tabular">
                Searched {cov.sessions_scanned} of {cov.candidates} sessions
                {cov.skipped_reason === "timeout" ? " before the time budget ran out" : ""}
                {canWiden ? "; narrow by project or search more." : "; narrow by project or agent."}
              </div>
            )}
            {cov.timed_out && cov.sessions_skipped === 0 && (
              <div>The search hit its time budget and may be incomplete.</div>
            )}
            {cov.truncated > 0 && (
              <div className="tabular">
                {cov.truncated} very long {cov.truncated === 1 ? "session was" : "sessions were"} searched only in its last 20,000 chunks.
              </div>
            )}
            {cov.unreadable > 0 && <div className="tabular">{cov.unreadable} could not be read.</div>}
          </div>
          {canWiden && (
            <Button size="sm" onClick={onSearchMore} disabled={loading}>
              Search more ({RECALL_WIDE_MAX_SESSIONS} sessions)
            </Button>
          )}
        </div>
      )}

      {unindexed > 0 && (
        <div role="status" className="flex flex-wrap items-center gap-3 rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-sunken)] px-3 py-2 text-[12px] text-[var(--tt-fg-muted)]">
          <span className="flex-1 min-w-[220px] tabular">
            {unindexed} of {cov.semantic!.indexed_sessions + unindexed} searched {unindexed === 1 ? "session is" : "sessions are"} not indexed and matched by keyword only.
          </span>
          {sem.settings?.ollama.reachable && sem.settings.ollama.model_installed && sem.index?.state !== "running" && (
            <Button size="sm" disabled={sem.busy} onClick={() => void sem.build(project || null)}>
              {project ? `Build index for ${projectName ?? "this project"}` : "Build index"}
            </Button>
          )}
          {sem.index?.state === "running" && (
            <span className="tabular text-[var(--tt-fg-dim)]">Indexing {sem.index.sessions_done + sem.index.sessions_skipped}/{sem.index.sessions_total}</span>
          )}
        </div>
      )}

      {groups.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Search size={20} />}
            title={`No matches for "${submitted.q}"`}
            description={incomplete
              ? "Not every session was searched, so this does not mean it was never discussed."
              : "Try fewer or different words, or another project."}
          />
        </Card>
      ) : (
        <div className="space-y-3">
          {groups.map((g) => (
            <HitGroupCard key={`${g.agent}:${g.id}`} g={g} needles={needles} showProject={showProject} />
          ))}
        </div>
      )}
    </div>
  );
}
