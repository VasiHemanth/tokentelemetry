"use client";

import { Brain, User as UserIcon } from "lucide-react";
import { useResource } from "@/lib/api";
import {
  PageHeader, Card, CardHeader, CardTitle, EmptyState,
} from "@/components/ui";

interface MemoryFile {
  entries: string[];
  char_count: number;
  exists: boolean;
}

interface MemoryResp {
  memory: MemoryFile;
  user: MemoryFile;
  memory_char_limit: number;
  user_char_limit: number;
}

export default function HermesMemoryPage() {
  const { data, loading } = useResource<MemoryResp>("/hermes/memory", { pollMs: 30_000 });

  return (
    <div className="px-8 py-8 max-w-[1600px] mx-auto space-y-8 pb-20">
      <PageHeader
        backHref="/hermes"
        eyebrow="Hermes Agent"
        icon={<Brain size={20} />}
        title="Memory"
        description="Hermes's persistent facts (MEMORY.md) and your profile (USER.md). Written by the agent's memory tool, frozen into the system prompt at session start."
      />

      {!loading && !data?.memory.exists && !data?.user.exists && (
        <EmptyState
          title="No memory files yet"
          description="Hermes creates MEMORY.md and USER.md when the agent uses the memory tool for the first time. Both live at ~/.hermes/memories/."
        />
      )}

      {data?.memory.exists && (
        <MemoryCard
          icon={<Brain size={14} />}
          title="Agent memory"
          subtitle="MEMORY.md — environment facts, conventions, tool quirks"
          file={data.memory}
          limit={data.memory_char_limit}
        />
      )}
      {data?.user.exists && (
        <MemoryCard
          icon={<UserIcon size={14} />}
          title="User profile"
          subtitle="USER.md — preferences, communication style, habits"
          file={data.user}
          limit={data.user_char_limit}
        />
      )}
    </div>
  );
}

function MemoryCard({
  icon, title, subtitle, file, limit,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  file: MemoryFile;
  limit: number;
}) {
  const pct = limit > 0 ? Math.min(100, Math.round((file.char_count / limit) * 100)) : 0;
  const barColor = pct >= 90 ? "bg-red-500" : pct >= 70 ? "bg-amber-500" : "bg-emerald-500";
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <span className="flex items-center gap-2">
            {icon}
            {title}
          </span>
        </CardTitle>
        <div className="ml-auto text-[11px] text-[var(--tt-fg-muted)] flex items-center gap-3">
          <span className="tabular">{file.entries.length} entries</span>
          <span className="tabular">{file.char_count.toLocaleString()} / {limit.toLocaleString()} chars</span>
        </div>
      </CardHeader>
      <div className="px-5 pb-2">
        <div className="text-[10px] text-[var(--tt-fg-dim)] mb-1.5 italic">{subtitle}</div>
        <div className="h-1.5 bg-[var(--tt-sunken)] rounded-full overflow-hidden">
          <div className={`h-full ${barColor} transition-all`} style={{ width: `${pct}%` }} />
        </div>
      </div>
      <div className="px-5 pb-5 mt-3 space-y-2">
        {file.entries.map((e, i) => (
          <div key={i} className="bg-[var(--tt-sunken)] border border-[var(--tt-border)] rounded-[var(--tt-radius)] p-3 text-[12px] text-[var(--tt-fg)] whitespace-pre-wrap leading-relaxed">
            {e}
          </div>
        ))}
      </div>
    </Card>
  );
}
