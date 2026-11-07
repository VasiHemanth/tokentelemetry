"use client";

import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import type { Event } from "@/lib/traceEvents";

const PAGE_SIZE = 80;

export default function EventLog({ events, selected, onSelect }: { events: Event[]; selected: Event | null; onSelect: (event: Event) => void }) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  // Search record types and roles without serializing large source payloads.
  const rows = useMemo(() => events.map((event, index) => ({ event, index })).filter(({ event }) => `${event.type} ${event.role || event.message?.role || ""} ${event.payload?.type || ""}`.toLowerCase().includes(query.toLowerCase())), [events, query]);
  const last = Math.max(0, Math.ceil(rows.length / PAGE_SIZE) - 1);
  const current = Math.min(page, last);
  return (
    <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden" aria-label="Recorded event log">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--tt-border)] px-4 py-3"><label className="flex items-center gap-2 text-xs text-[var(--tt-fg-muted)]"><Search size={14} /><span className="sr-only">Filter event types</span><input aria-label="Filter event types" value={query} onChange={e => { setQuery(e.target.value); setPage(0); }} placeholder="Filter event types…" className="min-w-0 rounded-md border border-[var(--tt-border)] bg-[var(--tt-sunken)] px-3 py-2 text-sm text-[var(--tt-fg)]" /></label><span className="text-xs text-[var(--tt-fg-muted)]">{rows.length.toLocaleString()} of {events.length.toLocaleString()} source records</span></div>
      <div className="min-h-0 flex-1 overflow-y-auto scrollbar-thin">{rows.slice(current * PAGE_SIZE, (current + 1) * PAGE_SIZE).map(({ event, index }) => <button key={index} type="button" onClick={() => onSelect(event)} aria-pressed={selected === event} className={`flex w-full items-center gap-4 border-b border-[var(--tt-border)] px-4 py-3 text-left text-sm hover:bg-[var(--tt-raised)] ${selected === event ? "bg-[var(--tt-brand-glow)]" : ""}`}><span className="w-14 shrink-0 font-mono text-xs tabular-nums text-[var(--tt-fg-muted)]">{index + 1}</span><span className="min-w-0 flex-1 break-words text-[var(--tt-fg)]">{event.type || "unknown"}{event.payload?.type ? ` / ${event.payload.type}` : ""}</span><span className="shrink-0 text-xs text-[var(--tt-fg-muted)]">{event.role || event.message?.role || "metadata"}</span></button>)}{!rows.length && <p className="p-6 text-sm text-[var(--tt-fg-muted)]">No records match this type.</p>}</div>
      <div className="flex items-center justify-between gap-3 border-t border-[var(--tt-border)] px-4 py-3 text-xs text-[var(--tt-fg-muted)]"><button type="button" disabled={!current} onClick={() => setPage(current - 1)} aria-label="Previous event page" className="rounded border border-[var(--tt-border)] p-2 disabled:opacity-40"><ChevronLeft size={14} /></button><span>Page {current + 1} of {last + 1} · API record order</span><button type="button" disabled={current === last} onClick={() => setPage(current + 1)} aria-label="Next event page" className="rounded border border-[var(--tt-border)] p-2 disabled:opacity-40"><ChevronRight size={14} /></button></div>
    </section>
  );
}
