"use client";

import { useMemo, useState } from "react";
import { CircleDollarSign, Search } from "lucide-react";

import {
  Badge, Card, EmptyState, PageHeader, Skeleton,
  Table, TBody, TD, TH, THead, TR,
} from "@/components/ui";
import { useResource } from "@/lib/api";

type PriceRate = {
  in?: number | null;
  out?: number | null;
  cached_read?: number | null;
};

type PricingResponse = {
  updated: string;
  overlay_updated?: string | null;
  models: Record<string, PriceRate>;
};

type PricingRow = {
  model: string;
  rates: PriceRate;
};

export default function PricingPage() {
  const { data, loading } = useResource<PricingResponse>("/pricing");
  const [search, setSearch] = useState("");

  const rows = useMemo<PricingRow[]>(() => {
    const q = search.trim().toLowerCase();
    return Object.entries(data?.models ?? {})
      .map(([model, rates]) => ({ model, rates }))
      .filter((row) => !q || row.model.toLowerCase().includes(q))
      .sort((a, b) => {
        if (a.model === "_default") return -1;
        if (b.model === "_default") return 1;
        return a.model.localeCompare(b.model);
      });
  }, [data, search]);

  return (
    <div className="px-8 py-8 max-w-[1200px] mx-auto space-y-8 pb-20">
      <PageHeader
        eyebrow="Billing"
        title="Pricing"
        description="Model pricing rates used to estimate API-equivalent costs across recorded sessions."
        icon={<CircleDollarSign size={20} strokeWidth={2.25} />}
        actions={
          data && (
            <>
              <Badge variant="outline" size="sm" className="h-9">Curated · {data.updated}</Badge>
              {data.overlay_updated && <Badge variant="neutral" size="sm" className="h-9">Overlay · {data.overlay_updated}</Badge>}
            </>
          )
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[260px]">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--tt-fg-dim)] pointer-events-none" />
          <input
            type="text"
            placeholder="Search models..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full h-9 pl-9 pr-3 rounded-[var(--tt-radius)] bg-[var(--tt-panel)] border border-[var(--tt-border)] text-[13px] text-[var(--tt-fg)] placeholder:text-[var(--tt-fg-faint)] hover:border-[var(--tt-border-strong)] focus:border-[color:var(--tt-brand)]/40 focus:outline-none focus:ring-1 focus:ring-[color:var(--tt-brand)]/30 transition-colors"
          />
        </div>
        {data && (
          <Badge variant="neutral" size="sm" className="h-9">
            {rows.length.toLocaleString()} / {Object.keys(data.models).length.toLocaleString()} models
          </Badge>
        )}
      </div>

      {loading && !data ? (
        <PricingLoading />
      ) : !data ? (
        <Card>
          <EmptyState
            icon={<CircleDollarSign size={20} />}
            title="No pricing data"
            description="The pricing endpoint did not return a model table."
          />
        </Card>
      ) : rows.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Search size={20} />}
            title={`No models match "${search}"`}
            description="Try a shorter model name or clear the search."
          />
        </Card>
      ) : (
        <Card padding="none">
          <Table>
            <THead>
              <TR>
                <TH className="pl-5">Model</TH>
                <TH className="text-right">Input</TH>
                <TH className="text-right">Output</TH>
                <TH className="text-right pr-5">Cached read</TH>
              </TR>
            </THead>
            <TBody>
              {rows.map(({ model, rates }) => (
                <TR key={model}>
                  <TD className="pl-5">
                    <div className="font-mono text-[12px] text-[var(--tt-fg)]">{model}</div>
                    {model === "_default" && (
                      <div className="mt-1 text-[11px] text-[var(--tt-fg-dim)]">Fallback rate for unrecognized models</div>
                    )}
                  </TD>
                  <TD className="text-right tabular text-[var(--tt-fg-muted)]">{formatRate(rates.in)}</TD>
                  <TD className="text-right tabular text-[var(--tt-fg-muted)]">{formatRate(rates.out)}</TD>
                  <TD className="text-right pr-5 tabular text-[var(--tt-fg-muted)]">{formatRate(rates.cached_read)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </Card>
      )}
    </div>
  );
}

function formatRate(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "Not priced";
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 6 })} / 1M`;
}

function PricingLoading() {
  return (
    <Card padding="none">
      <div className="p-5 space-y-3">
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <Skeleton key={i} className="h-8 w-full" />
        ))}
      </div>
    </Card>
  );
}
