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
          <dd className="flex flex-col items-end gap-1 text-right">
            <span className="flex items-center gap-2 font-mono text-[12.5px] text-[var(--tt-fg)]">
              {cellText(f.value)}
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

function Tree({ section }: { section: Section }) {
  return (
    <div className="font-mono text-[12px] leading-[1.85] overflow-x-auto">
      {(section.tree ?? []).map((node, i) => (
        <div key={i} className={i > 0 ? "mt-3" : undefined}>
          <div className="text-[var(--tt-fg)]">{node.label}</div>
          {(node.children ?? []).map((c, j, arr) => (
            <div key={j} className="text-[var(--tt-fg-muted)] whitespace-nowrap">
              <span className="opacity-40">{j === arr.length - 1 ? "└─ " : "├─ "}</span>
              {c.label}
              {c.status && <span className="opacity-50"> · {c.status}</span>}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function Rows({ section }: { section: Section }) {
  const cols = section.columns ?? [];
  return (
    <div className="-mx-5 overflow-x-auto">
      <Table>
        <THead>
          <TR>
            {cols.map((c) => (
              <TH key={c} className={isNumericColumn(c) ? "text-right" : undefined}>{c}</TH>
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
                    <TD key={j}>
                      {cell ? <Badge variant="success">yes</Badge>
                            : <span className="text-[var(--tt-fg-muted)]">—</span>}
                    </TD>
                  );
                }
                return (
                  <TD
                    key={j}
                    className={
                      numeric
                        ? "tabular text-right font-mono text-[12px]"
                        : "font-mono text-[12px] max-w-[280px] truncate"
                    }
                    title={typeof cell === "string" ? cell : undefined}
                  >
                    {isDateColumn(col) ? relative(cell) : cellText(cell)}
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
