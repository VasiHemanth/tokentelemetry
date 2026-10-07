"use client";

import { useState } from "react";
import { Gauge, RefreshCw, Loader2, AlertTriangle } from "lucide-react";

import { AgentLogo } from "@/components/icons/AgentLogo";
import { useQuotas } from "@/components/QuotaProvider";
import {
  Badge, Card, EmptyState, PageHeader, Skeleton,
  Table, TBody, TD, TH, THead, TR,
} from "@/components/ui";
import {
  quotaAmount, quotaColor, quotaPercent, quotaResourceLabel, resetText, worstWindowFor,
  type QuotaCapability, type QuotaResource, type QuotaSnapshot,
} from "@/lib/quotas";

type QuotaRow = {
  providerId: string;
  providerName: string;
  plan?: string | null;
  resourceKey: string;
  resource: QuotaResource;
  pct: number;
};

export default function QuotasPage() {
  const { data, loading, refresh } = useQuotas();
  const providers = Object.entries(data?.providers ?? {});
  const rows = providers.flatMap(([providerId, snapshot]) => quotaRows(providerId, snapshot));
  const unavailable = Object.values(data?.capabilities ?? {}).filter((c) => c.state !== "available");
  const errors = data?.errors ?? [];

  return (
    <div className="px-8 py-8 max-w-[1200px] mx-auto space-y-8 pb-20">
      <PageHeader
        eyebrow="Plan limits"
        title="Quotas"
        description="Live provider quota windows, balances, and reset times from the same local provider data used by the sidebar indicator."
        icon={<Gauge size={20} strokeWidth={2.25} />}
        actions={
          <RefreshButton onRefresh={refresh} />
        }
      />

      {loading && !data ? (
        <QuotasLoading />
      ) : providers.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Gauge size={20} />}
            title="No live quotas yet"
            description="Once a connected provider reports plan limits, this page will show its remaining windows and reset times."
          />
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {providers.map(([providerId, snapshot]) => (
              <ProviderCard key={providerId} providerId={providerId} snapshot={snapshot} />
            ))}
          </div>

          <Card padding="none">
            <Table>
              <THead>
                <TR>
                  <TH className="pl-5">Provider</TH>
                  <TH>Plan</TH>
                  <TH>Window</TH>
                  <TH className="text-right">Remaining</TH>
                  <TH>Reset</TH>
                  <TH className="pr-5">Usage</TH>
                </TR>
              </THead>
              <TBody>
                {rows.map((row) => (
                  <TR key={`${row.providerId}:${row.resourceKey}`}>
                    <TD className="pl-5">
                      <span className="flex items-center gap-2 min-w-0">
                        <AgentLogo agent={row.providerId} size={14} color />
                        <span className="font-semibold truncate">{row.providerName}</span>
                      </span>
                    </TD>
                    <TD className="text-[var(--tt-fg-muted)]">{row.plan || "Unknown"}</TD>
                    <TD>{quotaResourceLabel(row.resourceKey)}</TD>
                    <TD className="text-right tabular font-semibold">{Math.max(0, Math.round(100 - row.pct))}%</TD>
                    <TD className="text-[var(--tt-fg-muted)] whitespace-nowrap">{resetText(row.resource.resetsAt) ?? "No reset reported"}</TD>
                    <TD className="pr-5 min-w-[180px]">
                      <UsageBar pct={row.pct} />
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </Card>

          <Balances providers={providers} />
        </>
      )}

      {(unavailable.length > 0 || errors.length > 0) && (
        <AvailabilityPanel unavailable={unavailable} errors={errors} />
      )}
    </div>
  );
}

function quotaRows(providerId: string, snapshot: QuotaSnapshot): QuotaRow[] {
  return Object.entries(snapshot.resources)
    .map(([resourceKey, resource]) => ({ resourceKey, resource, pct: quotaPercent(resource) }))
    .filter((row): row is { resourceKey: string; resource: QuotaResource; pct: number } => row.pct != null)
    .map(({ resourceKey, resource, pct }) => ({
      providerId,
      providerName: snapshot.displayName,
      plan: snapshot.plan,
      resourceKey,
      resource,
      pct,
    }));
}

function ProviderCard({ providerId, snapshot }: { providerId: string; snapshot: QuotaSnapshot }) {
  const worst = worstWindowFor(providerId, snapshot);
  const rows = quotaRows(providerId, snapshot);
  const remaining = worst ? Math.max(0, Math.round(100 - worst.pct)) : null;

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <AgentLogo agent={providerId} size={20} color />
          <div className="min-w-0">
            <div className="text-[14px] font-semibold text-[var(--tt-fg)] truncate">{snapshot.displayName}</div>
            <div className="mt-1 text-[11px] text-[var(--tt-fg-dim)]">
              {snapshot.plan || "No plan name reported"}
            </div>
          </div>
        </div>
        {snapshot.stale && <Badge variant="warn">Stale</Badge>}
      </div>

      <div className="mt-5">
        {worst ? (
          <>
            <div className="flex items-baseline justify-between gap-3">
              <div>
                <div className="text-[10px] uppercase tracking-[0.18em] text-[var(--tt-fg-dim)]">Tightest window</div>
                <div className="mt-1 text-[13px] font-medium text-[var(--tt-fg)]">{worst.label}</div>
              </div>
              <div className="text-right">
                <div className="text-[24px] leading-none font-semibold tabular" style={{ color: quotaColor(worst.pct) }}>
                  {remaining}%
                </div>
                <div className="mt-1 text-[10px] uppercase tracking-[0.14em] text-[var(--tt-fg-dim)]">remaining</div>
              </div>
            </div>
            <div className="mt-3">
              <UsageBar pct={worst.pct} />
            </div>
          </>
        ) : (
          <div className="rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-sunken)] p-3 text-[12px] text-[var(--tt-fg-dim)]">
            No percentage quota window reported.
          </div>
        )}
      </div>

      <div className="mt-4 space-y-2">
        {rows.slice(0, 3).map((row) => (
          <div key={row.resourceKey} className="flex items-center justify-between gap-3 text-[11px]">
            <span className="text-[var(--tt-fg-muted)]">{quotaResourceLabel(row.resourceKey)}</span>
            <span className="tabular text-[var(--tt-fg)]">{Math.max(0, Math.round(100 - row.pct))}% left</span>
          </div>
        ))}
      </div>
    </Card>
  );
}

