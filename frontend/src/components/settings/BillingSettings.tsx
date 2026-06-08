"use client";

import { useEffect, useState } from "react";
import { Wallet, Check, Loader2 } from "lucide-react";
import { getAgent } from "@/lib/agents";
import { Card, CardHeader, CardTitle, Badge, Skeleton } from "@/components/ui";
import {
  getBillingConfig, setBillingMode, MODE_LABEL,
  type BillingConfig, type AgentBilling, type BillingMode,
} from "@/lib/billing";

// Modes a user can pick explicitly (plus the implicit "auto" = clear override).
const SELECTABLE: BillingMode[] = ["subscription", "api", "local"];

function sourceNote(b: AgentBilling): string {
  if (b.source === "user") return "Set by you";
  if (b.source === "detected") return `Auto-detected${b.detect_source ? ` from ${b.detect_source}` : ""}`;
  return b.detect_source ? `Default (couldn't detect from ${b.detect_source})` : "Default";
}

export function BillingSettings() {
  const [config, setConfig] = useState<BillingConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingAgent, setSavingAgent] = useState<string | null>(null);
  const [savedAgent, setSavedAgent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getBillingConfig()
      .then((c) => { if (!cancelled) { setConfig(c); setLoading(false); } })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Failed to load billing config.");
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const onChange = async (agent: string, raw: string) => {
    // "auto" clears the override → revert to auto-detection.
    const mode = raw === "auto" ? null : (raw as BillingMode);
    setSavingAgent(agent);
    setError(null);
    try {
      const next = await setBillingMode(agent, mode);
      setConfig(next);
      setSavedAgent(agent);
      setTimeout(() => setSavedAgent((a) => (a === agent ? null : a)), 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save.");
    } finally {
      setSavingAgent((a) => (a === agent ? null : a));
    }
  };

  const entries = config ? Object.entries(config.agents) : [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <Wallet size={14} className="text-[var(--tt-brand)]" />
          Billing mode per agent
        </CardTitle>
      </CardHeader>

      {loading ? (
        <div className="space-y-2">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      ) : entries.length === 0 ? (
        <p className="text-[13px] text-[var(--tt-fg-dim)]">No agents detected yet.</p>
      ) : (
        <div className="divide-y divide-[var(--tt-border)]">
          {entries.map(([agent, b]) => {
            const meta = getAgent(agent);
            const Icon = meta.icon;
            const value = b.source === "user" ? b.mode : "auto";
            return (
              <div key={agent} className="flex items-center justify-between gap-4 py-3">
                <div className="flex items-center gap-2.5 min-w-0">
                  <span
                    className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md"
                    style={{ background: `${meta.hex}1a`, color: meta.hex }}
                  >
                    <Icon size={15} />
                  </span>
                  <div className="min-w-0">
                    <div className="text-[13px] font-medium text-[var(--tt-fg)]">{meta.label}</div>
                    <div className="text-[11px] text-[var(--tt-fg-muted)] truncate">{sourceNote(b)}</div>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  {savedAgent === agent && (
                    <span className="flex items-center gap-1 text-[11px] text-[var(--tt-success-fg)]">
                      <Check size={12} /> Saved
                    </span>
                  )}
                  {savingAgent === agent && <Loader2 size={13} className="animate-spin text-[var(--tt-fg-muted)]" />}
                  <select
                    value={value}
                    disabled={savingAgent === agent}
                    onChange={(e) => onChange(agent, e.target.value)}
                    className="rounded-md border border-[var(--tt-border)] bg-[var(--tt-bg-elev)] px-2.5 py-1.5 text-[12px] text-[var(--tt-fg)] outline-none focus:border-[var(--tt-brand)] cursor-pointer"
                  >
                    <option value="auto">
                      Auto{b.detected ? ` · ${MODE_LABEL[b.detected]}` : b.source === "default" ? ` · ${MODE_LABEL[b.default]}` : ""}
                    </option>
                    {SELECTABLE.map((m) => (
                      <option key={m} value={m}>{MODE_LABEL[m]}</option>
                    ))}
                  </select>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {error && <p className="mt-3 text-[12px] text-[var(--tt-danger-fg)]">{error}</p>}
    </Card>
  );
}
