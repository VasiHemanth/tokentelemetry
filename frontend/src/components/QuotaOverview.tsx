"use client";

import { useState } from "react";
import { formatDistanceToNowStrict } from "date-fns";
import { RefreshCw, TimerReset } from "lucide-react";

import { api, useResource } from "@/lib/api";
import { quotaAmount, quotaResourceLabel, type QuotaCapability, type QuotaResource, type QuotaResponse } from "@/lib/quotas";
import { Badge, Button, Card, CardEyebrow, CardHeader, CardTitle, Section, Skeleton } from "@/components/ui";

function resetText(value?: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return `resets ${formatDistanceToNowStrict(date, { addSuffix: true })}`;
}

function Meter({ resourceKey, resource }: { resourceKey: string; resource: QuotaResource }) {
  const label = quotaResourceLabel(resourceKey);
  const reset = resetText(resource.resetsAt);
  const usableMeter = resource.used != null && resource.limit != null && resource.limit > 0;
  const pct = usableMeter ? Math.min(100, Math.max(0, (resource.used! / resource.limit!) * 100)) : null;
  const percentAllowance = pct != null && resource.unit === "percent";
  const value = percentAllowance
    ? `${Math.round(100 - pct!)}% left`
    : usableMeter
      ? `${quotaAmount(resource.used!, resource.unit)} used`
    : resource.available != null
      ? quotaAmount(resource.available, resource.unit)
      : resource.used != null
        ? quotaAmount(resource.used, resource.unit)
        : "No data";

  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-3 text-[11px]">
        <span className="text-[var(--tt-fg-muted)]">{label}</span>
        <span className="tabular text-[var(--tt-fg)] whitespace-nowrap">{value}</span>
      </div>
      {pct != null && (
        <div
          className="h-1.5 rounded-full tt-tint-1 overflow-hidden"
          role="progressbar"
          aria-label={`${label}: ${Math.round(percentAllowance ? 100 - pct : pct)}% ${percentAllowance ? "left" : "used"}`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(percentAllowance ? 100 - pct : pct)}
        >
          <div
            className="h-full rounded-full bg-[var(--tt-brand)] transition-[width] duration-500"
            style={{ width: `${percentAllowance ? 100 - pct : pct}%` }}
          />
        </div>
      )}
      {(reset || resource.estimated) && (
        <div className="flex items-center gap-1 text-[10px] text-[var(--tt-fg-faint)]">
          {reset && <TimerReset size={10} />}
          <span>{[reset, resource.estimated ? "estimated" : null].filter(Boolean).join(" · ")}</span>
        </div>
      )}
    </div>
  );
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

function QuotaSource({ capability }: { capability: QuotaCapability }) {
  return (
    <Card padding="md">
      <CardHeader className="mb-3">
        <CardTitle>{capability.displayName}</CardTitle>
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
                    <div>
                      <CardTitle>{snapshot.displayName}</CardTitle>
                      {snapshot.plan && <CardEyebrow className="mt-1">{snapshot.plan}</CardEyebrow>}
                    </div>
                    <Badge variant={snapshot.stale ? "warn" : "success"} size="xs">
                      {snapshot.stale ? "Cached" : "Live"}
                    </Badge>
                  </CardHeader>
                  <div className="space-y-4">
                    {Object.entries(snapshot.resources).map(([key, resource]) => <Meter key={key} resourceKey={key} resource={resource} />)}
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
                {unavailableSources.map(([providerId, capability]) => <QuotaSource key={providerId} capability={capability} />)}
              </div>
            </div>
          )}
        </>
      )}
    </Section>
  );
}