function UsageBar({ pct }: { pct: number }) {
  return (
    <div>
      <div className="flex items-center justify-between gap-3 text-[11px]">
        <span className="text-[var(--tt-fg-dim)]">Used</span>
        <span className="tabular" style={{ color: quotaColor(pct) }}>{Math.round(pct)}%</span>
      </div>
      <div className="mt-1 h-1.5 rounded-full tt-tint-1 overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: quotaColor(pct) }} />
      </div>
    </div>
  );
}

function Balances({ providers }: { providers: [string, QuotaSnapshot][] }) {
  const balances = providers.flatMap(([providerId, snapshot]) =>
    Object.entries(snapshot.resources)
      .filter(([, resource]) => quotaPercent(resource) == null)
      .map(([resourceKey, resource]) => ({ providerId, snapshot, resourceKey, resource })));

  if (balances.length === 0) return null;

  return (
    <Card padding="none">
      <div className="px-5 py-4 border-b border-[var(--tt-border)]">
        <div className="text-[13px] font-semibold text-[var(--tt-fg)]">Balances and usage counters</div>
        <div className="mt-1 text-[12px] text-[var(--tt-fg-dim)]">Resources that do not report a fixed percentage window.</div>
      </div>
      <Table>
        <THead>
          <TR>
            <TH className="pl-5">Provider</TH>
            <TH>Resource</TH>
            <TH className="text-right pr-5">Value</TH>
          </TR>
        </THead>
        <TBody>
          {balances.map(({ providerId, snapshot, resourceKey, resource }) => (
            <TR key={`${providerId}:${resourceKey}`}>
              <TD className="pl-5">
                <span className="flex items-center gap-2">
                  <AgentLogo agent={providerId} size={13} color />
                  <span className="font-medium">{snapshot.displayName}</span>
                </span>
              </TD>
              <TD>{quotaResourceLabel(resourceKey)}</TD>
              <TD className="text-right pr-5 tabular text-[var(--tt-fg-muted)]">
                {resource.available != null
                  ? quotaAmount(resource.available, resource.unit)
                  : resource.remaining != null
                    ? `${quotaAmount(resource.remaining, resource.unit)} remaining`
                    : resource.used != null
                      ? `${quotaAmount(resource.used, resource.unit)} used`
                      : "No value reported"}
              </TD>
            </TR>
          ))}
        </TBody>
      </Table>
    </Card>
  );
}

function AvailabilityPanel({
  unavailable, errors,
}: {
  unavailable: QuotaCapability[];
  errors: { providerId: string; message: string }[];
}) {
  return (
    <Card>
      <div className="flex items-center gap-2 text-[13px] font-semibold text-[var(--tt-fg)]">
        <AlertTriangle size={15} className="text-[var(--tt-warn-fg)]" />
        Provider availability
      </div>
      <div className="mt-3 grid gap-2">
        {unavailable.map((cap) => (
          <div key={cap.displayName} className="flex items-start justify-between gap-4 rounded-[var(--tt-radius)] bg-[var(--tt-sunken)] px-3 py-2 text-[12px]">
            <span className="font-medium text-[var(--tt-fg)]">{cap.displayName}</span>
            <span className="text-right text-[var(--tt-fg-muted)]">{cap.detail || cap.state}</span>
          </div>
        ))}
        {errors.map((err) => (
          <div key={`${err.providerId}:${err.message}`} className="rounded-[var(--tt-radius)] bg-[var(--tt-sunken)] px-3 py-2 text-[12px] text-[var(--tt-fg-muted)]">
            <span className="font-medium text-[var(--tt-fg)]">{err.providerId}</span>: {err.message}
          </div>
        ))}
      </div>
    </Card>
  );
}

function RefreshButton({ onRefresh }: { onRefresh: () => Promise<void> }) {
  const [refreshing, setRefreshing] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        setRefreshing(true);
        try {
          await onRefresh();
        } finally {
          setRefreshing(false);
        }
      }}
      disabled={refreshing}
      className="inline-flex h-9 items-center gap-2 rounded-[var(--tt-radius)] border border-[var(--tt-border)] px-3 text-[12px] font-medium text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] hover:tt-tint-1 disabled:opacity-50 transition-colors"
    >
      {refreshing ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
      Refresh
    </button>
  );
}

function QuotasLoading() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {[0, 1, 2].map((i) => (
          <Card key={i}>
            <Skeleton className="h-5 w-36" />
            <Skeleton className="mt-5 h-8 w-24" />
            <Skeleton className="mt-4 h-2 w-full" />
          </Card>
        ))}
      </div>
      <Card padding="none">
        <Skeleton className="m-5 h-48" />
      </Card>
    </div>
  );
}
