"use client";

import { useCallback, useEffect, useState } from "react";
import { useResource } from "@/lib/api";
import { PageHeader, Card, EmptyState, StatTile, Badge } from "@/components/ui";
import { formatTokens, formatCost } from "@/lib/format";
import { timeAgo } from "@/lib/notifications";
import { profileColor, profileTint } from "@/lib/profileColor";
import { Budget, BudgetStatus, getBudgets, putBudgets } from "@/lib/budgets";
import {
  Users, Power, BookOpen, Clock, Sparkles, TrendingUp, TrendingDown,
  Bot, Wallet, GitCompareArrows,
} from "lucide-react";

interface ProfileGateway {
  state: string | null;
  pid: number | null;
  pid_alive: boolean;
}

interface ProfileUsage {
  sessions: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost: number;
  last_activity: string | null;
  cost_7d: number;
  cost_prev_7d: number;
  unattended_cost_7d: number;
  daily: { date: string; cost: number }[];
}

interface Profile {
  name: string;
  is_default: boolean;
  active: boolean;
  description: string | null;
  soul_exists: boolean;
  skills_count: number;
  cron_jobs: number;
  gateway: ProfileGateway;
  usage: ProfileUsage;
}

interface ProfilesResp {
  profiles: Profile[];
  active_profile: string | null;
}

interface Session {
  id: string;
  agent: string;
  model?: string;
  cost?: number;
  hermes_profile?: string;
  tokens?: { total: number };
}

export default function ProfilesPage() {
  const { data, loading } = useResource<ProfilesResp>("/hermes/profiles", { pollMs: 60_000 });
  const sessionsRes = useResource<Session[]>("/sessions", { pollMs: 60_000, initial: [] });
  const profiles = data?.profiles || [];
  const named = profiles.filter((p) => !p.is_default);
  const totals = profiles.reduce(
    (acc, p) => ({
      sessions: acc.sessions + p.usage.sessions,
      tokens: acc.tokens + p.usage.total_tokens,
      cost: acc.cost + p.usage.cost,
      cost7d: acc.cost7d + p.usage.cost_7d,
    }),
    { sessions: 0, tokens: 0, cost: 0, cost7d: 0 },
  );

  // Per-profile budgets ride the standard budgets engine via the
  // hermes_profile filter; this page only manages that one budget shape.
  const [budgets, setBudgets] = useState<BudgetStatus[] | null>(null);
  const refreshBudgets = useCallback(() => {
    getBudgets().then(setBudgets).catch(() => setBudgets([]));
  }, []);
  useEffect(refreshBudgets, [refreshBudgets]);

  const budgetFor = (name: string) =>
    (budgets ?? []).find(
      (b) => b.filters.agent === "hermes" && b.filters.hermes_profile === name
        && !b.filters.project && !b.filters.model,
    );

  const saveBudget = async (name: string, limit: number | null) => {
    const all: Budget[] = (budgets ?? []).map(
      ({ id, filters, period, limit_type, limit_value, thresholds, enabled }) =>
        ({ id, filters, period, limit_type, limit_value, thresholds, enabled }),
    );
    const idx = all.findIndex(
      (b) => b.filters.agent === "hermes" && b.filters.hermes_profile === name
        && !b.filters.project && !b.filters.model,
    );
    if (limit === null || limit <= 0) {
      if (idx >= 0) all.splice(idx, 1);
    } else if (idx >= 0) {
      all[idx] = { ...all[idx], limit_value: limit };
    } else {
      all.push({
        id: `hermes-profile-${name}-${Date.now().toString(36)}`,
        filters: { agent: "hermes", hermes_profile: name },
        period: "monthly", limit_type: "usd", limit_value: limit,
        thresholds: [0.8, 1.0], enabled: true,
      });
    }
    await putBudgets(all);
    refreshBudgets();
  };

  return (
    <div className="px-8 py-8 max-w-[1200px] mx-auto space-y-6 pb-20">
      <PageHeader
        backHref="/hermes"
        icon={<div className="h-10 w-10 grid place-items-center rounded-[var(--tt-radius)] bg-blue-500/10 border border-blue-500/30"><Users className="text-blue-500" size={20} /></div>}
        eyebrow="Hermes Agent"
        title="Profiles"
        description="Each profile is a full parallel agent home (own config, SOUL, sessions, cron, gateway). Hermes has no combined usage view across profiles — this is it."
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile label="Profiles" value={loading ? "—" : String(profiles.length)} hint={named.length ? `${named.length} named + default` : "default only"} />
        <StatTile label="Sessions" value={loading ? "—" : String(totals.sessions)} />
        <StatTile label="Tokens" value={loading ? "—" : formatTokens(totals.tokens)} />
        <StatTile label="Cost / 7d" value={loading ? "—" : formatCost(totals.cost7d)} hint={loading ? undefined : `${formatCost(totals.cost)} all-time`} />
      </div>

      {!loading && profiles.length >= 2 && (
        <ComparePanel profiles={profiles} sessions={sessionsRes.data ?? []} />
      )}

      {loading ? (
        <div className="animate-pulse h-32 bg-[var(--tt-panel)] rounded-xl" />
      ) : profiles.length === 0 ? (
        <EmptyState title="Hermes not found" description="No ~/.hermes directory on this machine." />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {profiles.map((p) => (
            <ProfileCard
              key={p.name}
              p={p}
              budget={budgetFor(p.name)}
              onSaveBudget={(v) => saveBudget(p.name, v)}
            />
          ))}
        </div>
      )}

      {!loading && profiles.length > 0 && named.length === 0 && (
        <div className="text-[11px] text-[var(--tt-fg-dim)]">
          Only the default home is in use. Create isolated agent identities with <code className="font-mono text-[var(--tt-fg-muted)]">hermes profile create &lt;name&gt;</code> — their sessions and costs will show up here.
        </div>
      )}
    </div>
  );
}

