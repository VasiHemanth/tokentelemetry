"use client";

/* Right-side drawer showing one wiki page: metadata, staleness, rendered
 * markdown, and in/out links that navigate the graph. Follows the
 * WhatsChangedDrawer pattern (backdrop, Esc, scroll lock, slide-in). */

import {
  ArrowDownLeft, ArrowUpRight, Check, Copy, FileText, GitCommitHorizontal, Tag, X,
} from "lucide-react";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { trackEvent } from "@/lib/telemetry";
import { Badge, Skeleton } from "@/components/ui";

import { buildTypePalette, typeSlot } from "./palette";
import type { PageDetail } from "./types";

interface Props {
  project: string;
  pageId: string | null;
  types: string[];
  dark: boolean;
  onClose: () => void;
  onNavigate: (id: string) => void;
}

export default function PageDrawer({ project, pageId, types, dark, onClose, onNavigate }: Props) {
  const [detail, setDetail] = useState<PageDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const open = pageId !== null;

  useEffect(() => {
    if (!pageId) return;
    let cancelled = false;
    setDetail(null);
    setError(null);
    trackEvent("feature.used", { name: "brain-page-open" });
    api<PageDetail>(`/brain/page?project=${encodeURIComponent(project)}&id=${encodeURIComponent(pageId)}`)
      .then((d) => { if (!cancelled) setDetail(d); })
      .catch((e) => { if (!cancelled) setError(String(e?.message ?? e)); });
    return () => { cancelled = true; };
  }, [project, pageId]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  const palette = buildTypePalette(types);
  const slot = typeSlot(palette, detail?.type ?? null);
  const accent = dark ? slot.dark : slot.light;

  return (
    <div role="dialog" aria-modal="true" aria-labelledby="brain-drawer-title" className="fixed inset-0 z-[100]">
      <style>{`
        @keyframes tt-brain-fade-in { from { opacity: 0 } to { opacity: 1 } }
        @keyframes tt-brain-slide-in { from { transform: translateX(8%); opacity: .4 } to { transform: none; opacity: 1 } }
        @media (prefers-reduced-motion: reduce) {
          .tt-brain-anim { animation: none !important }
        }
        /* Drawer-scoped markdown scale. The global .prose is sized for the
         * full-width session viewer; at 520px its headings read shouty, so
         * everything steps down one notch here. */
        .tt-brain-md { font-size: 12.5px; line-height: 1.62; color: var(--tt-fg-muted); }
        .tt-brain-md h1, .tt-brain-md h2, .tt-brain-md h3, .tt-brain-md h4 {
          color: var(--tt-fg); font-weight: 600; letter-spacing: -0.01em;
          margin: 1.4em 0 0.45em;
        }
        .tt-brain-md > :first-child { margin-top: 0.2em; }
        .tt-brain-md h1 { font-size: 15px; padding-bottom: 0.3em; border-bottom: 1px solid var(--tt-border); }
        .tt-brain-md h2 { font-size: 13.5px; }
        .tt-brain-md h3, .tt-brain-md h4 { font-size: 12.5px; }
        .tt-brain-md p { margin: 0 0 0.8em; }
        .tt-brain-md ul, .tt-brain-md ol { margin: 0 0 0.8em; padding-left: 1.3em; }
        .tt-brain-md ul { list-style-type: disc; }
        .tt-brain-md ol { list-style-type: decimal; }
        .tt-brain-md li { margin-bottom: 0.3em; }
        .tt-brain-md code {
          background: var(--tt-sunken); border: 1px solid var(--tt-border);
          border-radius: 4px; padding: 0.1em 0.35em;
          font-family: var(--font-mono); font-size: 0.92em;
        }
        .tt-brain-md pre {
          background: var(--tt-sunken); border: 1px solid var(--tt-border);
          border-radius: var(--tt-radius); padding: 0.75em 0.9em;
          overflow-x: auto; margin: 0 0 1em; font-size: 11px; line-height: 1.55;
        }
        .tt-brain-md pre code { background: none; border: none; padding: 0; font-size: inherit; }
        .tt-brain-md blockquote {
          border-left: 3px solid var(--tt-border-strong); padding-left: 0.9em;
          margin: 0 0 0.8em; color: var(--tt-fg-dim); font-style: italic;
        }
        .tt-brain-md table { border-collapse: collapse; font-size: 11.5px; margin: 0 0 1em; display: block; overflow-x: auto; }
        .tt-brain-md th, .tt-brain-md td { border: 1px solid var(--tt-border); padding: 0.35em 0.6em; text-align: left; }
        .tt-brain-md th { background: var(--tt-sunken); color: var(--tt-fg); font-weight: 600; }
        .tt-brain-md a { color: var(--tt-brand); text-decoration: none; }
        .tt-brain-md a:hover { text-decoration: underline; }
        .tt-brain-md hr { border: none; border-top: 1px solid var(--tt-border); margin: 1.2em 0; }
      `}</style>
      <div
        className="tt-brain-anim absolute inset-0 bg-black/55 backdrop-blur-[2px] animate-[tt-brain-fade-in_120ms_ease-out]"
        onClick={onClose}
      />
      <aside className="tt-brain-anim absolute right-0 top-0 bottom-0 w-full max-w-[520px] bg-[var(--tt-panel)] border-l border-[var(--tt-border-strong)] shadow-[-24px_0_60px_-20px_rgba(0,0,0,0.6)] flex flex-col animate-[tt-brain-slide-in_180ms_ease-out]">
        {/* header */}
        <div className="shrink-0 px-5 pt-4 pb-3 border-b border-[var(--tt-border)]" style={{ boxShadow: `inset 3px 0 0 ${accent}` }}>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="h-2.5 w-2.5 rounded-full shrink-0" style={{ background: accent }} />
                <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--tt-fg-dim)]">
                  {detail?.type ?? "page"}
                </span>
                {detail?.status && (
                  <Badge variant={detail.status === "adopted" ? "success" : detail.status === "rejected" ? "danger" : "info"} size="xs">
                    {detail.status}
                  </Badge>
                )}
              </div>
              <h2 id="brain-drawer-title" className="text-[17px] font-semibold leading-snug text-[var(--tt-fg)]">
                {detail?.title ?? pageId}
              </h2>
              <div className="mt-1 font-mono text-[10.5px] text-[var(--tt-fg-faint)] truncate" title={pageId ?? undefined}>
                {pageId}.md
              </div>
            </div>
            <button
              onClick={onClose}
              aria-label="Close"
              className="shrink-0 h-7 w-7 grid place-items-center rounded-[var(--tt-radius-sm)] text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)] hover:tt-tint-2 transition-colors"
            >
              <X size={15} />
            </button>
          </div>
        </div>

        {/* body */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {error && (
            <div className="text-[12px] text-[var(--tt-danger-fg)] bg-[var(--tt-danger-bg)] border border-[var(--tt-danger-bd)] rounded-[var(--tt-radius)] px-3 py-2">
              {error}
            </div>
          )}
          {!detail && !error && (
            <div className="space-y-3">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-40 w-full" />
            </div>
          )}

          {detail && (
            <>
              {detail.description && (
                <p className="text-[13px] leading-relaxed text-[var(--tt-fg-muted)] italic">
                  {detail.description}
                </p>
              )}

              {/* meta grid */}
              <div className="grid grid-cols-1 gap-1.5 text-[11.5px]">
                {detail.timestamp && (
                  <MetaRow label="Updated">{detail.timestamp}</MetaRow>
                )}
                {detail.resource && (
                  <MetaRow label="Source">
                    <span className="inline-flex items-center gap-1.5 min-w-0">
                      <FileText size={11} className="shrink-0 text-[var(--tt-fg-dim)]" />
                      <span className="font-mono truncate" title={detail.resource}>{detail.resource}</span>
                      <button
                        onClick={() => {
                          navigator.clipboard?.writeText(detail.resource!);
                          setCopied(true);
                          setTimeout(() => setCopied(false), 1200);
                        }}
                        className="shrink-0 text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)]"
                        title="Copy source path"
                      >
                        {copied ? <Check size={11} className="text-[var(--tt-success-fg)]" /> : <Copy size={11} />}
                      </button>
                    </span>
                  </MetaRow>
                )}
                <MetaRow label="Freshness">
                  <StalenessPill s={detail.staleness} />
                </MetaRow>
                {detail.tags.length > 0 && (
                  <MetaRow label="Tags">
                    <span className="flex flex-wrap gap-1">
                      {detail.tags.map((t) => (
                        <span key={String(t)} className="inline-flex items-center gap-1 px-1.5 h-5 rounded-full tt-tint-2 text-[10px] text-[var(--tt-fg-dim)]">
                          <Tag size={9} />{String(t)}
                        </span>
                      ))}
                    </span>
                  </MetaRow>
                )}
              </div>

              {/* markdown body */}
              <div className="pt-2 border-t border-[var(--tt-border)]">
                <div className="tt-brain-md max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{stripDupTitle(detail.body, detail.title)}</ReactMarkdown>
                </div>
              </div>

              {/* links */}
              {(detail.outbound.length > 0 || detail.inbound.length > 0) && (
                <div className="pt-3 border-t border-[var(--tt-border)] space-y-3">
                  <LinkGroup
                    icon={<ArrowUpRight size={12} />}
                    label={`Links to (${detail.outbound.length})`}
                    links={detail.outbound}
                    onNavigate={onNavigate}
                  />
                  <LinkGroup
                    icon={<ArrowDownLeft size={12} />}
                    label={`Linked from (${detail.inbound.length})`}
                    links={detail.inbound}
                    onNavigate={onNavigate}
                  />
                </div>
              )}
            </>
          )}
        </div>

        {/* footer */}
        <div className="shrink-0 px-5 py-2.5 border-t border-[var(--tt-border)] flex items-center gap-1.5 text-[10.5px] text-[var(--tt-fg-faint)]">
          <GitCommitHorizontal size={11} />
          Maintained by the tokentelemetry plugin. Pages are a map, not testimony: confirm against the cited source before relying on one.
        </div>
      </aside>
    </div>
  );
}

