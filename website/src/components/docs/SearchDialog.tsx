"use client";

/**
 * Static Orama search dialog for the docs site.
 * Reads from /api/search (generated at build time by scripts/generate-search.mjs).
 * Uses the oramaStaticClient so no server route is required — compatible with
 * output: "export" (GitHub Pages static hosting).
 */
import { oramaStaticClient } from "fumadocs-core/search/client/orama-static";
import { useDocsSearch } from "fumadocs-core/search/client";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const client = oramaStaticClient({ from: "/api/search" });

export default function StaticSearchDialog({ open, onOpenChange }: Props) {
  const { search, setSearch, query } = useDocsSearch({ client });
  const results = query.data;

  if (!open) return null;

  return (
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Search documentation"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 100,
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "center",
        paddingTop: "15vh",
        background: "rgba(0,0,0,0.6)",
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onOpenChange(false);
      }}
    >
      <div
        style={{
          background: "var(--tt-panel, #11141a)",
          border: "1px solid var(--tt-border, rgba(255,255,255,0.06))",
          borderRadius: "14px",
          width: "min(600px, 90vw)",
          overflow: "hidden",
          boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
        }}
      >
        <input
          autoFocus
          type="search"
          placeholder="Search docs…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Escape" && onOpenChange(false)}
          style={{
            width: "100%",
            padding: "1rem 1.25rem",
            background: "transparent",
            border: "none",
            borderBottom: "1px solid var(--tt-border, rgba(255,255,255,0.06))",
            color: "var(--tt-fg, #e8eaf0)",
            fontSize: "1rem",
            outline: "none",
            boxSizing: "border-box",
          }}
        />
        {results !== "empty" && Array.isArray(results) && results.length > 0 && (
          <ul style={{ listStyle: "none", margin: 0, padding: "0.5rem 0", maxHeight: "60vh", overflowY: "auto" }}>
            {results.map((item) => (
              <li key={item.id}>
                <a
                  href={item.url}
                  onClick={() => onOpenChange(false)}
                  style={{
                    display: "block",
                    padding: "0.625rem 1.25rem",
                    color: "var(--tt-fg, #e8eaf0)",
                    textDecoration: "none",
                    fontSize: "0.9rem",
                  }}
                >
                  {String(item.content)}
                </a>
              </li>
            ))}
          </ul>
        )}
        {results === "empty" && search.length > 0 && (
          <p style={{ padding: "1rem 1.25rem", color: "var(--tt-fg-muted, #9aa1ad)", fontSize: "0.9rem" }}>
            No results for &ldquo;{search}&rdquo;
          </p>
        )}
      </div>
    </div>
  );
}
