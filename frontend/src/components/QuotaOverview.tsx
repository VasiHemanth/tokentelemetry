"use client";

import { useState } from "react";
import { formatDistanceToNowStrict } from "date-fns";
import { RefreshCw } from "lucide-react";

import { api, useResource } from "@/lib/api";
import { quotaAmount, quotaResourceLabel, type QuotaCapability, type QuotaResource, type QuotaResponse } from "@/lib/quotas";
import { Badge, Button, Card, CardEyebrow, CardHeader, CardTitle, Section, Skeleton } from "@/components/ui";
import { AgentLogo } from "@/components/icons/AgentLogo";

function resetText(value?: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return `Resets ${formatDistanceToNowStrict(date, { addSuffix: true })}`;
}

/** Matches the thresholds the providers use in their own usage screens. */
const WARN_AT = 75;
const CRITICAL_AT = 90;

function meterColor(pct: number): string {
  if (pct >= CRITICAL_AT) return "var(--tt-danger-fg)";
  if (pct >= WARN_AT) return "var(--tt-warn-fg)";
  return "var(--tt-brand)";
}

/** A quota with a ceiling: a labelled bar over its reading and reset time. */
function Meter({ label, resource, pct }: { label: string; resource: QuotaResource; pct: number }) {
  const reset = resetText(resource.resetsAt);
  const spent = pct >= 100;
  const tone = pct >= WARN_AT ? meterColor(pct) : "var(--tt-fg)";

  return (
    <div className="space-y-2">
      <div className="text-[12px] font-medium text-[var(--tt-fg)]">{label}</div>
      <div
        className="h-1.5 rounded-full tt-tint-1 overflow-hidden"
        role="progressbar"
        aria-label={`${label}: ${Math.round(pct)}% used`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(pct)}
      >
        <div
          className="h-full rounded-full transition-[width,background-color] duration-500"
          style={{ width: `${pct}%`, backgroundColor: meterColor(pct) }}
        />
      </div>
      <div className="flex items-baseline justify-between gap-3 text-[11px]">
        <span className="tabular whitespace-nowrap" style={{ color: tone }}>
          {spent ? "Limit reached" : `${Math.round(pct)}% used`}
        </span>
        {(reset || resource.estimated) && (
          <span className="text-[var(--tt-fg-dim)] whitespace-nowrap">
            {[reset, resource.estimated ? "estimated" : null].filter(Boolean).join(" · ")}
          </span>
        )}
      </div>
    </div>
  );
}

/** A balance with no ceiling — credits, spend, resets. One line, no bar. */
function Balance({ label, resource }: { label: string; resource: QuotaResource }) {
  const value = resource.available != null
    ? quotaAmount(resource.available, resource.unit)
    : resource.used != null
      ? `${quotaAmount(resource.used, resource.unit)} used`
      : "No data";

  return (
    <div className="flex items-baseline justify-between gap-3 text-[11px]">
      <span className="text-[var(--tt-fg-muted)]">{label}</span>
      <span className="tabular text-[var(--tt-fg)] whitespace-nowrap">{value}</span>
    </div>
  );
}

/**
 * A bar is only honest when the provider gave a ceiling to fill. Balances are
 * shown as plain readings rather than a meter against an invented maximum.
 */
function Reading({ resourceKey, resource }: { resourceKey: string; resource: QuotaResource }) {
  const label = quotaResourceLabel(resourceKey);
  const bounded = resource.used != null && resource.limit != null && resource.limit > 0;
  if (!bounded) return <Balance label={label} resource={resource} />;
  const pct = Math.min(100, Math.max(0, (resource.used! / resource.limit!) * 100));
  return <Meter label={label} resource={resource} pct={pct} />;
}

function capabilityLabel(state: QuotaCapability["state"]): string {
  if (state === "notSignedIn") return "Not signed in";
  if (state === "sessionExpired") return "Sign in again";
  if (state === "notEntitled") return "No plan quota";
  if (state === "refreshFailed") return "Needs refresh";
  if (state === "notSupported") return "Quota unavailable";
  return "Available";
}

