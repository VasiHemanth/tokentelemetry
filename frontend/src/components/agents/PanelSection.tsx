"use client";

import { formatDistanceToNow } from "date-fns";
import { AlertTriangle } from "lucide-react";
import {
  Card, CardHeader, CardTitle, Badge, Table, THead, TBody, TR, TH, TD,
} from "@/components/ui";
import {
  PanelSection as Section, PanelMeter, Severity,
  cellText, isDateColumn, isNumericColumn,
} from "@/lib/agentPanel";

/**
 * One renderer for every section a harness panel can produce.
 *
 * The backend decides `kind`; this file decides how each kind looks. Adding an
 * agent needs no change here — only a new `kind` does.
 */

const SEVERITY_VARIANT: Record<Severity, "success" | "warn" | "danger"> = {
  ok: "success", warn: "warn", crit: "danger",
};

/** Bar colour per severity. Semantic, deliberately not the brand accent. */
const METER_COLOR: Record<Severity, string> = {
  ok: "var(--tt-success-fg)",
  warn: "var(--tt-warn-fg)",
  crit: "var(--tt-danger-fg)",
};

function relative(value: unknown): string {
  if (typeof value !== "string" || !value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return formatDistanceToNow(d, { addSuffix: true });
}

/**
 * A timestamp is worth rendering as a timestamp even when its column isn't
 * named like one. Vibe keys a session by its start time, so the column is
 * "session" and the value is a raw `2026-04-08T00:29:49.155009` — and its
 * "log last written" field wrapped onto two lines in the rail. Matching the
 * value rather than the column heading catches both.
 */
const ISO_LIKE = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/;

function looksIso(value: unknown): value is string {
  return typeof value === "string" && ISO_LIKE.test(value);
}

/** "source ~/.codex/config.toml" — always shown, so a claim can be checked. */
function SourceLine({ source }: { source: string }) {
  return (
    <div className="mt-3 pt-3 border-t border-[var(--tt-border)] font-mono text-[10px] text-[var(--tt-fg-muted)] break-all">
      <span className="opacity-50">source&nbsp;&nbsp;</span>{source}
    </div>
  );
}

function Note({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-3 text-[11.5px] leading-relaxed text-[var(--tt-fg-muted)]">{children}</p>
  );
}

function Meter({ m }: { m: PanelMeter }) {
  const sev = m.severity ?? "ok";
  // A cached quota snapshot can outlive the window it describes — Claude Code
  // refreshes `cachedUsageUtilization` only when the CLI next calls the API, so
  // a 74-hour-old cache would otherwise render "resets 3 days ago", which reads
  // as broken. Past the reset point the percentage is history, not status.
  const resetAt = m.resets_at ? new Date(m.resets_at) : null;
  const elapsed = !!resetAt && !Number.isNaN(resetAt.getTime()) && resetAt.getTime() < Date.now();
  return (
    <div className="py-3 first:pt-0 last:pb-0 border-b border-[var(--tt-border)] last:border-b-0">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[11.5px] text-[var(--tt-fg-muted)]">{m.label}</span>
        <span
          className="tabular font-mono text-[19px] font-semibold tracking-tight"
          style={{ color: elapsed ? "var(--tt-fg-muted)" : METER_COLOR[sev] }}
        >
          {m.pct}%
        </span>
      </div>
      <div
        className="mt-2 h-2 rounded-full overflow-hidden bg-[var(--tt-sunken)]"
        role="progressbar"
        aria-valuenow={m.pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={m.label}
      >
        <div
          className="h-full rounded-full transition-[width] duration-500"
          style={{
            width: `${m.pct}%`,
            background: elapsed ? "var(--tt-border-strong)" : METER_COLOR[sev],
          }}
        />
      </div>
      {(m.detail || m.resets_at) && (
        <div className="mt-2 flex justify-between gap-3 font-mono text-[10.5px] text-[var(--tt-fg-muted)]">
          <span>{m.detail ?? ""}</span>
          {m.resets_at && (
            <span>
              {elapsed
                ? `window closed ${relative(m.resets_at)} — figure is stale`
                : `resets ${relative(m.resets_at)}`}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function Fields({ section }: { section: Section }) {
  return (
    <dl className="divide-y divide-[var(--tt-border)]">
      {(section.fields ?? []).map((f) => (
        <div key={f.label} className="flex items-start justify-between gap-4 py-2.5 first:pt-0 last:pb-0">
          <dt className="font-mono text-[10.5px] uppercase tracking-[0.09em] text-[var(--tt-fg-muted)] whitespace-nowrap pt-0.5">
            {f.label}
          </dt>
          <dd className="flex flex-col items-end gap-1 text-right min-w-0">
            <span
              className="flex items-center gap-2 font-mono text-[12.5px] text-[var(--tt-fg)]"
              title={looksIso(f.value) ? String(f.value) : undefined}
            >
              {looksIso(f.value) ? relative(f.value) : cellText(f.value)}
              {f.severity && (
                <Badge variant={SEVERITY_VARIANT[f.severity]}>
                  {f.severity === "crit" ? "risk" : f.severity}
                </Badge>
              )}
            </span>
            {f.hint && (
              <span className="text-[10.5px] text-[var(--tt-fg-muted)] max-w-[34ch]">{f.hint}</span>
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function Chips({ section }: { section: Section }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {(section.rows ?? []).map((r, i) => (
        <Badge key={i} variant="outline" size="sm">{cellText(r[0])}</Badge>
      ))}
    </div>
  );
}

/**
 * Codex titles a spawned thread with the message that spawned it, so a parent
 * that fanned out six children renders six byte-identical rows. Collapsing
 * repeats into one row with a count says the same thing and reads as
 * deliberate, where the repeat read as a render bug.
 */
function foldChildren(children: { label: string; status?: string | null }[]) {
  const order: { label: string; status?: string | null; n: number }[] = [];
  const seen = new Map<string, { n: number }>();
  for (const c of children) {
    // The backend already renders an absent title as an em dash, so testing
    // for an empty string alone leaves rows reading "— ×5".
    const raw = String(c.label ?? "").trim();
    const label = !raw || raw === "—" || raw === "-" ? "untitled" : raw;
    const key = `${label}\u0000${c.status ?? ""}`;
    const hit = seen.get(key);
    if (hit) {
      hit.n += 1;
      continue;
    }
    const row = { label, status: c.status, n: 1 };
    seen.set(key, row);
    order.push(row);
  }
  return order;
}

function Tree({ section }: { section: Section }) {
  return (
    <div className="font-mono text-[12px] leading-[1.85]">
      {(section.tree ?? []).map((node, i) => {
        const kids = foldChildren(node.children ?? []);
        return (
          <div key={i} className={i > 0 ? "mt-3" : undefined}>
            <div className="text-[var(--tt-fg)] truncate" title={node.label}>{node.label}</div>
            {kids.map((c, j) => (
              <div
                key={j}
                className="flex items-baseline gap-1.5 text-[var(--tt-fg-muted)]"
              >
                <span className="opacity-40 shrink-0">
                  {j === kids.length - 1 ? "└─" : "├─"}
                </span>
                <span className="truncate" title={c.label}>{c.label}</span>
                {c.n > 1 && (
                  <span className="shrink-0 tabular text-[var(--tt-fg)] opacity-80">×{c.n}</span>
                )}
                {c.status && <span className="shrink-0 opacity-50">· {c.status}</span>}
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

function Rows({ section }: { section: Section }) {
  const cols = section.columns ?? [];

  // Without this every column shares the width equally, so OpenCode's four
  // short columns (name / vcs / sandboxes / updated) spread across the whole
  // card with a hand-span of dead air between each one. Let the first label
  // column absorb the slack and make the rest shrink to their content: `w-px`
  // plus `whitespace-nowrap` is the standard trick — the browser treats the
  // 1px as a floor and grows the cell only as far as the text needs.
  const growIdx = Math.max(
    0,
    cols.findIndex((c) => !isNumericColumn(c) && !isDateColumn(c)),
  );
  const widthFor = (i: number) => (i === growIdx ? "w-full" : "w-px whitespace-nowrap");

  return (
    <div className="-mx-5 overflow-x-auto [&_th:first-child]:pl-5 [&_td:first-child]:pl-5 [&_th:last-child]:pr-5 [&_td:last-child]:pr-5">
      <Table>
        <THead>
          <TR>
            {cols.map((c, i) => (
              <TH
                key={c}
                className={`${widthFor(i)}${isNumericColumn(c) ? " text-right" : ""}`}
              >
                {c}
              </TH>
            ))}
          </TR>
        </THead>
        <TBody>
          {(section.rows ?? []).map((row, i) => (
            <TR key={i}>
              {row.map((cell, j) => {
                const col = cols[j] ?? "";
                const numeric = isNumericColumn(col);
                // Booleans in a table are always a state flag (live, archived),
                // so they read better as a pill than as the word "Yes".
                if (typeof cell === "boolean") {
                  return (
                    <TD key={j} className={widthFor(j)}>
                      {cell ? <Badge variant="success">yes</Badge>
                            : <span className="text-[var(--tt-fg-muted)]">—</span>}
                    </TD>
                  );
                }
                return (
                  <TD
                    key={j}
                    className={
                      j === growIdx
                        ? "font-mono text-[12px] max-w-[560px] truncate"
                        : numeric
                          ? "w-px whitespace-nowrap tabular text-right font-mono text-[12px]"
                          // Capped, not nowrap: Claude's "links" cell can hold
                          // four PR references, and left to run it pushed the
                          // last column clean off the right edge of the card.
                          : "w-px max-w-[240px] truncate font-mono text-[12px] text-[var(--tt-fg-muted)]"
                    }
                    title={typeof cell === "string" ? cell : undefined}
                  >
                    {isDateColumn(col) || looksIso(cell) ? relative(cell) : cellText(cell)}
                  </TD>
                );
              })}
            </TR>
          ))}
        </TBody>
      </Table>
    </div>
  );
}

export function PanelSection({ section }: { section: Section }) {
  const { kind } = section;
  const isMeter = kind === "meter" || kind === "quota";
  const isFields = kind === "fields" || kind === "permissions";
  const isChips = kind === "chips" || kind === "tools";
  const isTree = kind === "tree" || kind === "subagents";

  // "Installed but empty" is a real answer, not a missing section: the store
  // exists and the user could fill it. Saying so beats hiding the card, which
  // would imply the capability doesn't exist.
  const empty = section.empty_reason && !(section.rows ?? []).length;

  const headline = (() => {
    if (section.count !== undefined && section.total !== undefined && section.total !== section.count) {
      return `${section.count} of ${section.total}`;
    }
    if (section.count !== undefined) return String(section.count);
    if (section.total !== undefined) return String(section.total);
    return null;
  })();

  return (
    <Card padding="md">
      <CardHeader>
        <CardTitle>
          {section.title}
          {section.severity === "crit" && (
            <AlertTriangle size={13} className="text-[var(--tt-danger-fg)]" aria-label="Needs attention" />
          )}
        </CardTitle>
        {headline && (
          <span className="tabular font-mono text-[11px] text-[var(--tt-fg-muted)]">{headline}</span>
        )}
      </CardHeader>

      {empty ? (
        <p className="py-6 text-center text-[12.5px] text-[var(--tt-fg-muted)] max-w-[62ch] mx-auto">
          {section.empty_reason}
        </p>
      ) : isMeter ? (
        <>
          <div>{(section.meters ?? []).map((m, i) => <Meter key={i} m={m} />)}</div>
          {section.fields?.length ? <div className="mt-3"><Fields section={section} /></div> : null}
        </>
      ) : isFields ? (
        <Fields section={section} />
      ) : isChips ? (
        <Chips section={section} />
      ) : isTree ? (
        <Tree section={section} />
      ) : (
        <Rows section={section} />
      )}

      {section.note && <Note>{section.note}</Note>}
      <SourceLine source={section.source} />
    </Card>
  );
}
