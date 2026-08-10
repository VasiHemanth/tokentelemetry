"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { format, formatDistanceToNow } from "date-fns";
import {
  AlertTriangle, ChevronDown, ExternalLink, RotateCcw,
  Search, SlidersHorizontal, X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useResource } from "@/lib/api";
import {
  buildHermesSessionsPath, formatHermesProject, type HermesSessionPage,
  type HermesSessionQuery, type HermesSessionSort,
} from "@/lib/hermesSessions";
import { formatCost, formatTokens } from "@/lib/format";
import { Badge, Button, Card, EmptyState, Skeleton } from "@/components/ui";
import SourceBadge from "@/components/SourceBadge";

const PAGE_SIZE = 50;
// The backend rejects page_size above 200, so that is the most rows this view can
// hold at once. Past it the filters are the way to narrow things down, which is
// why there is no page-by-page walk any more.
const MAX_ROWS = 200;

function readQuery(searchParams: { get(name: string): string | null }): HermesSessionQuery {
  const rawSort = searchParams.get("sort");
  const sort: HermesSessionSort = rawSort === "oldest" || rawSort === "cost" || rawSort === "tokens"
    ? rawSort
    : "newest";
  return {
    search: searchParams.get("search") || "",
    project: searchParams.get("project") || "",
    source: searchParams.get("source") || "",
    model: searchParams.get("model") || "",
    sort,
  };
}

export default function HermesSessionExplorer() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const query = useMemo(() => readQuery(searchParams), [searchParams]);
  const [searchInput, setSearchInput] = useState(query.search || "");

  useEffect(() => {
    const timer = window.setTimeout(() => setSearchInput(query.search || ""), 0);
    return () => window.clearTimeout(timer);
  }, [query.search]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (searchInput.trim() === (query.search || "").trim()) return;
      updateQuery({ search: searchInput.trim() || null });
    }, 300);
    return () => window.clearTimeout(timer);
  }, [searchInput]); // eslint-disable-line react-hooks/exhaustive-deps

  // How many rows to ask for. "Load more" grows this rather than walking pages,
  // so one request always returns the whole visible list and there is no page
  // number to fall out of sync with the results.
  const [rowLimit, setRowLimit] = useState(PAGE_SIZE);

  const path = useMemo(
    () => buildHermesSessionsPath({ ...query, page: 1, pageSize: rowLimit }),
    [query, rowLimit],
  );
  const { data, loading, error, refetch } = useResource<HermesSessionPage>(path, {
    pollMs: 15_000,
    initial: { sessions: [], pagination: { page: 1, page_size: PAGE_SIZE, total: 0, total_pages: 0 } },
  });

  const activeFilterCount = [query.project, query.source, query.model, query.search].filter(Boolean).length;

  function updateQuery(updates: Record<string, string | null>) {
    const next = new URLSearchParams(searchParams.toString());
    for (const [key, value] of Object.entries(updates)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    // Left over from the old paginated view; harmless in the URL but misleading.
    next.delete("page");
    // Any filter change re-scopes the list, so start from one screenful again.
    setRowLimit(PAGE_SIZE);
    const nextQuery = next.toString();
    router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname, { scroll: false });
  }

  function clearFilters() {
    setSearchInput("");
    updateQuery({ search: null, project: null, source: null, model: null, sort: null });
  }

  const sessions = data?.sessions ?? [];
  const total = data?.pagination.total ?? 0;
  // A larger limit than we have rows for means the wider request is still in
  // flight — useResource keeps serving the previous response until it lands.
  const loadingMore = rowLimit > sessions.length && sessions.length < total;
  const canLoadMore = sessions.length < total && rowLimit < MAX_ROWS;
  const cappedOut = rowLimit >= MAX_ROWS && total > sessions.length;
  const returnPath = searchParams.toString() ? `${pathname}?${searchParams.toString()}` : pathname;

  return (
    <div className="space-y-4">
      <Card padding="sm" tone="sunken">
        <div className="flex flex-wrap items-center gap-2">
          <label className="relative flex-1 min-w-[240px]">
            <span className="sr-only">Search Hermes sessions</span>
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--tt-fg-dim)]" />
            <input
              type="search"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder="Search messages, projects, models…"
              className="w-full h-9 pl-9 pr-3 rounded-[var(--tt-radius)] bg-[var(--tt-panel)] border border-[var(--tt-border)] text-[13px] text-[var(--tt-fg)] placeholder:text-[var(--tt-fg-dim)] focus:outline-none focus:border-[var(--tt-border-strong)]"
            />
          </label>
          <FilterInput label="Project" value={query.project || ""} onChange={(value) => updateQuery({ project: value || null })} />
          <FilterInput label="Source" value={query.source || ""} onChange={(value) => updateQuery({ source: value || null })} />
          <FilterInput label="Model" value={query.model || ""} onChange={(value) => updateQuery({ model: value || null })} />
          <select
            aria-label="Sort Hermes sessions"
            value={query.sort || "newest"}
            onChange={(event) => updateQuery({ sort: event.target.value === "newest" ? null : event.target.value })}
            className="h-9 rounded-[var(--tt-radius)] bg-[var(--tt-panel)] border border-[var(--tt-border)] px-2.5 text-[12px] text-[var(--tt-fg-muted)] focus:outline-none focus:border-[var(--tt-border-strong)]"
          >
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
            <option value="cost">Highest cost</option>
            <option value="tokens">Most tokens</option>
          </select>
          {activeFilterCount > 0 && (
            <Button variant="ghost" size="sm" onClick={clearFilters} title="Clear filters">
              <X size={13} /> Clear
            </Button>
          )}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-[var(--tt-fg-dim)]">
          <SlidersHorizontal size={12} />
          <span>{data ? `${data.pagination.total.toLocaleString()} sessions` : "Loading sessions…"}</span>
          {activeFilterCount > 0 && <Badge variant="brand" size="xs">{activeFilterCount} filters active</Badge>}
          <span className="ml-auto">Updated automatically</span>
        </div>
      </Card>

      {loading && sessions.length === 0 ? (
        <Card padding="none">
          <div className="p-5 space-y-3" aria-busy="true" aria-label="Loading Hermes sessions">
            {Array.from({ length: 8 }).map((_, index) => <Skeleton key={index} className="h-12 w-full" />)}
          </div>
        </Card>
      ) : error ? (
        <Card>
          <EmptyState
            icon={<AlertTriangle size={20} />}
            title="Could not load Hermes sessions"
            description={error.message}
            action={<Button onClick={refetch}><RotateCcw size={13} /> Try again</Button>}
          />
        </Card>
      ) : sessions.length === 0 ? (
        <Card><EmptyState title="No Hermes sessions match" description="Try clearing a filter or broadening your search." action={activeFilterCount > 0 ? <Button onClick={clearFilters}>Clear filters</Button> : undefined} /></Card>
      ) : (
        <Card padding="none" className="overflow-hidden">
          <div className="hidden md:grid grid-cols-[120px_minmax(140px,1fr)_minmax(140px,1.5fr)_minmax(100px,0.8fr)_110px_112px] gap-3 px-5 py-3 border-b border-[var(--tt-border)] text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--tt-fg-dim)]">
            <div>Source</div><div>Project</div><div>Message</div><div>Model</div><div className="text-right">Cost</div><div className="text-right">Time</div>
          </div>
          <div className="divide-y divide-[var(--tt-border)]">
            {sessions.map((session) => <HermesSessionRow key={session.id} session={session} returnPath={returnPath} />)}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3 border-t border-[var(--tt-border)] text-[11px] text-[var(--tt-fg-muted)]">
            <span>Showing {sessions.length.toLocaleString()} of {total.toLocaleString()}</span>
            {canLoadMore ? (
              <Button
                variant="ghost"
                size="sm"
                disabled={loadingMore}
                onClick={() => setRowLimit((limit) => Math.min(MAX_ROWS, limit + PAGE_SIZE))}
              >
                {loadingMore ? "Loading…" : <>Load more <ChevronDown size={14} /></>}
              </Button>
            ) : cappedOut ? (
              <span>Showing the first {MAX_ROWS} — narrow with filters to reach the rest</span>
            ) : null}
          </div>
        </Card>
      )}
    </div>
  );
}

