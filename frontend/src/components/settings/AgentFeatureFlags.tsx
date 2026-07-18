"use client";

import { useEffect, useState } from "react";
import { FlaskConical, Check, X } from "lucide-react";

import { apiFetch } from "@/lib/api";
import { Card, Badge, AgentBadge, Skeleton, EmptyState } from "@/components/ui";
import { cn } from "@/lib/cn";

interface Flag {
  name: string;
  value: boolean | string | number;
  kind: "bool" | "value";
}
interface AgentFeatures {
  agent: string;
  detected: boolean;
  source: string;
  flags: Flag[];
  note?: string;
}

export function AgentFeatureFlags() {
  const [data, setData] = useState<AgentFeatures[] | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    apiFetch("/config/agent-features")
      .then((r) => r.json())
      .then((d) => { if (!cancelled) setData(d.agents ?? []); })
      .catch(() => { if (!cancelled) setData([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <Card>
        <EmptyState
          icon={<FlaskConical size={18} />}
          title="No local feature flags found"
          description="None of the agents that expose experimental flags on disk (Copilot, Codex, Claude Code) are set up on this machine."
        />
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      {data.map((a) => <AgentFlagsCard key={a.agent} a={a} />)}
    </div>
  );
}

function AgentFlagsCard({ a }: { a: AgentFeatures }) {
  return (
    <Card padding="md">
      <div className="flex items-start justify-between gap-4 mb-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <AgentBadge agent={a.agent} />
          {a.note && (
            <p className="text-[12px] text-[var(--tt-fg-dim)] leading-relaxed">{a.note}</p>
          )}
        </div>
        <span
          className="shrink-0 text-[10px] font-mono text-[var(--tt-fg-faint)] truncate max-w-[280px]"
          title={a.source}
        >
          {a.source}
        </span>
      </div>

      {a.flags.length === 0 ? (
        <p className="text-[12px] text-[var(--tt-fg-dim)] italic">
          Config present, but no known feature flags are set.
        </p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {a.flags.map((f) => <FlagPill key={f.name} flag={f} />)}
        </div>
      )}
    </Card>
  );
}

function FlagPill({ flag }: { flag: Flag }) {
  // Boolean flags read as on/off with an icon; value flags show "name: value".
  if (flag.kind === "bool") {
    const on = flag.value === true;
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] font-medium",
          on
            ? "border-[color:var(--tt-success)]/30 bg-[color:var(--tt-success)]/10 text-[var(--tt-success-fg)]"
            : "border-[var(--tt-border)] bg-[var(--tt-sunken)] text-[var(--tt-fg-dim)]",
        )}
      >
        {on ? <Check size={11} /> : <X size={11} />}
        <span className="font-mono normal-case">{flag.name}</span>
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md border border-[var(--tt-border)] bg-[var(--tt-sunken)] px-2 py-1 text-[11px]">
      <span className="font-mono text-[var(--tt-fg-muted)]">{flag.name}</span>
      <Badge variant="neutral" size="xs" className="font-mono normal-case">{String(flag.value)}</Badge>
    </span>
  );
}
