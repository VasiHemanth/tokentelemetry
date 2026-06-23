"use client";

import { useEffect, useState } from "react";
import { Wallet, Plus, Trash2, Check, Loader2 } from "lucide-react";

import { cn } from "@/lib/cn";
import { getAgent } from "@/lib/agents";
import { trackEvent } from "@/lib/telemetry";
import { Card, CardHeader, CardTitle, Button } from "@/components/ui";
import {
  getBudgets, putBudgets,
  type Budget, type BudgetStatus, type BudgetPeriod, type BudgetLimitType,
  DEFAULT_THRESHOLDS,
} from "@/lib/budgets";

/** Editable row in the form. `agent` empty string = the project-total budget. */
interface Row {
  id: string;
  agent: string;
  period: BudgetPeriod;
  limit_type: BudgetLimitType;
  limit_value: string;        // kept as string for controlled input
  thresholds: number[];
}

const PERIODS: { value: BudgetPeriod; label: string }[] = [
  { value: "monthly", label: "Monthly" },
  { value: "weekly", label: "Weekly" },
  { value: "rolling_30d", label: "Rolling 30d" },
];

const THRESHOLD_PRESETS: { key: string; label: string; value: number[] }[] = [
  { key: "80-100", label: "80% & 100%", value: [0.8, 1.0] },
  { key: "90-100", label: "90% & 100%", value: [0.9, 1.0] },
  { key: "100", label: "100% only", value: [1.0] },
];

function presetKey(thresholds: number[]): string {
  const found = THRESHOLD_PRESETS.find(
    (p) => p.value.length === thresholds.length && p.value.every((v, i) => v === thresholds[i]),
  );
  return found?.key ?? "80-100";
}

function toBudget(s: BudgetStatus): Budget {
  return {
    id: s.id, filters: s.filters, period: s.period, limit_type: s.limit_type,
    limit_value: s.limit_value, thresholds: s.thresholds, enabled: s.enabled,
  };
}

let _tmpId = 0;
const newId = () => `tmp-${Date.now()}-${_tmpId++}`;

