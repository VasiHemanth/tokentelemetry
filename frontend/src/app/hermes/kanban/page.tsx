"use client";

import Link from "next/link";
import { useResource } from "@/lib/api";
import { PageHeader, Card, CardHeader, CardTitle, StatTile, EmptyState, Badge } from "@/components/ui";
import { formatTokens, formatCost } from "@/lib/format";
import { timeAgo } from "@/lib/notifications";
import { profileColor, profileTint } from "@/lib/profileColor";
import { Kanban, AlertTriangle, Bot } from "lucide-react";

interface TaskRuns {
  count: number;
  failed: number;
  profiles: string[];
}

interface Task {
  id: string;
  title: string;
  status: string;
  assignee: string | null;
  priority: number;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  consecutive_failures: number;
  last_failure_error: string | null;
  session_id: string | null;
  cost: number;
  tokens: number;
  runs: TaskRuns | null;
}

interface Board {
  profile: string | null;
  board: string;
  tasks: Task[];
  totals: {
    tasks: number;
    cost: number;
    by_status: Record<string, number>;
    by_assignee: { assignee: string; tasks: number; cost: number }[];
  };
}

interface KanbanResp {
  installed: boolean;
  boards: Board[];
}

// Hermes's own status vocabulary, in board order. Archived is summarized, not
// rendered as a column.
const STATUS_ORDER = ["triage", "todo", "scheduled", "ready", "running", "blocked", "review", "done"];
const STATUS_VARIANT: Record<string, "neutral" | "info" | "warn" | "success" | "danger"> = {
  running: "info", blocked: "warn", done: "success", review: "info",
};

export default function HermesKanbanPage() {
  const { data, loading } = useResource<KanbanResp>("/hermes/kanban", { pollMs: 30_000 });
  const boards = data?.boards ?? [];
  const allTasks = boards.flatMap((b) => b.tasks);
  const totalCost = boards.reduce((a, b) => a + b.totals.cost, 0);
  const failing = allTasks.filter((t) => t.consecutive_failures > 0).length;
  const costed = allTasks.filter((t) => t.cost > 0).length;

  return (
    <div className="px-8 py-8 max-w-[1600px] mx-auto space-y-6 pb-20">
      <PageHeader
        backHref="/hermes"
        icon={<div className="h-10 w-10 grid place-items-center rounded-[var(--tt-radius)] bg-rose-500/10 border border-rose-500/30"><Kanban className="text-rose-500" size={20} /></div>}
        eyebrow="Hermes Agent"
        title="Kanban"
        description="Swarm task boards with per-task cost — Hermes tracks the tasks, TokenTelemetry prices them via each task's linked session."
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile label="Boards" value={loading ? "—" : String(boards.length)} />
        <StatTile label="Tasks" value={loading ? "—" : String(allTasks.length)} hint={loading || !failing ? undefined : `${failing} failing`} />
        <StatTile label="Attributed cost" value={loading ? "—" : formatCost(totalCost)} hint={loading || !allTasks.length ? undefined : `${costed}/${allTasks.length} tasks linked to a session`} />
        <StatTile label="Workers" value={loading ? "—" : String(new Set(allTasks.map((t) => t.assignee).filter(Boolean)).size)} />
      </div>

      {loading ? (
        <div className="animate-pulse h-40 bg-[var(--tt-panel)] rounded-xl" />
      ) : !data?.installed ? (
        <EmptyState
          title="No kanban boards"
          description="No kanban.db found under ~/.hermes (or any profile). Create tasks with `hermes kanban` or launch a swarm and the board shows up here."
        />
      ) : allTasks.length === 0 ? (
        <EmptyState
          title="Boards are empty"
          description="Kanban is set up but no tasks have been created yet. Older Hermes versions don't link tasks to sessions (no session_id column) — cost shows as — for those."
        />
      ) : (
        boards.map((b) => <BoardCard key={`${b.profile ?? "default"}/${b.board}`} b={b} />)
      )}
    </div>
  );
}

