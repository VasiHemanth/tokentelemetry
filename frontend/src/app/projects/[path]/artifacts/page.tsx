"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { format } from "date-fns";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Globe, ArrowUpRight, ExternalLink, FileText,
  LayoutGrid, List as ListIcon, ChevronDown, ChevronRight,
} from "lucide-react";

import { Card, CardTitle, AgentBadge, EmptyState } from "@/components/ui";
import { artifactUrl } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useProject, type PublishedArtifact } from "../_lib/project-context";

type ViewMode = "cards" | "list";
const VIEW_KEY = "tt-artifacts-view";

function rawFileUrl(path: string): string {
  return artifactUrl(`/artifacts?path=${encodeURIComponent(path)}`);
}

/* Scaled-down live preview of a page artifact's LOCAL html source (the file the
   Artifact tool published from). The iframe is sandboxed with no scripts and no
   pointer events — it's a thumbnail, not an embed; clicking opens the hosted
   url. Mounted lazily (IntersectionObserver) and only after a HEAD check
   confirms the source file still exists — it may have been deleted since. */
const FRAME_W = 1280;
const PREVIEW_H = 200;

function PagePreview({ path, href }: { path: string; href: string }) {
  const holderRef = useRef<HTMLDivElement>(null);
  const [inView, setInView] = useState(false);
  const [available, setAvailable] = useState<boolean | null>(null);
  const [scale, setScale] = useState(0);

  // Lazy-mount: wait until the card scrolls near the viewport.
  useEffect(() => {
    const el = holderRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setInView(true);
          io.disconnect();
        }
      },
      { rootMargin: "200px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  // Availability check — on any failure render nothing (just the link card).
  useEffect(() => {
    if (!inView) return;
    let cancelled = false;
    fetch(rawFileUrl(path), { method: "HEAD" })
      .then((res) => { if (!cancelled) setAvailable(res.ok); })
      .catch(() => { if (!cancelled) setAvailable(false); });
    return () => { cancelled = true; };
  }, [inView, path]);

  // Scale the fixed 1280px frame down to the container's width.
  useEffect(() => {
    if (!available) return;
    const el = holderRef.current;
    if (!el) return;
    const update = () => setScale(el.clientWidth / FRAME_W);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [available]);

  return (
    <div ref={holderRef}>
      {available && (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          title="Open hosted page"
          className="block relative overflow-hidden rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-sunken)] hover:border-[var(--tt-border-strong)] transition-colors"
          style={{ height: PREVIEW_H }}
        >
          {scale > 0 && (
            <iframe
              src={rawFileUrl(path)}
              sandbox="allow-same-origin"
              tabIndex={-1}
              aria-hidden
              scrolling="no"
              className="pointer-events-none select-none origin-top-left border-0 bg-white"
              style={{ width: FRAME_W, height: PREVIEW_H / scale, transform: `scale(${scale})` }}
            />
          )}
        </a>
      )}
    </div>
  );
}

/* Collapsed-by-default markdown preview for document artifacts. Fetches the
   file only on first expand; a vanished file degrades to a quiet note. */
function DocumentPreview({ path }: { path: string }) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [text, setText] = useState("");

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && state === "idle") {
      setState("loading");
      fetch(rawFileUrl(path))
        .then((res) => (res.ok ? res.text() : Promise.reject(new Error(`HTTP ${res.status}`))))
        .then((t) => { setText(t); setState("ready"); })
        .catch(() => setState("error"));
    }
  };

  return (
    <div className="pt-1">
      <button
        onClick={toggle}
        className="inline-flex items-center gap-1 text-[11px] font-medium text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] transition-colors"
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />} Preview
      </button>
      {open && state === "loading" && (
        <p className="mt-2 text-[11px] text-[var(--tt-fg-dim)]">Loading…</p>
      )}
      {open && state === "error" && (
        <p className="mt-2 text-[11px] italic text-[var(--tt-fg-dim)]">file no longer available</p>
      )}
      {open && state === "ready" && (
        <div className="mt-2 max-h-[300px] overflow-y-auto rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-sunken)] p-4 prose prose-sm max-w-none">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
        </div>
      )}
    </div>
  );
}

function ArtifactCard({ a, sessionHref }: { a: PublishedArtifact; sessionHref: string | null }) {
  const isPage = !!a.url;
  return (
    <Card padding="none" className="overflow-hidden">
      <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-[var(--tt-border)]">
        <div className="flex items-center gap-3 min-w-0">
          {!isPage && <FileText size={14} className="shrink-0 text-[var(--tt-fg-muted)]" />}
          <AgentBadge agent={a.agent || "claude"} />
          <CardTitle className="!text-[13px] truncate" title={a.title || a.url || a.file_name || undefined}>
            {a.title || a.file_name || "Untitled artifact"}
          </CardTitle>
        </div>
        {a.timestamp && (
          <span className="text-[10px] uppercase tracking-[0.18em] text-[var(--tt-fg-dim)] shrink-0">
            {format(new Date(a.timestamp), "MMM d, HH:mm")}
          </span>
        )}
      </div>

      <div className="px-5 py-4 space-y-2">
        {a.description && (
          <p className="text-[12px] text-[var(--tt-fg-muted)] leading-relaxed">{a.description}</p>
        )}
        {isPage ? (
          <a
            href={a.url!}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-[11px] font-mono text-[var(--tt-brand)] hover:underline break-all"
          >
            {a.url} <ExternalLink size={11} className="shrink-0" />
          </a>
        ) : a.path && (
          <a
            href={rawFileUrl(a.path)}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-[11px] font-mono text-[var(--tt-brand)] hover:underline"
          >
            {a.file_name || "open file"} <ExternalLink size={11} className="shrink-0" />
          </a>
        )}
        {isPage && a.path && a.url && <PagePreview path={a.path} href={a.url} />}
        {!isPage && a.path && <DocumentPreview path={a.path} />}
      </div>

      {sessionHref && (
        <div className="px-5 py-3 border-t border-[var(--tt-border)] bg-[var(--tt-sunken)] flex justify-end">
          <Link
            href={sessionHref}
            className="inline-flex items-center gap-1.5 text-[11px] font-medium text-[var(--tt-fg-muted)] hover:text-[var(--tt-brand)] transition-colors uppercase tracking-[0.16em]"
          >
            View session <ArrowUpRight size={12} />
          </Link>
        </div>
      )}
    </Card>
  );
}