export default function BudgetEditor({
  projectPath, agents,
}: { projectPath: string; agents: string[] }) {
  const [rows, setRows] = useState<Row[]>([]);
  const [otherBudgets, setOtherBudgets] = useState<Budget[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Anonymous adoption signal: someone opened the budget editor. Content-free —
  // just the "budgets" feature label; the backend re-sanitizes regardless.
  useEffect(() => {
    trackEvent("feature.used", { name: "budgets" });
  }, []);

  useEffect(() => {
    let cancelled = false;
    getBudgets()
      .then((all) => {
        if (cancelled) return;
        const mine: Row[] = [];
        const others: Budget[] = [];
        for (const b of all) {
          const isMine = b.filters.project === projectPath && !b.filters.model;
          if (isMine) {
            mine.push({
              id: b.id, agent: b.filters.agent ?? "",
              period: b.period, limit_type: b.limit_type,
              limit_value: String(b.limit_value), thresholds: b.thresholds,
            });
          } else {
            others.push(toBudget(b));
          }
        }
        setRows(mine);
        setOtherBudgets(others);
      })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [projectPath]);

  const hasTotal = rows.some((r) => r.agent === "");
  const budgetedAgents = new Set(rows.filter((r) => r.agent).map((r) => r.agent));
  const availableAgents = agents.filter((a) => !budgetedAgents.has(a));

  const update = (id: string, patch: Partial<Row>) =>
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  const remove = (id: string) => setRows((rs) => rs.filter((r) => r.id !== id));

  const addTotal = () =>
    setRows((rs) => [
      { id: newId(), agent: "", period: "monthly", limit_type: "usd", limit_value: "", thresholds: [...DEFAULT_THRESHOLDS] },
      ...rs,
    ]);
  const addAgent = (agent: string) =>
    setRows((rs) => [
      ...rs,
      { id: newId(), agent, period: "monthly", limit_type: "usd", limit_value: "", thresholds: [...DEFAULT_THRESHOLDS] },
    ]);

  const save = async () => {
    setSaving(true); setError(null); setSaved(false);
    try {
      const mine: Budget[] = rows
        .map((r) => {
          const val = parseFloat(r.limit_value);
          if (!isFinite(val) || val <= 0) return null;
          const filters = r.agent ? { project: projectPath, agent: r.agent } : { project: projectPath };
          return {
            id: r.id.startsWith("tmp-") ? "" : r.id,
            filters, period: r.period, limit_type: r.limit_type,
            limit_value: val, thresholds: r.thresholds, enabled: true,
          } as Budget;
        })
        .filter((b): b is Budget => b !== null);
      const next = await putBudgets([...otherBudgets, ...mine]);
      // Re-seat our rows from the canonical saved set (picks up backend-assigned ids).
      const mineSaved: Row[] = [];
      const others: Budget[] = [];
      for (const b of next) {
        if (b.filters.project === projectPath && !b.filters.model) {
          mineSaved.push({
            id: b.id, agent: b.filters.agent ?? "", period: b.period,
            limit_type: b.limit_type, limit_value: String(b.limit_value), thresholds: b.thresholds,
          });
        } else {
          others.push(toBudget(b));
        }
      }
      setRows(mineSaved);
      setOtherBudgets(others);
      setSaved(true);
      // Conversion signal: a budget was actually configured (>=1 saved row).
      if (mine.length > 0) trackEvent("feature.used", { name: "budget-set" });
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const invalid = rows.some((r) => {
    const v = parseFloat(r.limit_value);
    return !isFinite(v) || v <= 0;
  });

  return (
    <Card padding="lg">
      <CardHeader>
        <div>
          <CardTitle><Wallet size={14} className="text-[var(--tt-brand)]" /> Budgets</CardTitle>
          <p className="text-[12px] text-[var(--tt-fg-dim)] mt-0.5">
            Set a spend limit for this project — overall and per agent. Alerts only; TokenTelemetry never blocks an agent.
          </p>
        </div>
      </CardHeader>

      {loading ? (
        <div className="text-[12px] text-[var(--tt-fg-dim)] py-4">Loading…</div>
      ) : (
        <div className="space-y-3">
          {rows.length === 0 && (
            <div className="text-[12px] text-[var(--tt-fg-dim)] italic py-1">
              No budgets yet. Add a project-wide limit or a per-agent limit below.
            </div>
          )}

          {rows.map((r) => {
            const meta = r.agent ? getAgent(r.agent) : null;
            return (
              <div key={r.id} className="rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-panel)] p-3">
                <div className="flex items-center justify-between mb-2.5">
                  <span
                    className="text-[11px] font-semibold uppercase tracking-[0.14em]"
                    style={meta ? { color: meta.hex } : { color: "var(--tt-fg)" }}
                  >
                    {meta ? meta.label : "Project total"}
                  </span>
                  <button
                    onClick={() => remove(r.id)}
                    aria-label="Remove budget"
                    className="grid place-items-center h-6 w-6 rounded text-[var(--tt-fg-dim)] hover:text-[var(--tt-danger)] hover:tt-tint-1 transition-colors"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  {/* limit type */}
                  <Segmented
                    options={[{ v: "usd", l: "$" }, { v: "tokens", l: "Tokens" }]}
                    value={r.limit_type}
                    onChange={(v) => update(r.id, { limit_type: v as BudgetLimitType })}
                  />
                  {/* limit value */}
                  <div className="relative">
                    {r.limit_type === "usd" && (
                      <span className="absolute left-2 top-1/2 -translate-y-1/2 text-[12px] text-[var(--tt-fg-dim)]">$</span>
                    )}
                    <input
                      type="number"
                      min="0"
                      step={r.limit_type === "usd" ? "1" : "100000"}
                      value={r.limit_value}
                      onChange={(e) => update(r.id, { limit_value: e.target.value })}
                      placeholder={r.limit_type === "usd" ? "100" : "5000000"}
                      className={cn(
                        "h-8 w-32 rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-surface)] text-[12px] text-[var(--tt-fg)] tabular focus:outline-none focus:border-[var(--tt-brand)]",
                        r.limit_type === "usd" ? "pl-5 pr-2" : "px-2",
                      )}
                    />
                  </div>
                  {/* period */}
                  <select
                    value={r.period}
                    onChange={(e) => update(r.id, { period: e.target.value as BudgetPeriod })}
                    className="h-8 rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-surface)] text-[12px] text-[var(--tt-fg)] px-2 focus:outline-none focus:border-[var(--tt-brand)]"
                  >
                    {PERIODS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
                  </select>
                  {/* thresholds */}
                  <select
                    value={presetKey(r.thresholds)}
                    onChange={(e) => {
                      const preset = THRESHOLD_PRESETS.find((p) => p.key === e.target.value);
                      if (preset) update(r.id, { thresholds: [...preset.value] });
                    }}
                    className="h-8 rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-surface)] text-[12px] text-[var(--tt-fg)] px-2 focus:outline-none focus:border-[var(--tt-brand)]"
                    title="When to alert"
                  >
                    {THRESHOLD_PRESETS.map((p) => <option key={p.key} value={p.key}>Alert {p.label}</option>)}
                  </select>
                </div>
              </div>
            );
          })}

          {/* Add controls */}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            {!hasTotal && (
              <Button size="sm" variant="secondary" onClick={addTotal}>
                <Plus size={13} /> Project total
              </Button>
            )}
            {availableAgents.length > 0 && (
              <select
                value=""
                onChange={(e) => { if (e.target.value) addAgent(e.target.value); }}
                className="h-7 rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-panel)] text-[12px] text-[var(--tt-fg-muted)] px-2 focus:outline-none focus:border-[var(--tt-brand)]"
              >
                <option value="">+ Add agent budget…</option>
                {availableAgents.map((a) => <option key={a} value={a}>{getAgent(a).label}</option>)}
              </select>
            )}
          </div>

          {/* Save */}
          <div className="flex items-center gap-3 pt-2">
            <Button variant="primary" size="sm" onClick={save} disabled={saving || invalid}>
              {saving ? <Loader2 size={13} className="animate-spin" /> : saved ? <Check size={13} /> : null}
              {saved ? "Saved" : "Save budgets"}
            </Button>
            {invalid && rows.length > 0 && (
              <span className="text-[11px] text-[var(--tt-warn)]">Enter a positive limit for every row.</span>
            )}
            {error && <span className="text-[11px] text-[var(--tt-danger)]">{error}</span>}
          </div>
        </div>
      )}
    </Card>
  );
}

function Segmented({
  options, value, onChange,
}: { options: { v: string; l: string }[]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="inline-flex rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-surface)] overflow-hidden">
      {options.map((o) => (
        <button
          key={o.v}
          onClick={() => onChange(o.v)}
          className={cn(
            "h-8 px-3 text-[12px] font-medium transition-colors",
            value === o.v
              ? "tt-tint-2 text-[var(--tt-fg)]"
              : "text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)]",
          )}
        >
          {o.l}
        </button>
      ))}
    </div>
  );
}
