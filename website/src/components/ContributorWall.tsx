import data from "@/data/contributors.json";

export const CONTRIBUTING_URL = "https://github.com/VasiHemanth/tokentelemetry/blob/main/CONTRIBUTING.md";

type Role = "code" | "pr" | "issue" | "discussion";

export interface Contributor {
  login: string;
  role: Role;
  commits: number;
  merged_prs: number;
  open_or_closed_prs: number;
  issues: number;
  discussions: number;
  avatar: string;
}

export const contributors = data.contributors as Contributor[];
export const contributorCounts = {
  total: data.total,
  code: data.counts.code ?? 0,
};

function plural(n: number, word: string) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

/** Hover text, e.g. "hwantage: 16 commits, 10 merged PRs, 11 issues". */
function describe(p: Contributor) {
  const parts = [
    p.commits && plural(p.commits, "commit"),
    p.merged_prs && plural(p.merged_prs, "merged PR"),
    p.open_or_closed_prs && plural(p.open_or_closed_prs, "other PR"),
    p.issues && plural(p.issues, "issue"),
    p.discussions && plural(p.discussions, "discussion post"),
  ].filter(Boolean);
  return `${p.login}: ${parts.join(", ")}`;
}

// Cells skipped at the start of each row (right-aligned wall) give the ragged
// edge; a few faint empty rings mixed into the rows keep it from reading as a
// plain table. Both are fixed patterns so server and client render the same.
const LEAD_BLANKS = [2, 1, 3, 0, 2, 1, 0, 3];
const isGhost = (slot: number) => slot % 11 === 4 || slot % 13 === 9;

type Cell = { kind: "person"; p: Contributor } | { kind: "ghost" } | { kind: "blank" };

function layout(people: Contributor[], columns: number, ragged: boolean): Cell[] {
  const cells: Cell[] = [];
  let next = 0;
  let slot = 0;
  for (let row = 0; next < people.length; row++) {
    const lead = ragged ? Math.min(LEAD_BLANKS[row % LEAD_BLANKS.length], columns - 1) : 0;
    for (let col = 0; col < columns; col++) {
      if (col < lead) cells.push({ kind: "blank" });
      else if (next >= people.length) cells.push({ kind: "blank" });
      else if (isGhost(slot++)) cells.push({ kind: "ghost" });
      else cells.push({ kind: "person", p: people[next++] });
    }
  }
  return cells;
}

export default function ContributorWall({
  columns,
  size,
  ragged = true,
  className = "",
}: {
  columns: number;
  size: number;
  ragged?: boolean;
  className?: string;
}) {
  const cells = layout(contributors, columns, ragged);
  const gap = Math.round(size * 0.22);

  return (
    <ul
      aria-label={`${contributorCounts.total} contributors`}
      className={`grid w-fit ${className}`}
      style={{ gridTemplateColumns: `repeat(${columns}, ${size}px)`, gap }}
    >
      {cells.map((cell, i) => {
        if (cell.kind === "blank") return <li key={i} aria-hidden style={{ width: size, height: size }} />;
        if (cell.kind === "ghost") {
          return (
            <li key={i} aria-hidden className="rounded-full border border-[var(--tt-border-strong)]"
              style={{ width: size, height: size }} />
          );
        }
        const { p } = cell;
        const code = p.role === "code";
        return (
          <li key={p.login} style={{ width: size, height: size }}>
            <a
              href={`https://github.com/${p.login}`}
              target="_blank"
              rel="noopener noreferrer"
              title={describe(p)}
              aria-label={describe(p)}
              className={`block h-full w-full overflow-hidden rounded-full bg-[var(--tt-raised)] transition-transform duration-150 hover:scale-110 hover:z-10 focus-visible:scale-110 ${
                code
                  ? "ring-2 ring-[var(--tt-brand)] ring-offset-2 ring-offset-[var(--tt-canvas)]"
                  : "ring-1 ring-[var(--tt-border-strong)]"
              }`}
            >
              {/* Plain img: the site is a static export with unoptimized images,
                  and the avatars are already resized to 96px at fetch time. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={p.avatar} alt="" width={size} height={size} loading="lazy" decoding="async"
                className="h-full w-full object-cover" />
            </a>
          </li>
        );
      })}
    </ul>
  );
}