/** Identity in the compare view is carried by POSITION (A is always left)
 *  and by the name labels; the profile color only reinforces it. The default
 *  home has no identity hue, so it wears the app brand color here. */
function compareColor(name: string): string {
  return profileColor(name) ?? "var(--tt-brand)";
}

function ComparePanel({ profiles, sessions }: { profiles: Profile[]; sessions: Session[] }) {
  // Default to the two biggest spenders — the comparison people actually want.
  const byCost = [...profiles].sort((x, y) => y.usage.cost - x.usage.cost);
  const [open, setOpen] = useState(false);
  const [nameA, setNameA] = useState(byCost[0].name);
  const [nameB, setNameB] = useState(byCost[1].name);
  const a = profiles.find((p) => p.name === nameA);
  const b = profiles.find((p) => p.name === nameB);
  if (!a || !b) return null;
  const colA = compareColor(a.name);
  const colB = compareColor(b.name);

  const rows: { label: string; va: number; vb: number; fmt: (n: number) => string }[] = [
    { label: "Sessions", va: a.usage.sessions, vb: b.usage.sessions, fmt: (n) => String(n) },
    { label: "Total tokens", va: a.usage.total_tokens, vb: b.usage.total_tokens, fmt: formatTokens },
    { label: "Input tokens", va: a.usage.input_tokens, vb: b.usage.input_tokens, fmt: formatTokens },
    { label: "Output tokens", va: a.usage.output_tokens, vb: b.usage.output_tokens, fmt: formatTokens },
    { label: "All-time cost", va: a.usage.cost, vb: b.usage.cost, fmt: formatCost },
    { label: "7-day burn", va: a.usage.cost_7d, vb: b.usage.cost_7d, fmt: formatCost },
    { label: "Unattended 7d", va: a.usage.unattended_cost_7d, vb: b.usage.unattended_cost_7d, fmt: formatCost },
  ];

  const topModels = (name: string) => {
    const m = new Map<string, { count: number; cost: number }>();
    for (const s of sessions) {
      if (s.agent !== "hermes" || (s.hermes_profile || "default") !== name) continue;
      const key = s.model || "—";
      const cur = m.get(key) ?? { count: 0, cost: 0 };
      cur.count += 1;
      cur.cost += s.cost || 0;
      m.set(key, cur);
    }
    return [...m.entries()].sort((x, y) => y[1].cost - x[1].cost || y[1].count - x[1].count).slice(0, 5);
  };

  // One shared scale across both series — never two axes.
  const dailyMax = Math.max(
    ...a.usage.daily.map((d) => d.cost),
    ...b.usage.daily.map((d) => d.cost),
    0.000001,
  );
  const days = a.usage.daily.map((d, i) => ({
    date: d.date,
    ca: d.cost,
    cb: b.usage.daily[i]?.cost ?? 0,
  }));

  const Select = ({ value, onChange, exclude }: { value: string; onChange: (v: string) => void; exclude: string }) => (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="bg-[var(--tt-sunken)] border border-[var(--tt-border)] rounded px-2 py-1 text-[11px] font-mono text-[var(--tt-fg)] focus:outline-none focus:border-[var(--tt-border-strong)]"
    >
      {profiles.filter((p) => p.name !== exclude).map((p) => (
        <option key={p.name} value={p.name}>{p.name}</option>
      ))}
    </select>
  );

  return (
    <Card className="p-5 space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <GitCompareArrows size={14} className="text-[var(--tt-fg-muted)]" />
        <span className="text-[13px] font-semibold text-[var(--tt-fg)]">Compare profiles</span>
        {open ? (
          <>
            <Select value={nameA} onChange={setNameA} exclude={nameB} />
            <span className="text-[11px] text-[var(--tt-fg-dim)]">vs</span>
            <Select value={nameB} onChange={setNameB} exclude={nameA} />
            <button onClick={() => setOpen(false)} className="ml-auto text-[10px] text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)]">
              close
            </button>
          </>
        ) : (
          <button onClick={() => setOpen(true)} className="ml-auto text-[10px] text-[var(--tt-brand)] hover:underline">
            open
          </button>
        )}
      </div>

      {open && (
        <>
          {/* Legend: colored dot + name on each side, position fixed A-left B-right */}
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2">
            <div className="flex items-center gap-1.5 justify-end font-mono text-[12px] text-[var(--tt-fg)]">
              {a.name}
              <span className="h-2.5 w-2.5 rounded-full shrink-0" style={{ background: colA }} />
            </div>
            <span className="text-[9px] uppercase tracking-wider text-[var(--tt-fg-dim)] px-2">metric</span>
            <div className="flex items-center gap-1.5 font-mono text-[12px] text-[var(--tt-fg)]">
              <span className="h-2.5 w-2.5 rounded-full shrink-0" style={{ background: colB }} />
              {b.name}
            </div>
          </div>

          {/* Mirrored metric bars, each row scaled to its own max */}
          <div className="space-y-1.5">
            {rows.map((r) => {
              const max = Math.max(r.va, r.vb, 0.000001);
              return (
                <div key={r.label} className="grid grid-cols-[1fr_110px_1fr] items-center gap-2" title={`${r.label}: ${a.name} ${r.fmt(r.va)} vs ${b.name} ${r.fmt(r.vb)}`}>
                  <div className="flex items-center gap-2 justify-end">
                    <span className="text-[11px] tabular text-[var(--tt-fg-muted)]">{r.fmt(r.va)}</span>
                    <div className="h-3 rounded-l-[4px] min-w-[2px]" style={{ width: `${(r.va / max) * 100}%`, maxWidth: "70%", background: colA }} />
                  </div>
                  <div className="text-center text-[10px] text-[var(--tt-fg-dim)]">{r.label}</div>
                  <div className="flex items-center gap-2">
                    <div className="h-3 rounded-r-[4px] min-w-[2px]" style={{ width: `${(r.vb / max) * 100}%`, maxWidth: "70%", background: colB }} />
                    <span className="text-[11px] tabular text-[var(--tt-fg-muted)]">{r.fmt(r.vb)}</span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Paired daily-cost bars, one shared scale */}
          <div>
            <div className="text-[9px] uppercase tracking-wider text-[var(--tt-fg-dim)] mb-1.5">Daily cost, last 14 days</div>
            <div className="flex items-end gap-[3px] h-16">
              {days.map((d) => (
                <div key={d.date} className="flex-1 flex items-end justify-center gap-[2px] h-full" title={`${d.date} · ${a.name} ${formatCost(d.ca)} · ${b.name} ${formatCost(d.cb)}`}>
                  <div className="w-1/2 max-w-[10px] rounded-t-[3px] min-h-[2px]" style={{ height: `${Math.max(2, (d.ca / dailyMax) * 100)}%`, background: d.ca > 0 ? colA : "var(--tt-border)" }} />
                  <div className="w-1/2 max-w-[10px] rounded-t-[3px] min-h-[2px]" style={{ height: `${Math.max(2, (d.cb / dailyMax) * 100)}%`, background: d.cb > 0 ? colB : "var(--tt-border)" }} />
                </div>
              ))}
            </div>
            <div className="flex justify-between text-[9px] text-[var(--tt-fg-dim)] mt-1">
              <span>{days[0]?.date}</span>
              <span>{days[days.length - 1]?.date}</span>
            </div>
          </div>

          {/* Top models per side */}
          <div className="grid grid-cols-2 gap-4">
            {[{ p: a, col: colA }, { p: b, col: colB }].map(({ p, col }) => (
              <div key={p.name}>
                <div className="flex items-center gap-1.5 text-[9px] uppercase tracking-wider text-[var(--tt-fg-dim)] mb-1.5">
                  <span className="h-2 w-2 rounded-full" style={{ background: col }} /> Top models · {p.name}
                </div>
                {topModels(p.name).length === 0 ? (
                  <div className="text-[11px] italic text-[var(--tt-fg-faint)]">no sessions</div>
                ) : (
                  <div className="space-y-1">
                    {topModels(p.name).map(([m, info]) => (
                      <div key={m} className="flex items-center justify-between text-[11px]">
                        <span className="font-mono text-[var(--tt-fg)] truncate max-w-[65%]" title={m}>{m}</span>
                        <span className="tabular text-[var(--tt-fg-muted)]">{info.count} · {formatCost(info.cost)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </Card>
  );
}

function ProfileCard({ p, budget, onSaveBudget }: {
  p: Profile;
  budget: BudgetStatus | undefined;
  onSaveBudget: (v: number | null) => Promise<void>;
}) {
  const color = profileColor(p.name);
  const tint = profileTint(p.name);
  const burnDelta = p.usage.cost_7d - p.usage.cost_prev_7d;
  const maxDay = Math.max(...p.usage.daily.map((d) => d.cost), 0.000001);

  const [editing, setEditing] = useState(false);
  const [limitInput, setLimitInput] = useState("");
  const [saving, setSaving] = useState(false);
  const submitBudget = async () => {
    const v = parseFloat(limitInput);
    setSaving(true);
    try {
      await onSaveBudget(Number.isFinite(v) && v > 0 ? v : null);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="p-5 space-y-3">
      <div className="flex items-center gap-3">
        <div
          className={`h-10 w-10 rounded-full flex items-center justify-center font-semibold text-lg uppercase shrink-0 ${color ? "" : "bg-[var(--tt-border)] text-[var(--tt-fg)]"}`}
          style={color ? { background: tint ?? undefined, color, border: `1px solid ${color}` } : undefined}
        >
          {p.name.charAt(0)}
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-sm text-[var(--tt-fg)] truncate">{p.name}</span>
            {p.active && <Badge variant="brand" size="xs">active</Badge>}
            {p.is_default && <Badge variant="outline" size="xs">default home</Badge>}
          </div>
          <div className="text-[11px] text-[var(--tt-fg-muted)] truncate" title={p.description || undefined}>
            {p.description || (p.is_default ? "~/.hermes" : `~/.hermes/profiles/${p.name}`)}
          </div>
        </div>
        <div className="ml-auto shrink-0">
          <Badge variant={p.gateway.pid_alive ? "success" : "neutral"} size="xs" title={p.gateway.pid ? `PID ${p.gateway.pid}` : "no gateway"}>
            <Power size={10} /> {p.gateway.pid_alive ? "gateway up" : "gateway off"}
          </Badge>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-2 text-center">
        <div className="bg-[var(--tt-sunken)] border border-[var(--tt-border)] rounded-[var(--tt-radius)] p-2">
          <div className="text-[15px] tabular font-semibold text-[var(--tt-fg)]">{p.usage.sessions}</div>
          <div className="text-[9px] uppercase tracking-wider text-[var(--tt-fg-dim)]">Sessions</div>
        </div>
        <div className="bg-[var(--tt-sunken)] border border-[var(--tt-border)] rounded-[var(--tt-radius)] p-2">
          <div className="text-[15px] tabular font-semibold text-[var(--tt-fg)]">{formatTokens(p.usage.total_tokens)}</div>
          <div className="text-[9px] uppercase tracking-wider text-[var(--tt-fg-dim)]">Tokens</div>
        </div>
        <div className="bg-[var(--tt-sunken)] border border-[var(--tt-border)] rounded-[var(--tt-radius)] p-2">
          <div className="text-[15px] tabular font-semibold text-[var(--tt-fg)]">{formatCost(p.usage.cost)}</div>
          <div className="text-[9px] uppercase tracking-wider text-[var(--tt-fg-dim)]">Cost</div>
        </div>
        <div className="bg-[var(--tt-sunken)] border border-[var(--tt-border)] rounded-[var(--tt-radius)] p-2">
          <div className="text-[15px] tabular font-semibold text-[var(--tt-fg)]">{p.usage.last_activity ? timeAgo(p.usage.last_activity) : "—"}</div>
          <div className="text-[9px] uppercase tracking-wider text-[var(--tt-fg-dim)]">Last active</div>
        </div>
      </div>

      {/* Burn strip: 14-day daily-cost sparkline + 7d vs prior-7d trend + unattended share */}
      <div className="flex items-end gap-3">
        <div className="flex items-end gap-[2px] h-8 flex-1" title="Daily cost, last 14 days">
          {p.usage.daily.map((d) => (
            <div
              key={d.date}
              className="flex-1 rounded-sm min-h-[2px]"
              style={{
                height: `${Math.max(2, Math.round((d.cost / maxDay) * 100))}%`,
                background: d.cost > 0 ? (color ?? "var(--tt-brand)") : "var(--tt-border)",
                opacity: d.cost > 0 ? 0.9 : 0.5,
              }}
              title={`${d.date} · ${formatCost(d.cost)}`}
            />
          ))}
        </div>
        <div className="text-right shrink-0">
          <div className="flex items-center justify-end gap-1 text-[12px] tabular font-semibold text-[var(--tt-fg)]">
            {formatCost(p.usage.cost_7d)}
            {burnDelta > 0.0001 ? (
              <TrendingUp size={11} className="text-[var(--tt-warn-fg)]" />
            ) : burnDelta < -0.0001 ? (
              <TrendingDown size={11} className="text-[var(--tt-success-fg)]" />
            ) : null}
          </div>
          <div className="text-[9px] uppercase tracking-wider text-[var(--tt-fg-dim)]">7-day burn</div>
          {p.usage.unattended_cost_7d > 0 && (
            <div className="flex items-center justify-end gap-1 text-[10px] tabular text-[var(--tt-warn-fg)]" title="Spent by cron / subagent / kanban sessions nobody was watching">
              <Bot size={10} /> {formatCost(p.usage.unattended_cost_7d)} unattended
            </div>
          )}
        </div>
      </div>

      {/* Budget: alerts-only, rides the standard budgets engine */}
      <div className="flex items-center gap-2 min-h-6">
        <Wallet size={11} className="text-[var(--tt-fg-dim)] shrink-0" />
        {budget && !editing ? (
          <>
            <div className="flex-1 h-1.5 rounded-full bg-[var(--tt-border)] overflow-hidden">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${Math.min(100, Math.round(budget.fraction * 100))}%`,
                  background: budget.alert_level ? "var(--tt-danger-fg)" : (color ?? "var(--tt-brand)"),
                }}
              />
            </div>
            <button
              onClick={() => { setLimitInput(String(budget.limit_value)); setEditing(true); }}
              className="text-[10px] tabular text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] shrink-0"
              title="Edit monthly budget"
            >
              {formatCost(budget.used)} / {formatCost(budget.limit_value)} mo
            </button>
            {budget.alert_level && (
              <Badge variant="danger" size="xs">{Math.round(budget.fraction * 100)}%</Badge>
            )}
          </>
        ) : editing ? (
          <div className="flex items-center gap-1.5 flex-1">
            <input
              type="number"
              min="0"
              step="0.5"
              value={limitInput}
              onChange={(e) => setLimitInput(e.target.value)}
              placeholder="USD / month"
              className="w-24 px-2 py-1 bg-[var(--tt-sunken)] border border-[var(--tt-border)] rounded text-[11px] text-[var(--tt-fg)] focus:outline-none focus:border-[var(--tt-border-strong)]"
              autoFocus
            />
            <button onClick={submitBudget} disabled={saving} className="text-[10px] text-[var(--tt-brand)] hover:underline disabled:opacity-50">
              {saving ? "saving…" : "save"}
            </button>
            {budget && (
              <button onClick={() => { setLimitInput(""); submitBudget(); }} disabled={saving} className="text-[10px] text-[var(--tt-danger-fg)] hover:underline disabled:opacity-50">
                remove
              </button>
            )}
            <button onClick={() => setEditing(false)} disabled={saving} className="text-[10px] text-[var(--tt-fg-dim)] hover:underline">
              cancel
            </button>
          </div>
        ) : (
          <button
            onClick={() => { setLimitInput(""); setEditing(true); }}
            className="text-[10px] text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)]"
          >
            Set monthly budget (alerts only)
          </button>
        )}
      </div>

      <div className="flex items-center gap-3 text-[11px] text-[var(--tt-fg-muted)]">
        <span className="inline-flex items-center gap-1"><BookOpen size={11} /> {p.skills_count} skills</span>
        <span className="inline-flex items-center gap-1"><Clock size={11} /> {p.cron_jobs} cron jobs</span>
        {p.soul_exists && <span className="inline-flex items-center gap-1"><Sparkles size={11} /> SOUL.md</span>}
      </div>
    </Card>
  );
}