function ArtifactRow({ a, sessionHref }: { a: PublishedArtifact; sessionHref: string | null }) {
  const isPage = !!a.url;
  const openHref = a.url || (a.path ? rawFileUrl(a.path) : null);
  return (
    <div className="flex items-center gap-3 px-5 py-2.5">
      {!isPage && <FileText size={13} className="shrink-0 text-[var(--tt-fg-muted)]" />}
      <AgentBadge agent={a.agent || "claude"} />
      <span
        className="flex-1 min-w-0 truncate text-[12px] font-medium text-[var(--tt-fg)]"
        title={a.title || a.url || a.file_name || undefined}
      >
        {a.title || a.file_name || "Untitled artifact"}
      </span>
      {a.timestamp && (
        <span className="text-[10px] uppercase tracking-[0.18em] text-[var(--tt-fg-dim)] shrink-0 text-right">
          {format(new Date(a.timestamp), "MMM d, HH:mm")}
        </span>
      )}
      {openHref && (
        <a
          href={openHref}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={isPage ? "Open hosted page" : "Open file"}
          title={isPage ? "Open hosted page" : "Open file"}
          className="shrink-0 text-[var(--tt-fg-muted)] hover:text-[var(--tt-brand)] transition-colors"
        >
          <ExternalLink size={13} />
        </a>
      )}
      {sessionHref && (
        <Link
          href={sessionHref}
          aria-label="View session"
          title="View session"
          className="shrink-0 text-[var(--tt-fg-muted)] hover:text-[var(--tt-brand)] transition-colors"
        >
          <ArrowUpRight size={14} />
        </Link>
      )}
    </div>
  );
}

/* Deliverable artifacts from sessions in this project (worktree publishes
   roll up to the repo-root card on the backend). Two kinds: "page" — hosted
   claude.ai pages from Claude Code's Artifact tool, linked externally with an
   inline preview of the local html source when it still exists; "document" —
   local docs like Antigravity's task/plan/walkthrough, linked into the session
   inspector and served raw via /artifacts?path=. */
export default function ArtifactsTab() {
  const pathname = usePathname();
  const { project } = useProject();
  const artifacts = project?.artifacts ?? [];

  // Default "cards"; read the persisted choice post-mount (SSR-safe, and the
  // effect-read avoids a hydration mismatch a lazy initializer would cause).
  const [view, setView] = useState<ViewMode>("cards");
  useEffect(() => {
    try {
      if (window.localStorage.getItem(VIEW_KEY) === "list") setView("list");
    } catch { /* storage unavailable — keep default */ }
  }, []);
  const changeView = (v: ViewMode) => {
    setView(v);
    try {
      window.localStorage.setItem(VIEW_KEY, v);
    } catch { /* non-fatal */ }
  };

  if (artifacts.length === 0) {
    return (
      <Card>
        <EmptyState
          icon={<Globe size={20} />}
          title="No artifacts"
          description="When an agent produces a deliverable artifact — Claude Code publishing a hosted page, or Antigravity writing a task list, implementation plan, or walkthrough — it shows up here."
        />
      </Card>
    );
  }

  const sessionHrefFor = (a: PublishedArtifact) =>
    a.session_id
      ? `/sessions/${a.session_id}?agent=${a.agent || "claude"}&tab=artifacts&from=${encodeURIComponent(pathname)}`
      : null;

  return (
    <div className="space-y-4">
      {/* View toggle */}
      <div className="flex justify-end">
        <div className="flex items-center rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-panel)] overflow-hidden">
          {([
            { v: "cards", icon: LayoutGrid, label: "Cards" },
            { v: "list",  icon: ListIcon,   label: "List"  },
          ] as { v: ViewMode; icon: typeof LayoutGrid; label: string }[]).map(({ v, icon: I, label }) => (
            <button
              key={v}
              onClick={() => changeView(v)}
              aria-label={label}
              title={label}
              className={cn(
                "h-7 w-8 grid place-items-center transition-colors",
                view === v ? "text-[var(--tt-brand)] tt-tint-1" : "text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)]",
              )}
            >
              <I size={13} />
            </button>
          ))}
        </div>
      </div>

      {view === "cards" ? (
        <div className="space-y-5">
          {artifacts.map((a) => (
            <ArtifactCard key={a.url || a.path} a={a} sessionHref={sessionHrefFor(a)} />
          ))}
        </div>
      ) : (
        <Card padding="none">
          <div className="divide-y divide-[var(--tt-border)]">
            {artifacts.map((a) => (
              <ArtifactRow key={a.url || a.path} a={a} sessionHref={sessionHrefFor(a)} />
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
