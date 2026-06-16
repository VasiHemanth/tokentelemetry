"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import rawResources from "../../../content/resources.json";

type Resource = {
  title: string;
  author: string;
  url: string;
  summary: string;
  tags: string[];
};

const RESOURCES: Resource[] = rawResources as Resource[];

const ALL_TAGS = ["skill", "hook", "mcp", "workflow", "guide"] as const;
type Tag = (typeof ALL_TAGS)[number];

const TAG_COLORS: Record<Tag, string> = {
  skill: "bg-[color-mix(in_srgb,var(--tt-brand)_12%,transparent)] border-[color-mix(in_srgb,var(--tt-brand)_30%,transparent)] text-[var(--tt-brand)]",
  hook: "bg-[color-mix(in_srgb,#a78bfa_12%,transparent)] border-[color-mix(in_srgb,#a78bfa_30%,transparent)] text-[#a78bfa]",
  mcp: "bg-[color-mix(in_srgb,#34d399_12%,transparent)] border-[color-mix(in_srgb,#34d399_30%,transparent)] text-[#34d399]",
  workflow: "bg-[color-mix(in_srgb,#fb923c_12%,transparent)] border-[color-mix(in_srgb,#fb923c_30%,transparent)] text-[#fb923c]",
  guide: "bg-[color-mix(in_srgb,#f472b6_12%,transparent)] border-[color-mix(in_srgb,#f472b6_30%,transparent)] text-[#f472b6]",
};

const TAG_COLORS_ACTIVE: Record<Tag, string> = {
  skill: "bg-[var(--tt-brand)] border-[var(--tt-brand)] text-white",
  hook: "bg-[#a78bfa] border-[#a78bfa] text-white",
  mcp: "bg-[#34d399] border-[#34d399] text-white",
  workflow: "bg-[#fb923c] border-[#fb923c] text-white",
  guide: "bg-[#f472b6] border-[#f472b6] text-white",
};