function capabilityVariant(state: QuotaCapability["state"]): "success" | "warn" | "neutral" {
  if (state === "available") return "success";
  if (state === "refreshFailed" || state === "sessionExpired") return "warn";
  return "neutral";
}

function QuotaSource({ providerId, capability }: { providerId: string; capability: QuotaCapability }) {
  return (
    <Card padding="md">
      <CardHeader className="mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <AgentLogo agent={providerId} size={14} color />
          <CardTitle className="truncate">{capability.displayName}</CardTitle>
        </div>
        <Badge variant={capabilityVariant(capability.state)} size="xs">{capabilityLabel(capability.state)}</Badge>
      </CardHeader>
      <p className="text-[11px] leading-5 text-[var(--tt-fg-dim)]">
        {capability.detail ?? "A native quota source is available."}
      </p>
    </Card>
  );
}

export default function QuotaOverview() {
  const quotas = useResource<QuotaResponse>("/quotas", { pollMs: 60_000 });
  const data = quotas.data;
  const providers = Object.entries(data?.providers ?? {});
  const unavailableSources = Object.entries(data?.capabilities ?? {}).filter(([, capability]) => capability.state !== "available");
  const [refreshing, setRefreshing] = useState(false);

  async function refresh(): Promise<void> {
    setRefreshing(true);
    try {
      await api<QuotaResponse>("/quotas/refresh", { method: "POST" });
      quotas.refetch();
    } finally {
      setRefreshing(false);
    }
  }

  if (!quotas.loading && providers.length === 0 && unavailableSources.length === 0 && !(data?.errors.length)) return null;

  return (
    <Section
      title="Plan limits"
      description="Provider-reported quota windows and balances. Separate from TokenTelemetry’s historical usage and cost estimates."
      actions={
        <Button variant="ghost" size="sm" onClick={refresh} disabled={refreshing} aria-label="Refresh plan limits">
          <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} /> Refresh
        </Button>
      }
    >
      {quotas.loading && !data ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, index) => <Skeleton key={index} className="h-40" />)}
        </div>
      ) : (
        <>
          {providers.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
              {providers.map(([providerId, snapshot]) => (
                <Card key={providerId} padding="md">
                  <CardHeader className="mb-5">
                    <div className="flex items-baseline gap-2 min-w-0">
                      <CardTitle className="truncate">{snapshot.displayName}</CardTitle>
                      {snapshot.plan && <CardEyebrow className="shrink-0">{snapshot.plan}</CardEyebrow>}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {snapshot.stale && <Badge variant="warn" size="xs">Cached</Badge>}
                      <AgentLogo agent={providerId} size={16} color />
                    </div>
                  </CardHeader>
                  <div className="space-y-5">
                    {Object.entries(snapshot.resources).map(([key, resource]) => (
                      <Reading key={key} resourceKey={key} resource={resource} />
                    ))}
                    {Object.keys(snapshot.resources).length === 0 && (
                      <p className="text-[11px] text-[var(--tt-fg-dim)]">This plan does not expose a personal quota meter.</p>
                    )}
                  </div>
                </Card>
              ))}
            </div>
          )}
          {(data?.errors.length ?? 0) > 0 && (
            <p className="text-[11px] text-amber-300">Some provider limits could not be refreshed; cached readings are kept when available.</p>
          )}
          {unavailableSources.length > 0 && (
            <div className="space-y-3">
              <p className="text-[11px] text-[var(--tt-fg-dim)]">
                Other coding agents — why each has no live quota above
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
                {unavailableSources.map(([providerId, capability]) => <QuotaSource key={providerId} providerId={providerId} capability={capability} />)}
              </div>
            </div>
          )}
        </>
      )}
    </Section>
  );
}
