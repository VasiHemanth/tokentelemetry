"use client";

import { createContext, useContext, useMemo } from "react";

import { api, useResource } from "@/lib/api";
import { worstWindow, type QuotaResponse, type QuotaWindow } from "@/lib/quotas";

type QuotaContextValue = {
  data?: QuotaResponse;
  loading: boolean;
  /** The most-consumed window across every signed-in provider, if any. */
  worst?: QuotaWindow;
  refresh: () => Promise<void>;
};

const QuotaContext = createContext<QuotaContextValue>({
  loading: true,
  refresh: async () => {},
});

/**
 * One poll of /quotas for the whole app.
 *
 * The sidebar indicator is mounted on every page, and the dashboard tiles and
 * agent pages read the same snapshot. `useResource` does not dedupe, so without
 * this each of them would poll the endpoint on its own schedule and they could
 * disagree about the same window for up to a minute.
 */
export function QuotaProvider({ children }: { children: React.ReactNode }) {
  const { data, loading, refetch } = useResource<QuotaResponse>("/quotas", { pollMs: 60_000 });

  const value = useMemo<QuotaContextValue>(() => ({
    data,
    loading,
    worst: worstWindow(data),
    refresh: async () => {
      await api<QuotaResponse>("/quotas/refresh", { method: "POST" });
      refetch();
    },
  }), [data, loading, refetch]);

  return <QuotaContext.Provider value={value}>{children}</QuotaContext.Provider>;
}

export function useQuotas(): QuotaContextValue {
  return useContext(QuotaContext);
}