function FilterInput({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="relative w-[132px]">
      <span className="sr-only">Filter by {label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={label}
        className="w-full h-9 rounded-[var(--tt-radius)] bg-[var(--tt-panel)] border border-[var(--tt-border)] px-2.5 text-[12px] text-[var(--tt-fg-muted)] placeholder:text-[var(--tt-fg-dim)] focus:outline-none focus:border-[var(--tt-border-strong)]"
      />
    </label>
  );
}

function HermesSessionRow({ session, returnPath }: { session: HermesSessionPage["sessions"][number]; returnPath: string }) {
  const href = `/sessions/${session.id}?agent=hermes&from=${encodeURIComponent(returnPath)}`;
  const message = session.display || session.text || "No message content";
  return (
    <Link href={href} className="group block px-5 py-3 hover:bg-[var(--tt-sunken)] transition-colors focus:outline-none focus:bg-[var(--tt-sunken)]">
      <div className="grid grid-cols-1 md:grid-cols-[120px_minmax(140px,1fr)_minmax(140px,1.5fr)_minmax(100px,0.8fr)_110px_112px] gap-2 md:gap-3 items-center text-[12px]">
        <div><SourceBadge source={session.source_subtype} size="xs" /></div>
        <div className="min-w-0">
          <div className="text-[var(--tt-fg)] truncate" title={session.project}>{formatHermesProject(session.project)}</div>
          <div className="text-[10px] text-[var(--tt-fg-dim)] truncate" title={session.project}>{session.project || "unknown"}</div>
        </div>
        <div className="min-w-0 text-[var(--tt-fg)] truncate" title={message}>
          {session.cost_anomaly && <AlertTriangle size={11} className="inline mr-1 text-[var(--tt-warn-fg)]" aria-label="Reasoning cost anomaly" />}
          {message}
        </div>
        <div className="font-mono text-[11px] text-[var(--tt-fg-muted)] truncate" title={session.model}>{session.model || "—"}</div>
        <div className="md:text-right tabular text-[var(--tt-fg-muted)]">
          {session.cost && session.cost > 0 ? formatCost(session.cost) : "—"}
          {session.tokens?.total ? <div className="text-[10px] text-[var(--tt-fg-dim)]">{formatTokens(session.tokens.total)} tok</div> : null}
        </div>
        <div className="md:text-right text-[11px] text-[var(--tt-fg-muted)]">
          <div>{formatDistanceToNow(new Date(session.timestamp), { addSuffix: true })}</div>
          <div className="text-[10px] text-[var(--tt-fg-dim)]">{format(new Date(session.timestamp), "MMM d, HH:mm")}</div>
        </div>
      </div>
      <div className="mt-1 flex items-center justify-end gap-1 text-[10px] text-[var(--tt-fg-dim)] opacity-0 group-hover:opacity-100 group-focus:opacity-100 transition-opacity">
        Open trace <ExternalLink size={10} />
      </div>
    </Link>
  );
}