function BoardCard({ b }: { b: Board }) {
  const profileName = b.profile ?? "default";
  const color = profileColor(profileName);
  const byStatus = new Map<string, Task[]>();
  for (const t of b.tasks) {
    const s = t.status === "archived" ? "archived" : t.status;
    if (!byStatus.has(s)) byStatus.set(s, []);
    byStatus.get(s)!.push(t);
  }
  const columns = STATUS_ORDER.filter((s) => byStatus.has(s));
  const other = [...byStatus.keys()].filter((s) => !STATUS_ORDER.includes(s) && s !== "archived");
  const archived = byStatus.get("archived")?.length ?? 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <span className="flex items-center gap-2 font-mono">
            {color && <span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />}
            {profileName} / {b.board}
          </span>
        </CardTitle>
        <div className="ml-auto text-[11px] tabular text-[var(--tt-fg-muted)]">
          {b.totals.tasks} task{b.totals.tasks === 1 ? "" : "s"}
          {b.totals.cost > 0 && ` · ${formatCost(b.totals.cost)}`}
          {archived > 0 && ` · ${archived} archived`}
        </div>
      </CardHeader>

      {/* Per-worker cost lanes — the "which persona is burning budget" view */}
      {b.totals.by_assignee.length > 0 && (
        <div className="px-5 pb-3 flex flex-wrap gap-2">
          {b.totals.by_assignee.map((a) => (
            <span
              key={a.assignee}
              className="inline-flex items-center gap-1.5 font-mono text-[10px] px-2 h-6 rounded-full border border-[var(--tt-border)] text-[var(--tt-fg-muted)]"
              style={profileColor(a.assignee) ? {
                color: profileColor(a.assignee)!,
                borderColor: profileColor(a.assignee)!,
                background: profileTint(a.assignee)!,
              } : undefined}
            >
              <Bot size={10} /> {a.assignee}
              <span className="tabular">{a.tasks} · {a.cost > 0 ? formatCost(a.cost) : "—"}</span>
            </span>
          ))}
        </div>
      )}

      <div className="px-5 pb-5 overflow-x-auto">
        <div className="flex gap-3 min-w-fit">
          {[...columns, ...other].map((status) => (
            <div key={status} className="w-[260px] shrink-0 space-y-2">
              <div className="flex items-center gap-2">
                <Badge variant={STATUS_VARIANT[status] ?? "neutral"} size="xs">{status}</Badge>
                <span className="text-[10px] tabular text-[var(--tt-fg-dim)]">{byStatus.get(status)!.length}</span>
              </div>
              {byStatus.get(status)!.map((t) => (
                <div key={t.id} className="bg-[var(--tt-sunken)] border border-[var(--tt-border)] rounded-[var(--tt-radius)] p-3 space-y-1.5">
                  <div className="text-[12px] text-[var(--tt-fg)] line-clamp-2" title={t.title}>{t.title}</div>
                  <div className="flex items-center justify-between gap-2 text-[10px] text-[var(--tt-fg-muted)]">
                    <span className="font-mono truncate" title={t.assignee ?? undefined}>{t.assignee || "unassigned"}</span>
                    <span className="tabular shrink-0">
                      {t.cost > 0 ? (
                        <span title={`${formatTokens(t.tokens)} tokens`}>{formatCost(t.cost)}</span>
                      ) : "—"}
                    </span>
                  </div>
                  <div className="flex items-center justify-between gap-2 text-[9px] text-[var(--tt-fg-dim)]">
                    <span>{t.completed_at ? `done ${timeAgo(t.completed_at)}` : t.started_at ? `started ${timeAgo(t.started_at)}` : t.created_at ? timeAgo(t.created_at) : ""}</span>
                    {t.runs && t.runs.count > 0 && (
                      <span className="tabular" title={t.runs.profiles.length ? `Ran on: ${t.runs.profiles.join(", ")}` : undefined}>
                        {t.runs.count} run{t.runs.count === 1 ? "" : "s"}{t.runs.failed > 0 && ` · ${t.runs.failed} failed`}
                      </span>
                    )}
                  </div>
                  {t.consecutive_failures > 0 && (
                    <div className="flex items-center gap-1 text-[9px] text-[var(--tt-danger-fg)]" title={t.last_failure_error ?? undefined}>
                      <AlertTriangle size={9} /> {t.consecutive_failures} consecutive failure{t.consecutive_failures === 1 ? "" : "s"}
                    </div>
                  )}
                  {t.session_id && (
                    <Link
                      href={`/sessions/${t.session_id}?agent=hermes&from=${encodeURIComponent("/hermes/kanban")}`}
                      className="block text-[9px] font-mono text-[var(--tt-brand)] hover:underline truncate"
                    >
                      {t.session_id}
                    </Link>
                  )}
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}
