"use client";

import { useResource } from "@/lib/api";
import { PageHeader, Card, EmptyState, StatTile, Badge } from "@/components/ui";
import { formatTokens, formatCost } from "@/lib/format";
import { timeAgo } from "@/lib/notifications";
import { Users, Power, BookOpen, Clock, Sparkles } from "lucide-react";

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

export default function ProfilesPage() {
  const { data, loading } = useResource<ProfilesResp>("/hermes/profiles", { pollMs: 60_000 });
  const profiles = data?.profiles || [];
  const named = profiles.filter((p) => !p.is_default);
  const totals = profiles.reduce(
    (acc, p) => ({
      sessions: acc.sessions + p.usage.sessions,
      tokens: acc.tokens + p.usage.total_tokens,
      cost: acc.cost + p.usage.cost,
    }),
    { sessions: 0, tokens: 0, cost: 0 },
  );

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
        <StatTile label="Cost" value={loading ? "—" : formatCost(totals.cost)} />
      </div>

      {loading ? (
        <div className="animate-pulse h-32 bg-[var(--tt-panel)] rounded-xl" />
      ) : profiles.length === 0 ? (
        <EmptyState title="Hermes not found" description="No ~/.hermes directory on this machine." />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {profiles.map((p) => (
            <Card key={p.name} className="p-5 space-y-3">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 bg-[var(--tt-border)] text-[var(--tt-fg)] rounded-full flex items-center justify-center font-semibold text-lg uppercase shrink-0">
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

              <div className="flex items-center gap-3 text-[11px] text-[var(--tt-fg-muted)]">
                <span className="inline-flex items-center gap-1"><BookOpen size={11} /> {p.skills_count} skills</span>
                <span className="inline-flex items-center gap-1"><Clock size={11} /> {p.cron_jobs} cron jobs</span>
                {p.soul_exists && <span className="inline-flex items-center gap-1"><Sparkles size={11} /> SOUL.md</span>}
              </div>
            </Card>
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