/** Drop a leading `# Heading` that just repeats the drawer's own title. */
function stripDupTitle(body: string, title: string): string {
  const m = body.match(/^\s*#\s+(.+?)\s*\n+/);
  if (m && m[1].trim().toLowerCase() === title.trim().toLowerCase()) {
    return body.slice((m.index ?? 0) + m[0].length);
  }
  return body;
}

function MetaRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      <span className="w-[64px] shrink-0 text-[var(--tt-fg-faint)] uppercase tracking-wide text-[9.5px] font-semibold pt-0.5">{label}</span>
      <span className="min-w-0 text-[var(--tt-fg-muted)]">{children}</span>
    </div>
  );
}

function StalenessPill({ s }: { s: PageDetail["staleness"] }) {
  const cfg = {
    fresh: { text: "Fresh", cls: "text-[var(--tt-success-fg)] bg-[var(--tt-success-bg)] border-[var(--tt-success-bd)]", hint: "Source unchanged since this page was compiled" },
    stale: { text: "Source changed", cls: "text-[var(--tt-warn-fg)] bg-[var(--tt-warn-bg)] border-[var(--tt-warn-bd)]", hint: s.diffstat ?? "Source changed since compile; re-run /brain ingest" },
    unknown: { text: "Unknown", cls: "text-[var(--tt-fg-dim)] tt-tint-1 border-[var(--tt-border)]", hint: s.reason ?? "No compile SHA on record" },
  }[s.status];
  return (
    <span
      className={cn("inline-flex items-center h-5 px-2 rounded-full border text-[10px] font-medium", cfg.cls)}
      title={cfg.hint}
    >
      {cfg.text}
    </span>
  );
}

function LinkGroup({ icon, label, links, onNavigate }: {
  icon: React.ReactNode; label: string; links: { id: string; title: string }[]; onNavigate: (id: string) => void;
}) {
  if (links.length === 0) return null;
  return (
    <div>
      <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--tt-fg-faint)] mb-1.5">
        {icon}{label}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {links.map((l) => (
          <button
            key={l.id}
            onClick={() => onNavigate(l.id)}
            className="px-2 h-6 rounded-full border border-[var(--tt-border)] bg-[var(--tt-sunken)] text-[11px] text-[var(--tt-fg-muted)] hover:text-[var(--tt-brand)] hover:border-[color:var(--tt-brand)]/40 transition-colors"
            title={l.id}
          >
            {l.title}
          </button>
        ))}
      </div>
    </div>
  );
}
