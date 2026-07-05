"use client";

/* Shown when a project has no detected wiki: explain the plugin, offer the
 * build-new commands, and offer import of an already-built brain (detected
 * candidates or a manual path). Import only records a pointer in TT's own
 * config; the dashboard never writes into the repo. */

import {
  ArrowUp, Brain, Check, Copy, CornerDownLeft, Folder, FolderOpen, Hammer,
  Import, Loader2, Sparkles, TriangleAlert, X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api, apiFetch, useResource } from "@/lib/api";
import { cn } from "@/lib/cn";
import { trackEvent } from "@/lib/telemetry";
import { Badge, Card } from "@/components/ui";

import type { BrowseListing, WikiCandidate } from "./types";

const KIND_LABEL: Record<string, { label: string; tier: "full" | "partial" }> = {
  plugin_wiki: { label: "Plugin wiki", tier: "full" },
  okf_ish: { label: "OKF wiki", tier: "full" },
  obsidian_vault: { label: "Obsidian vault", tier: "partial" },
  markdown_wiki: { label: "Markdown wiki", tier: "partial" },
};

export default function Onboarding({ project, onImported }: { project: string; onImported: () => void }) {
  const { data: candData } = useResource<{ candidates: WikiCandidate[] }>(
    `/brain/candidates?project=${encodeURIComponent(project)}`,
    { initial: { candidates: [] } },
  );
  const candidates = useMemo(() => candData?.candidates ?? [], [candData]);
  const [manualPath, setManualPath] = useState("");
  const [busyPath, setBusyPath] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);

  const doImport = async (wikiPath: string): Promise<boolean> => {
    setBusyPath(wikiPath);
    setImportError(null);
    try {
      const res = await apiFetch("/brain/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project, wiki_path: wikiPath }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `import failed (${res.status})`);
      }
      trackEvent("feature.used", { name: "brain-import" });
      onImported();
      return true;
    } catch (e) {
      setImportError(String((e as Error)?.message ?? e));
      return false;
    } finally {
      setBusyPath(null);
    }
  };

  return (
    <div className="space-y-4">
      {/* hero */}
      <Card padding="lg">
        <div className="flex flex-wrap items-center gap-6">
          <div className="h-14 w-14 grid place-items-center rounded-[var(--tt-radius-lg)] bg-[var(--tt-brand-glow)] border border-[color:var(--tt-brand)]/25 text-[var(--tt-brand)] shrink-0">
            <Brain size={26} />
          </div>
          <div className="min-w-[260px] flex-1">
            <h2 className="text-[18px] font-semibold text-[var(--tt-fg)]">No second brain here yet</h2>
            <p className="mt-1 text-[13px] leading-relaxed text-[var(--tt-fg-muted)] max-w-[560px]">
              The tokentelemetry plugin compiles this project into a small wiki that coding
              agents read instead of re-exploring the codebase. Once it exists, this tab
              renders it as an interactive graph: clusters, links, and every page one click away.
            </p>
          </div>
          <PreviewGraph />
        </div>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* build new */}
        <Card padding="lg">
          <div className="flex items-center gap-2 mb-3">
            <Hammer size={15} className="text-[var(--tt-brand)]" />
            <h3 className="text-[14px] font-semibold text-[var(--tt-fg)]">Build a new brain</h3>
          </div>
          <p className="text-[12px] text-[var(--tt-fg-muted)] mb-3">
            Run these in a Claude Code session inside this project. The compile is
            resumable: batches checkpoint, and rerunning continues where it stopped.
          </p>
          <ol className="space-y-2">
            <CommandStep n={1} cmd="/brain-init" note="detect the domain profile, scaffold docs/wiki/" />
            <CommandStep n={2} cmd="/brain-compile" note="build pages in batches; rerun until complete" />
            <CommandStep n={3} cmd="/skillsmith" note="optional: generate the per-project optimization skill" />
          </ol>
          <p className="mt-3 text-[11px] text-[var(--tt-fg-dim)] flex items-start gap-1.5">
            <Sparkles size={12} className="shrink-0 mt-0.5 text-[var(--tt-brand)]" />
            If the project already holds a graphify graph, ADRs, or an Obsidian vault,
            /brain-init detects them and offers to seed the compile, so paid-for
            knowledge is reused, not rebuilt.
          </p>
        </Card>

        {/* import existing */}
        <Card padding="lg">
          <div className="flex items-center gap-2 mb-3">
            <Import size={15} className="text-[var(--tt-brand)]" />
            <h3 className="text-[14px] font-semibold text-[var(--tt-fg)]">Import an existing brain</h3>
          </div>

          {candidates.length > 0 ? (
            <div className="space-y-2 mb-3">
              {candidates.map((c) => {
                const kind = KIND_LABEL[c.kind] ?? { label: c.kind, tier: "partial" as const };
                return (
                  <div
                    key={c.path}
                    className="flex items-center justify-between gap-3 px-3 py-2 rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-sunken)]"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-[11px] text-[var(--tt-fg)] truncate" title={c.path}>
                          {c.path.replace(project + "/", "")}
                        </span>
                        <Badge variant={kind.tier === "full" ? "success" : "warn"} size="xs">{kind.label}</Badge>
                      </div>
                      <div className="text-[10.5px] text-[var(--tt-fg-dim)] mt-0.5">
                        {c.page_count} pages
                        {kind.tier === "partial" && " · renders untyped; run /brain adopt for the full experience"}
                      </div>
                    </div>
                    <button
                      onClick={() => doImport(c.path)}
                      disabled={busyPath !== null}
                      className="shrink-0 h-7 px-3 rounded-[var(--tt-radius-sm)] bg-[var(--tt-brand)] text-white text-[11px] font-medium hover:bg-[var(--tt-brand-strong)] disabled:opacity-50 transition-colors"
                    >
                      {busyPath === c.path ? "Importing…" : "Import"}
                    </button>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-[12px] text-[var(--tt-fg-muted)] mb-3">
              No wiki-shaped folder was detected in this project. If a brain lives
              somewhere unusual, point at it directly:
            </p>
          )}

          <div className="flex items-center gap-2">
            <button
              onClick={() => setPickerOpen(true)}
              disabled={busyPath !== null}
              className="flex items-center gap-1.5 h-8 px-3 rounded-[var(--tt-radius)] bg-[var(--tt-brand)] text-white text-[12px] font-medium hover:bg-[var(--tt-brand-strong)] disabled:opacity-50 transition-colors shrink-0"
            >
              <FolderOpen size={13} />
              Browse folders…
            </button>
            <div className="flex items-center gap-1.5 flex-1 h-8 px-2.5 rounded-[var(--tt-radius)] bg-[var(--tt-sunken)] border border-[var(--tt-border)] focus-within:border-[var(--tt-border-focus)]">
              <input
                value={manualPath}
                onChange={(e) => setManualPath(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && manualPath.trim()) doImport(manualPath.trim()); }}
                placeholder="or type /absolute/path/to/wiki"
                className="bg-transparent outline-none focus-visible:outline-none text-[12px] font-mono text-[var(--tt-fg)] placeholder:text-[var(--tt-fg-faint)] w-full"
              />
            </div>
            <button
              onClick={() => manualPath.trim() && doImport(manualPath.trim())}
              disabled={!manualPath.trim() || busyPath !== null}
              className="h-8 px-3.5 rounded-[var(--tt-radius)] border border-[var(--tt-border-strong)] text-[12px] font-medium text-[var(--tt-fg)] hover:tt-tint-2 disabled:opacity-40 transition-colors"
            >
              Import
            </button>
          </div>

          {importError && (
            <p className="mt-2 text-[11.5px] text-[var(--tt-danger-fg)] flex items-start gap-1.5">
              <TriangleAlert size={12} className="shrink-0 mt-0.5" />
              {importError}
            </p>
          )}

          <p className="mt-3 text-[11px] text-[var(--tt-fg-dim)]">
            Importing records a pointer in ~/.tokentelemetry only. Nothing is copied
            and this repo is never written; un-import any time.
          </p>
        </Card>
      </div>

      {pickerOpen && (
        <FolderPicker
          project={project}
          busy={busyPath !== null}
          error={importError}
          onImport={doImport}
          onClose={() => setPickerOpen(false)}
        />
      )}

      {/* benefits strip */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Benefit title="Cheaper sessions" text="Agents answer from short pages instead of re-reading the codebase; an AGENTS.md pointer makes it automatic." />
        <Benefit title="Bugs surface early" text="Compiles log contradictions as Findings; the first dogfood run caught a dead cache and stale tests." />
        <Benefit title="Humans can read it too" text="Onboarding, decisions, and playbooks live in one lint-checked place, with an inbox for new knowledge." />
      </div>
    </div>
  );
}

const HINT_BADGE: Record<string, { label: string; variant: "success" | "warn" | "info" }> = {
  plugin_wiki: { label: "Plugin wiki", variant: "success" },
  obsidian_vault: { label: "Obsidian vault", variant: "warn" },
  markdown_wiki: { label: "Markdown", variant: "info" },
};

/** Server-backed folder browser: browsers can't hand us an absolute path from a
 * native picker, so the backend lists directories (inside the allowed roots)
 * and the user walks to the wiki folder here. */
function FolderPicker({ project, busy, error, onImport, onClose }: {
  project: string;
  busy: boolean;
  error: string | null;
  onImport: (path: string) => Promise<boolean>;
  onClose: () => void;
}) {
  const [listing, setListing] = useState<BrowseListing | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const navigate = (path?: string) => {
    setLoading(true);
    setLoadError(null);
    const qs = new URLSearchParams({ project });
    if (path) qs.set("path", path);
    api<BrowseListing>(`/brain/browse?${qs.toString()}`)
      .then((l) => setListing(l))
      .catch((e) => setLoadError(String((e as Error)?.message ?? e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    navigate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const hint = listing?.hint ? HINT_BADGE[listing.hint] : null;

  return (
    <div role="dialog" aria-modal="true" aria-label="Choose a wiki folder" className="fixed inset-0 z-[100]">
      <div className="absolute inset-0 bg-black/55 backdrop-blur-[2px]" onClick={onClose} />
      <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[min(560px,calc(100vw-32px))] rounded-[var(--tt-radius-lg)] border border-[var(--tt-border-strong)] bg-[var(--tt-panel)] shadow-[var(--tt-shadow-pop)] flex flex-col max-h-[70vh]">
        {/* header */}
        <div className="shrink-0 flex items-center justify-between gap-3 px-4 pt-3.5 pb-3 border-b border-[var(--tt-border)]">
          <div className="flex items-center gap-2 text-[13px] font-semibold text-[var(--tt-fg)]">
            <FolderOpen size={14} className="text-[var(--tt-brand)]" />
            Choose a wiki folder
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="h-6 w-6 grid place-items-center rounded-[var(--tt-radius-sm)] text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)] hover:tt-tint-2 transition-colors"
          >
            <X size={13} />
          </button>
        </div>

        {/* current path + up */}
        <div className="shrink-0 flex items-center gap-2 px-4 py-2 border-b border-[var(--tt-border)]">
          <button
            onClick={() => listing?.parent && navigate(listing.parent)}
            disabled={!listing?.parent || loading}
            title="Up one level"
            className="shrink-0 h-6 w-6 grid place-items-center rounded-[var(--tt-radius-sm)] border border-[var(--tt-border)] text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)] hover:border-[var(--tt-border-strong)] disabled:opacity-35 transition-colors"
          >
            <ArrowUp size={12} />
          </button>
          <span className="min-w-0 flex-1 font-mono text-[11px] text-[var(--tt-fg-muted)] truncate" title={listing?.path}>
            {listing?.path ?? "…"}
          </span>
          {hint && <Badge variant={hint.variant} size="xs">{hint.label}</Badge>}
        </div>

        {/* directory list */}
        <div className="flex-1 overflow-y-auto px-2 py-1.5 min-h-[180px]">
          {loading && (
            <div className="h-full grid place-items-center text-[var(--tt-fg-dim)]">
              <Loader2 size={16} className="animate-spin" />
            </div>
          )}
          {!loading && loadError && (
            <p className="px-2 py-3 text-[11.5px] text-[var(--tt-danger-fg)]">{loadError}</p>
          )}
          {!loading && !loadError && listing && listing.dirs.length === 0 && (
            <p className="px-2 py-3 text-[11.5px] text-[var(--tt-fg-dim)]">No subfolders here.</p>
          )}
          {!loading && !loadError && listing?.dirs.map((d) => {
            const b = d.hint ? HINT_BADGE[d.hint] : null;
            return (
              <button
                key={d.path}
                onClick={() => navigate(d.path)}
                className="w-full flex items-center gap-2 px-2 h-7 rounded-[var(--tt-radius-sm)] text-left text-[12px] text-[var(--tt-fg-muted)] hover:tt-tint-2 hover:text-[var(--tt-fg)] transition-colors"
              >
                <Folder size={12} className="shrink-0 text-[var(--tt-fg-dim)]" />
                <span className="min-w-0 flex-1 truncate">{d.name}</span>
                {b && <Badge variant={b.variant} size="xs">{b.label}</Badge>}
              </button>
            );
          })}
          {!loading && listing?.truncated && (
            <p className="px-2 py-1.5 text-[10.5px] text-[var(--tt-fg-faint)]">List truncated; type the path directly if the folder is missing.</p>
          )}
        </div>

        {/* footer */}
        <div className="shrink-0 px-4 py-3 border-t border-[var(--tt-border)] space-y-2">
          {error && (
            <p className="text-[11.5px] text-[var(--tt-danger-fg)] flex items-start gap-1.5">
              <TriangleAlert size={12} className="shrink-0 mt-0.5" />
              {error}
            </p>
          )}
          <div className="flex items-center justify-between gap-3">
            <span className="text-[10.5px] text-[var(--tt-fg-faint)]">
              Pick the folder that holds the wiki pages, then import it.
            </span>
            <div className="flex items-center gap-2 shrink-0">
              <button
                onClick={onClose}
                className="h-7 px-3 rounded-[var(--tt-radius-sm)] border border-[var(--tt-border)] text-[11.5px] text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)] transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={async () => {
                  if (!listing) return;
                  const ok = await onImport(listing.path);
                  if (ok) onClose();
                }}
                disabled={!listing || busy || loading}
                className="flex items-center gap-1.5 h-7 px-3 rounded-[var(--tt-radius-sm)] bg-[var(--tt-brand)] text-white text-[11.5px] font-medium hover:bg-[var(--tt-brand-strong)] disabled:opacity-50 transition-colors"
              >
                {busy ? <Loader2 size={11} className="animate-spin" /> : <CornerDownLeft size={11} />}
                Import this folder
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function CommandStep({ n, cmd, note }: { n: number; cmd: string; note: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <li className="flex items-center gap-2.5">
      <span className="h-5 w-5 grid place-items-center rounded-full tt-tint-2 text-[10px] font-semibold text-[var(--tt-fg-dim)] shrink-0">{n}</span>
      <button
        onClick={() => {
          navigator.clipboard?.writeText(cmd);
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        }}
        className={cn(
          "flex items-center gap-1.5 px-2 h-6 rounded-[var(--tt-radius-sm)] border font-mono text-[11.5px] transition-colors shrink-0",
          copied
            ? "border-[var(--tt-success-bd)] text-[var(--tt-success-fg)] bg-[var(--tt-success-bg)]"
            : "border-[var(--tt-border)] bg-[var(--tt-sunken)] text-[var(--tt-brand)] hover:border-[var(--tt-border-strong)]",
        )}
        title="Copy command"
      >
        {cmd}
        {copied ? <Check size={10} /> : <Copy size={10} className="text-[var(--tt-fg-faint)]" />}
      </button>
      <span className="text-[11px] text-[var(--tt-fg-dim)]">{note}</span>
    </li>
  );
}

function Benefit({ title, text }: { title: string; text: string }) {
  return (
    <div className="px-4 py-3 rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-panel)]">
      <div className="text-[12px] font-semibold text-[var(--tt-fg)] mb-1">{title}</div>
      <div className="text-[11.5px] leading-relaxed text-[var(--tt-fg-dim)]">{text}</div>
    </div>
  );
}

/** Decorative static mini-graph so the payoff is visible before the work. */
function PreviewGraph() {
  const nodes = [
    { x: 60, y: 34, r: 9, c: "#3987e5" },
    { x: 26, y: 62, r: 6, c: "#199e70" },
    { x: 94, y: 60, r: 6, c: "#199e70" },
    { x: 60, y: 86, r: 5, c: "#c98500" },
    { x: 110, y: 26, r: 4.5, c: "#9085e9" },
    { x: 18, y: 24, r: 4.5, c: "#d55181" },
  ];
  const edges = [[0, 1], [0, 2], [0, 3], [1, 3], [2, 4], [0, 5]];
  return (
    <svg width={132} height={104} className="shrink-0 opacity-90" aria-hidden>
      {edges.map(([a, b], i) => (
        <line
          key={i}
          x1={nodes[a].x} y1={nodes[a].y} x2={nodes[b].x} y2={nodes[b].y}
          stroke="var(--tt-fg)" strokeOpacity={0.16} strokeWidth={1.2}
        />
      ))}
      {nodes.map((n, i) => (
        <circle key={i} cx={n.x} cy={n.y} r={n.r} fill={n.c} stroke="var(--tt-panel)" strokeWidth={2} />
      ))}
    </svg>
  );
}
