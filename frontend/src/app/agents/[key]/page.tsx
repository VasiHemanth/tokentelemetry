"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { formatDistanceToNow } from "date-fns";
import { ArrowLeft, ArrowRight, HardDrive } from "lucide-react";
import { useResource } from "@/lib/api";
import { AGENTS, type AgentKey } from "@/lib/agents";
import { AgentLogo } from "@/components/icons/AgentLogo";
import { Card, CardHeader, CardTitle, EmptyState, Skeleton } from "@/components/ui";
import { PanelSection } from "@/components/agents/PanelSection";
import { AgentPanel, PanelSection as Section, humanBytes } from "@/lib/agentPanel";

/**
 * One adaptive page per agent.
 *
 * Sections come back in value order and simply don't render when an agent lacks
 * them — Codex shows five cards, Vibe two. That's why this is a single page
 * rather than a tab bar: most agents would have too few sections to fill tabs,
 * and empty tabs read as broken.
 */

/**
 * Compact kinds go in the right rail; anything with a table or a tree takes the
 * main column.
 *
 * The first cut laid every section into one `grid-cols-2` and gave wide kinds
 * `col-span-2`. That guarantees holes — a narrow card followed by a wide one
 * leaves half a row empty, and Codex hit it on the very first section pair.
 * Two independent stacks cannot produce a gap.
 */
const RAIL_KINDS = new Set(["meter", "quota", "fields", "permissions", "chips", "tools"]);

/** Disk-bar ramp. Distinct hues so segments stay tellable apart, all from tokens. */
const DISK_COLORS = [
  "var(--tt-brand)",
  "var(--tt-violet-fg)",
  "var(--tt-cyan-fg)",
  "var(--tt-success-fg)",
  "var(--tt-warn-fg)",
  "var(--tt-info-fg)",
];

function SourceLine({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-4 pt-3 border-t border-[var(--tt-border)] font-mono text-[10px] text-[var(--tt-fg-muted)] break-all">
      <span className="opacity-50">source&nbsp;&nbsp;</span>{children}
    </div>
  );
}

/**
 * Sits above the section grid: it's the one figure every agent reports, which
 * makes it the anchor a reader can carry from one agent's page to the next.
 */
function DiskCard({ disk }: { disk: NonNullable<AgentPanel["disk"]> }) {
  const parts = disk.parts ?? [];
  const total = disk.total_bytes || 1;
  const shown = parts.reduce((a, p) => a + p.bytes, 0);
  const other = Math.max(0, disk.total_bytes - shown);

  return (
    <Card padding="md">
      <CardHeader>
        <CardTitle><HardDrive size={13} /> Disk footprint</CardTitle>
        {!!disk.reclaimable_bytes && (
          <span className="tabular font-mono text-[11px] text-[var(--tt-warn-fg)]">
            {humanBytes(disk.reclaimable_bytes)} reclaimable
          </span>
        )}
      </CardHeader>

      <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:gap-8">
        <div className="shrink-0 lg:w-[170px]">
          <div className="tabular text-[30px] leading-none font-semibold tracking-[-0.02em] text-[var(--tt-fg)]">
            {disk.total_human}
          </div>
          <div className="mt-1.5 text-[11px] leading-snug text-[var(--tt-fg-dim)]">
            {disk.complete === false
              ? "at least — the directory was big enough that the scan stopped early"
              : "on disk"}
          </div>
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex h-6 rounded-md overflow-hidden bg-[var(--tt-sunken)]">
            {parts.map((p, i) => (
              <div
                key={p.label}
                style={{
                  width: `${(p.bytes / total) * 100}%`,
                  background: DISK_COLORS[i % DISK_COLORS.length],
                }}
                title={`${p.label} — ${humanBytes(p.bytes)}`}
              />
            ))}
            {other > 0 && <div style={{ width: `${(other / total) * 100}%` }} />}
          </div>

          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 font-mono text-[10.5px] text-[var(--tt-fg-muted)]">
            {parts.map((p, i) => (
              <span key={p.label} className="flex items-center gap-1.5">
                <i
                  className="block h-2 w-2 rounded-[2px] shrink-0"
                  style={{ background: DISK_COLORS[i % DISK_COLORS.length] }}
                />
                {p.label}
                <span className="tabular text-[var(--tt-fg)]">{humanBytes(p.bytes)}</span>
              </span>
            ))}
          </div>
        </div>
      </div>

      {!!disk.reclaimable_bytes && disk.reclaimable_note && (
        <p className="mt-4 text-[11.5px] leading-relaxed text-[var(--tt-fg-muted)]">
          {disk.reclaimable_note}
        </p>
      )}

      <SourceLine>
        apparent file sizes, symlinks not followed — reads slightly under <code>du</code>
      </SourceLine>
    </Card>
  );
}

