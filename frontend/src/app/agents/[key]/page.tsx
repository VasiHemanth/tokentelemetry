"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { formatDistanceToNow } from "date-fns";
import { ArrowLeft, HardDrive } from "lucide-react";
import { useResource } from "@/lib/api";
import { AGENTS, getAgent, type AgentKey } from "@/lib/agents";
import { AgentLogo } from "@/components/icons/AgentLogo";
import { Card, CardHeader, CardTitle, EmptyState, Skeleton, Badge } from "@/components/ui";
import { PanelSection } from "@/components/agents/PanelSection";
import { AgentPanel, humanBytes } from "@/lib/agentPanel";

/**
 * One adaptive page per agent.
 *
 * Sections come back in value order and simply don't render when an agent lacks
 * them — Codex shows five or six cards, Vibe two. That's why this is a single
 * page rather than a tab bar: most agents would have too few sections to fill
 * tabs, and empty tabs read as broken.
 */

/** Palette for the disk bar. Neutral ramp, not semantic — size isn't a verdict. */
const DISK_COLORS = [
  "var(--tt-brand)",
  "var(--tt-fg-muted)",
  "var(--tt-info-fg)",
  "var(--tt-success-fg)",
  "var(--tt-warn-fg)",
  "var(--tt-border-strong)",
];

function DiskCard({ disk }: { disk: NonNullable<AgentPanel["disk"]> }) {
  const parts = disk.parts ?? [];
  const total = disk.total_bytes || 1;
  const shown = parts.reduce((a, p) => a + p.bytes, 0);
  const other = Math.max(0, disk.total_bytes - shown);

  return (
    <Card padding="md">
      <CardHeader>
        <CardTitle><HardDrive size={13} /> Disk footprint</CardTitle>
        <span className="tabular font-mono text-[11px] text-[var(--tt-fg-muted)]">
          {disk.total_human}
          {disk.complete === false && <span className="opacity-60"> or more</span>}
        </span>
      </CardHeader>

      <div className="flex h-5 rounded-md overflow-hidden bg-[var(--tt-sunken)]">
        {parts.map((p, i) => (
          <div
            key={p.label}
            style={{ width: `${(p.bytes / total) * 100}%`, background: DISK_COLORS[i % DISK_COLORS.length] }}
            title={`${p.label} — ${humanBytes(p.bytes)}`}
          />
        ))}
        {other > 0 && <div style={{ width: `${(other / total) * 100}%` }} />}
      </div>

      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 font-mono text-[10.5px] text-[var(--tt-fg-muted)]">
        {parts.map((p, i) => (
          <span key={p.label} className="flex items-center gap-1.5">
            <i
              className="block h-2 w-2 rounded-[2px]"
              style={{ background: DISK_COLORS[i % DISK_COLORS.length] }}
            />
            {p.label} {humanBytes(p.bytes)}
          </span>
        ))}
      </div>

      {!!disk.reclaimable_bytes && (
        <p className="mt-3 text-[11.5px] leading-relaxed text-[var(--tt-fg-muted)]">
          <span className="text-[var(--tt-warn-fg)] font-medium">
            {humanBytes(disk.reclaimable_bytes)} reclaimable
          </span>
          {disk.reclaimable_note ? ` — ${disk.reclaimable_note}` : null}
        </p>
      )}

      {disk.complete === false && (
        <p className="mt-2 text-[11px] text-[var(--tt-fg-muted)]">
          This directory is large enough that the scan stopped early, so the total is a floor.
        </p>
      )}

      <div className="mt-3 pt-3 border-t border-[var(--tt-border)] font-mono text-[10px] text-[var(--tt-fg-muted)]">
        <span className="opacity-50">source&nbsp;&nbsp;</span>
        apparent file sizes, symlinks not followed — reads slightly under <code>du</code>
      </div>
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

  return (
    <div className="space-y-5">
      <div>
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 font-mono text-[11.5px] text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] transition-colors"
        >
          <ArrowLeft size={12} /> Agents
        </Link>
      </div>

      <div className="flex flex-wrap items-start justify-between gap-4 pb-4 border-b border-[var(--tt-border)]">
        <div>
          <div className="flex items-center gap-3">
            <span
              className="grid h-8 w-8 place-items-center rounded-md"
              style={{ backgroundColor: `${meta?.hex ?? "#888"}14`, color: meta?.hex ?? "#888" }}
            >
              <AgentLogo agent={key} size={17} />
            </span>
            <h1 className="text-[22px] font-semibold tracking-tight text-[var(--tt-fg)]">{label}</h1>
          </div>
          {data?.installed && (
            <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[11px] text-[var(--tt-fg-muted)]">
              {data.version && <span>v{data.version}</span>}
              {data.version && data.last_active && <span className="opacity-40">·</span>}
              {data.last_active && (
                <span>active {formatDistanceToNow(new Date(data.last_active), { addSuffix: true })}</span>
              )}
              {data.disk && <span className="opacity-40">·</span>}
              {data.disk && <span>{data.disk.total_human}</span>}
            </div>
          )}
        </div>
        {data?.root && (
          <code className="rounded bg-[var(--tt-sunken)] px-2 py-1 font-mono text-[11.5px] text-[var(--tt-fg-muted)]">
            {data.root}
          </code>
        )}
      </div>

      {loading && (
        <div className="space-y-4">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-40 w-full" />
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
          {/* min-w-0 on every grid child is load-bearing: grid items default to
              min-width:auto, so one wide table (Threads has eight columns) would
              stretch the whole grid past the viewport and push field values off
              the right edge instead of scrolling inside its own card. */}
          <div className="grid gap-4 lg:grid-cols-2">
            {data.sections.map((s, i) => {
              // Tables and trees earn the full width; compact cards pair up.
              const wide = ["schedules", "jobs", "table", "checkpoints", "todos", "plans", "models"]
                .includes(s.kind);
              return (
                <div key={`${s.kind}-${i}`} className={wide ? "lg:col-span-2 min-w-0" : "min-w-0"}>
                  <PanelSection section={s} />
                </div>
              );
            })}
            {data.disk && <div className="min-w-0"><DiskCard disk={data.disk} /></div>}
          </div>

          {data.sections.length === 0 && (
            <EmptyState
              title={`Nothing extra on disk for ${label}`}
              description="This agent is installed, but keeps nothing beyond the session transcripts already shown in traces."
            />
          )}

          {data.not_available.length > 0 && (
            <div className="rounded-[var(--tt-radius-lg)] border border-dashed border-[var(--tt-border-strong)] p-4">
              <h2 className="font-mono text-[10.5px] font-semibold uppercase tracking-[0.11em] text-[var(--tt-fg-muted)]">
                Not available for {label}
              </h2>
              <ul className="mt-2.5 space-y-1.5">
                {data.not_available.map((na) => (
                  <li key={na.kind} className="text-[12.5px] leading-relaxed text-[var(--tt-fg-muted)]">
                    <span className="font-mono text-[12px] text-[var(--tt-fg)]">{na.kind}</span>
                    {" — "}{na.reason}
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
