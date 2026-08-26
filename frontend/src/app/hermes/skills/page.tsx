"use client";

import { useMemo, useState } from "react";
import { BookOpen, Search } from "lucide-react";
import { useResource } from "@/lib/api";
import {
  PageHeader, Card, CardHeader, CardTitle, StatTile, EmptyState, Badge,
} from "@/components/ui";

interface Skill {
  name: string;
  category: string;
  description: string;
  platforms: string[];
  conditions: {
    requires_toolsets?: string[];
    requires_tools?: string[];
    fallback_for_toolsets?: string[];
    fallback_for_tools?: string[];
  };
}

interface SkillsResp {
  snapshot_loaded: number;
  skills: Skill[];
  categories: Record<string, string>;
}

export default function HermesSkillsPage() {
  const { data, loading } = useResource<SkillsResp>("/hermes/skills", { pollMs: 60_000 });
  const [filter, setFilter] = useState("");

  const grouped = useMemo(() => {
    if (!data) return new Map<string, Skill[]>();
    const m = new Map<string, Skill[]>();
    const q = filter.trim().toLowerCase();
    for (const s of data.skills) {
      if (q && !(s.name?.toLowerCase().includes(q) || s.description?.toLowerCase().includes(q) || s.category?.toLowerCase().includes(q))) continue;
      const cat = s.category || "uncategorized";
      if (!m.has(cat)) m.set(cat, []);
      m.get(cat)!.push(s);
    }
    return new Map([...m.entries()].sort((a, b) => a[0].localeCompare(b[0])));
  }, [data, filter]);

  return (
    <div className="px-8 py-8 max-w-[1600px] mx-auto space-y-8 pb-20">
      <PageHeader
        backHref="/hermes"
        eyebrow="Hermes Agent"
        icon={<BookOpen size={20} />}
        title="Skills"
        description="Loaded skills from ~/.hermes/skills/ — read from the prompt snapshot Hermes itself uses."
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile label="Skills loaded" value={loading ? "—" : String(data?.snapshot_loaded ?? 0)} />
        <StatTile label="Categories" value={loading ? "—" : String(Object.keys(data?.categories ?? {}).length)} />
        <StatTile
          label="Platform-restricted"
          value={loading ? "—" : String(data?.skills.filter((s) => s.platforms?.length).length ?? 0)}
        />
        <StatTile
          label="With conditions"
          value={loading ? "—" : String(data?.skills.filter((s) => Object.values(s.conditions || {}).some((v) => Array.isArray(v) && v.length)).length ?? 0)}
        />
      </div>

      <div className="relative">
        <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--tt-fg-dim)]" />
        <input
          type="text"
          placeholder="Filter skills…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="w-full pl-9 pr-3 py-2 bg-[var(--tt-sunken)] border border-[var(--tt-border)] rounded-[var(--tt-radius)] text-[13px] text-[var(--tt-fg)] placeholder:text-[var(--tt-fg-dim)] focus:outline-none focus:border-[var(--tt-border-strong)]"
        />
      </div>

      {!loading && (data?.skills.length ?? 0) === 0 && (
        <EmptyState
          title="No skills snapshot"
          description="Run Hermes once to generate ~/.hermes/.skills_prompt_snapshot.json — it's written automatically when the agent starts."
        />
      )}

      {[...grouped.entries()].map(([cat, skills]) => (
        <Card key={cat}>
          <CardHeader>
            <CardTitle>
              <span className="flex items-center gap-2 font-mono">
                {cat}
                <span className="text-[10px] tabular text-[var(--tt-fg-muted)]">{skills.length}</span>
              </span>
            </CardTitle>
            {data?.categories[cat] && (
              <div className="ml-auto text-[10px] text-[var(--tt-fg-dim)] italic">{data.categories[cat]}</div>
            )}
          </CardHeader>
          <div className="px-5 pb-5 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {skills.map((s) => (
              <div key={`${cat}/${s.name}`} className="bg-[var(--tt-sunken)] border border-[var(--tt-border)] rounded-[var(--tt-radius)] p-3">
                <div className="flex items-start justify-between gap-2 mb-1">
                  <div className="font-mono text-[12px] text-[var(--tt-fg)] truncate" title={s.name}>{s.name}</div>
                  {s.platforms?.length > 0 && (
                    <Badge variant="outline" size="xs">
                      {s.platforms.join(", ")}
                    </Badge>
                  )}
                </div>
                <div className="text-[11px] text-[var(--tt-fg-muted)] line-clamp-2">{s.description || "—"}</div>
                {Object.entries(s.conditions || {}).map(([k, v]) => (
                  Array.isArray(v) && v.length > 0 ? (
                    <div key={k} className="mt-1.5 text-[9px] font-mono text-[var(--tt-fg-dim)] uppercase tracking-wider">
                      {k.replace(/_/g, " ")}: <span className="text-[var(--tt-fg-muted)] normal-case">{v.join(", ")}</span>
                    </div>
                  ) : null
                ))}
              </div>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}