export default function AgentPanelPage() {
  const params = useParams<{ key: string }>();
  const key = String(params?.key ?? "");
  const meta = AGENTS[key as AgentKey];

  const { data, loading, error } = useResource<AgentPanel>(
    key ? `/agents/${encodeURIComponent(key)}/panel` : null,
  );

  const label = meta?.label ?? key;
  const hex = meta?.hex ?? "#888888";

  const sections: Section[] = data?.sections ?? [];
  const rail = sections.filter((s) => RAIL_KINDS.has(s.kind));
  const main = sections.filter((s) => !RAIL_KINDS.has(s.kind));

  return (
    <div className="px-8 py-8 max-w-[1600px] mx-auto space-y-8 pb-20">
      <header className="flex flex-wrap items-start justify-between gap-6 pb-6 border-b border-[var(--tt-border)]">
        <div className="flex items-start gap-4 min-w-0">
          <Link
            href="/"
            title="Back to agents"
            aria-label="Back to agents"
            className="mt-1 h-9 w-9 grid place-items-center rounded-[var(--tt-radius)] border border-[var(--tt-border)] text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] hover:tt-tint-1 transition-colors shrink-0"
          >
            <ArrowLeft size={16} />
          </Link>
          <span
            className="mt-0.5 grid h-10 w-10 place-items-center rounded-[var(--tt-radius)] border shrink-0"
            style={{ backgroundColor: `${hex}14`, borderColor: `${hex}33`, color: hex }}
          >
            <AgentLogo agent={key} size={20} />
          </span>
          <div className="min-w-0">
            <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-[var(--tt-fg-dim)] mb-1.5">
              Coding agent
            </div>
            <h1 className="text-[28px] leading-[1.05] font-semibold tracking-[-0.02em] text-[var(--tt-fg)]">
              {label}
            </h1>
            {data?.installed && (
              <div className="mt-2 flex flex-wrap items-center gap-x-2.5 gap-y-1 font-mono text-[11.5px] text-[var(--tt-fg-muted)]">
                {data.version && <span>v{data.version}</span>}
                {data.version && data.last_active && <span className="opacity-40">·</span>}
                {data.last_active && (
                  <span>
                    active {formatDistanceToNow(new Date(data.last_active), { addSuffix: true })}
                  </span>
                )}
                {sections.length > 0 && <span className="opacity-40">·</span>}
                {sections.length > 0 && (
                  <span>
                    {sections.length} {sections.length === 1 ? "panel" : "panels"}
                  </span>
                )}
              </div>
            )}
          </div>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-3">
          {data?.root && (
            <code className="rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-sunken)] px-2.5 py-1.5 font-mono text-[11.5px] text-[var(--tt-fg-muted)]">
              {data.root}
            </code>
          )}
          {/* Hermes keeps a whole sub-dashboard of its own. Rather than compete
              with it, the panel advertises it and hands the reader across. */}
          {data?.dashboard && (
            <Link
              href={data.dashboard.href}
              title={data.dashboard.hint}
              className="inline-flex items-center gap-2 rounded-[var(--tt-radius)] border border-[var(--tt-brand)] bg-[var(--tt-brand)]/10 px-3.5 py-2 text-[12.5px] font-medium text-[var(--tt-brand)] transition-colors hover:bg-[var(--tt-brand)]/20"
            >
              {data.dashboard.label}
              <ArrowRight size={13} />
            </Link>
          )}
        </div>
      </header>

      {data?.dashboard?.hint && (
        <p className="-mt-4 text-[12.5px] leading-relaxed text-[var(--tt-fg-muted)] max-w-[92ch]">
          {data.dashboard.hint}
        </p>
      )}

      {loading && (
        <div className="space-y-5">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      )}

      {error && (
        <EmptyState
          title="Could not read this agent"
          description="The backend could not build a panel for this agent. It stays read-only, so nothing was changed."
        />
      )}

      {!loading && !error && data && !data.installed && (
        <EmptyState
          title={data.planned ? `No panel for ${label} yet` : `${label} is not installed here`}
          description={
            data.planned
              ? `TokenTelemetry scans ${label} for sessions, but nothing reads its harness-specific stores yet. Its sessions still appear in traces and analytics.`
              : `No ${label} data directory was found on this machine.`
          }
        />
      )}

      {data?.installed && (
        <>
          {data.disk && <DiskCard disk={data.disk} />}

          {/* Three shapes, so a sparse agent never leaves an empty column: both
              stacks (the common case), main only, or the rail cards spread
              across the full width when there's no table for them to sit beside. */}
          {main.length > 0 && rail.length > 0 ? (
            <div className="grid gap-5 items-start lg:grid-cols-[minmax(0,1fr)_340px]">
              <div className="min-w-0 space-y-5">
                {main.map((s, i) => (
                  <PanelSection key={`m-${s.kind}-${i}`} section={s} />
                ))}
              </div>
              <div className="min-w-0 space-y-5">
                {rail.map((s, i) => (
                  <PanelSection key={`r-${s.kind}-${i}`} section={s} />
                ))}
              </div>
            </div>
          ) : main.length > 0 ? (
            <div className="space-y-5">
              {main.map((s, i) => (
                <PanelSection key={`m-${s.kind}-${i}`} section={s} />
              ))}
            </div>
          ) : rail.length > 0 ? (
            <div className="grid gap-5 items-start sm:grid-cols-2 xl:grid-cols-3">
              {rail.map((s, i) => (
                <div key={`r-${s.kind}-${i}`} className="min-w-0">
                  <PanelSection section={s} />
                </div>
              ))}
            </div>
          ) : null}

          {sections.length === 0 && (
            <EmptyState
              title={`Nothing extra on disk for ${label}`}
              description="This agent is installed, but keeps nothing beyond the session transcripts already shown in traces."
            />
          )}

          {data.not_available.length > 0 && (
            <div className="rounded-[var(--tt-radius-lg)] border border-dashed border-[var(--tt-border-strong)] p-5">
              <h2 className="text-[10px] font-semibold uppercase tracking-[0.2em] text-[var(--tt-fg-dim)]">
                Not available for {label}
              </h2>
              <ul className="mt-3 space-y-2.5">
                {data.not_available.map((na) => (
                  <li
                    key={na.kind}
                    className="text-[12.5px] leading-relaxed text-[var(--tt-fg-muted)] max-w-[92ch]"
                  >
                    <span className="font-mono text-[12px] text-[var(--tt-fg)]">{na.kind}</span>
                    {" — "}
                    {na.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}
