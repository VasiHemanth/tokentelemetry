"use client";

import { useResource } from "@/lib/api";
import { PageHeader, Card, Table, THead, TBody, TR, TH, TD, Badge, EmptyState } from "@/components/ui";
import { Signal, Power } from "lucide-react";
import { formatDistanceToNow } from "date-fns";

interface GatewayPlatform {
  name: string;
  state?: string | null;
  error_code?: string | null;
}

interface GatewayOverview {
  gateway?: {
    pid_alive: boolean;
    pid?: number | null;
    state?: string | null;
    updated_at?: string | null;
    platforms?: GatewayPlatform[];
  };
}

export default function GatewayPage() {
  const res = useResource<GatewayOverview>("/hermes/overview", { pollMs: 10000 });
  const loading = !res.data;
  const gateway = res.data?.gateway;

  if (loading) return <div className="p-8">Loading...</div>;

  return (
    <div className="px-8 py-8 max-w-[1200px] mx-auto space-y-6 pb-20">
      <PageHeader
        backHref="/hermes"
        icon={<div className="h-10 w-10 grid place-items-center rounded-[var(--tt-radius)] bg-emerald-500/10 border border-emerald-500/30"><Signal className="text-emerald-500" size={20} /></div>}
        eyebrow="Hermes Agent"
        title="Gateway Status"
        description="Live messaging gateway connections across platforms"
      />
      {!gateway ? (
        <EmptyState title="Gateway off" description="Gateway state file is missing." />
      ) : (
        <div className="space-y-6">
          <Card className="p-6 flex items-center justify-between">
            <div>
              <div className="text-sm text-[var(--tt-fg-muted)] mb-1">Gateway Process</div>
              <div className="flex items-center gap-2">
                <Badge variant={gateway.pid_alive ? "success" : "danger"}>
                  <Power size={12} className="mr-1" />
                  {gateway.pid_alive ? "Running" : "Stopped"}
                </Badge>
                {gateway.pid && <span className="font-mono text-xs text-[var(--tt-fg-muted)]">PID: {gateway.pid}</span>}
              </div>
            </div>
            <div className="text-right">
              <div className="text-sm text-[var(--tt-fg-muted)] mb-1">State</div>
              <div className="font-mono text-sm uppercase">{gateway.state || "UNKNOWN"}</div>
              {gateway.updated_at && (
                <div className="text-xs text-[var(--tt-fg-faint)] mt-1">
                  Updated {formatDistanceToNow(new Date(gateway.updated_at), { addSuffix: true })}
                </div>
              )}
            </div>
          </Card>
          
          <Card>
            <div className="p-4 border-b border-[var(--tt-border)] font-medium">Platform Connections</div>
            <Table>
              <THead>
                <TR><TH className="pl-4">Platform</TH><TH>Status</TH><TH>Error</TH></TR>
              </THead>
              <TBody>
                {gateway.platforms?.map((p) => (
                  <TR key={p.name}>
                    <TD className="pl-4 font-mono text-sm">{p.name}</TD>
                    <TD>
                      <Badge variant={p.state === "connected" ? "success" : "warn"}>{p.state || "unknown"}</Badge>
                    </TD>
                    <TD className="text-xs text-[var(--tt-danger-fg)]">{p.error_code || "—"}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </Card>
        </div>
      )}
    </div>
  );
}