function TagChip({
  tag,
  active,
  onClick,
}: {
  tag: Tag;
  active: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center h-[22px] px-2 rounded-[5px] border text-[10.5px] font-semibold tracking-wide uppercase transition-colors ${
        active ? TAG_COLORS_ACTIVE[tag] : TAG_COLORS[tag]
      } ${onClick ? "cursor-pointer hover:opacity-80" : "cursor-default"}`}
    >
      {tag}
    </button>
  );
}

function ResourceCard({ resource }: { resource: Resource }) {
  return (
    <div className="flex flex-col p-5 rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] hover:border-[var(--tt-border-strong)] hover:bg-[var(--tt-raised)] hover:-translate-y-0.5 transition-all">
      <a
        href={resource.url}
        target="_blank"
        rel="noopener noreferrer"
        className="text-[15px] font-semibold tracking-[-0.01em] text-[var(--tt-fg)] hover:text-[var(--tt-brand)] transition-colors leading-snug mb-1"
      >
        {resource.title}
        <span className="ml-1.5 text-[11px] font-normal text-[var(--tt-fg-dim)] align-middle">↗</span>
      </a>

      <p className="text-[11.5px] font-mono text-[var(--tt-fg-dim)] mb-3">by {resource.author}</p>

      <p className="text-[13.5px] text-[var(--tt-fg-muted)] leading-relaxed flex-1 mb-4">
        {resource.summary}
      </p>

      <div className="flex flex-wrap gap-1.5 mt-auto">
        {resource.tags.map((tag) => (
          <TagChip key={tag} tag={tag as Tag} active={false} />
        ))}
      </div>
    </div>
  );
}

export default function ResourcesClient() {
  const [activeTags, setActiveTags] = useState<Set<Tag>>(new Set());
  const [query, setQuery] = useState("");

  function toggleTag(tag: Tag) {
    setActiveTags((prev) => {
      const next = new Set(prev);
      if (next.has(tag)) next.delete(tag);
      else next.add(tag);
      return next;
    });
  }

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return RESOURCES.filter((r) => {
      const matchesTags =
        activeTags.size === 0 || r.tags.some((t) => activeTags.has(t as Tag));
      const matchesQuery =
        q === "" ||
        r.title.toLowerCase().includes(q) ||
        r.summary.toLowerCase().includes(q) ||
        r.author.toLowerCase().includes(q);
      return matchesTags && matchesQuery;
    });
  }, [activeTags, query]);

  return (
    <main className="max-w-[1180px] mx-auto px-5 sm:px-8 py-16 sm:py-24">
      {/* Header */}
      <div className="max-w-[680px]">
        <p className="text-[12px] font-mono uppercase tracking-[0.18em] text-[var(--tt-fg-dim)]">
          Community
        </p>
        <h1 className="mt-2 text-[30px] sm:text-[44px] leading-[1.08] tracking-[-0.025em] font-semibold text-[var(--tt-fg)]">
          Resources
        </h1>
        <p className="mt-3 text-[15.5px] text-[var(--tt-fg-muted)] leading-relaxed max-w-[520px]">
          Curated guides, MCP servers, hooks, and workflow patterns for building
          with AI coding agents.
        </p>
      </div>

      {/* Filters */}
      <div className="mt-10 flex flex-col sm:flex-row gap-3 sm:items-center">
        {/* Search */}
        <div className="relative flex-1 max-w-[360px]">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--tt-fg-dim)] pointer-events-none">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="6.5" cy="6.5" r="5" />
              <path d="M10.5 10.5l4 4" />
            </svg>
          </span>
          <input
            type="search"
            placeholder="Search resources…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full h-[38px] pl-9 pr-3 rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-panel)] text-[13.5px] text-[var(--tt-fg)] placeholder:text-[var(--tt-fg-dim)] focus:outline-none focus:border-[var(--tt-border-strong)] transition-colors"
          />
        </div>

        {/* Tag filter chips */}
        <div className="flex flex-wrap gap-1.5">
          {ALL_TAGS.map((tag) => (
            <TagChip
              key={tag}
              tag={tag}
              active={activeTags.has(tag)}
              onClick={() => toggleTag(tag)}
            />
          ))}
          {activeTags.size > 0 && (
            <button
              type="button"
              onClick={() => setActiveTags(new Set())}
              className="inline-flex items-center h-[22px] px-2 rounded-[5px] border border-[var(--tt-border)] bg-[var(--tt-panel)] text-[10.5px] font-medium text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] transition-colors"
            >
              clear
            </button>
          )}
        </div>
      </div>

      {/* Results count */}
      <p className="mt-4 text-[12px] text-[var(--tt-fg-dim)]">
        {filtered.length} {filtered.length === 1 ? "resource" : "resources"}
        {activeTags.size > 0 || query ? " matching filters" : ""}
      </p>

      {/* Grid */}
      {filtered.length > 0 ? (
        <div className="mt-6 grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {filtered.map((r) => (
            <ResourceCard key={r.url} resource={r} />
          ))}
        </div>
      ) : (
        <div className="mt-12 text-center py-16 rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)]">
          <p className="text-[15px] text-[var(--tt-fg-muted)]">No resources match your filters.</p>
          <button
            type="button"
            onClick={() => { setActiveTags(new Set()); setQuery(""); }}
            className="mt-3 text-[13px] text-[var(--tt-brand)] hover:opacity-80 transition-opacity"
          >
            Clear filters
          </button>
        </div>
      )}

      {/* Footer note */}
      <div className="mt-14 pt-8 border-t border-[var(--tt-border)] flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <p className="text-[13px] text-[var(--tt-fg-dim)]">
          Community submissions coming soon —{" "}
          <a
            href="https://github.com/VasiHemanth/tokentelemetry"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[var(--tt-fg-muted)] underline underline-offset-2 hover:text-[var(--tt-brand)] transition-colors"
          >
            open a PR
          </a>{" "}
          to add your resource.
        </p>
        <Link
          href="/"
          className="text-[13px] text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] transition-colors"
        >
          ← Back to home
        </Link>
      </div>
    </main>
  );
}
