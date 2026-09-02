"use client";

import React from "react";
import { Server, Cpu, HardDrive } from "lucide-react";
import { useResource } from "@/lib/api";
import type { LocalRuntime } from "@/lib/power";
import { Card, CardHeader, CardTitle, Badge, Skeleton } from "@/components/ui";

function bytes(n?: number | null): string {
  if (n == null || !Number.isFinite(n)) return "—";
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)} GB`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(0)} MB`;
  return `${n} B`;
}

export default function LocalRuntimePanel() {
  const { data, loading, error } = useResource<LocalRuntime>("/local-runtime", {
    pollMs: 15_000,
  });

  const online = data?.ollama?.ollama === "online";

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Card padding="lg">
        <CardHeader>
          <CardTitle>
            <Server size={14} className="text-[var(--tt-brand)]" /> Ollama runtime
          </CardTitle>
          {loading && !data ? (
            <Skeleton className="h-5 w-16" />
          ) : (
            <Badge variant={online ? "success" : "neutral"} size="sm">
              {online ? "Online" : "Offline"}
            </Badge>
          )}
        </CardHeader>
        {error && (
          <p className="text-[12px] text-[var(--tt-fg-muted)]">
            Could not probe local runtime ({String(error)}).
          </p>
        )}
        {data && (
          <div className="space-y-3 text-[12px]">
            <div className="text-[var(--tt-fg-dim)]">
              Endpoint{" "}
              <span className="font-mono text-[var(--tt-fg)]">
                {data.ollama.base_url || "127.0.0.1:11434"}
              </span>
              {data.platform ? (
                <span className="text-[var(--tt-fg-faint)]"> · {data.platform}</span>
              ) : null}
            </div>
            {online ? (
              <>
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-[var(--tt-fg-dim)] mb-1.5">
                    Installed models ({data.ollama.models.length})
                  </div>
                  <ul className="space-y-1 max-h-40 overflow-y-auto">
                    {data.ollama.models.slice(0, 24).map((m) => (
                      <li
                        key={m.name || JSON.stringify(m)}
                        className="flex items-center justify-between gap-2 font-mono text-[11px]"
                      >
                        <span className="truncate text-[var(--tt-fg)]" title={m.name}>
                          {m.name}
                        </span>
                        <span className="shrink-0 text-[var(--tt-fg-faint)]">
                          {[m.parameter_size, m.quantization_level].filter(Boolean).join(" · ") ||
                            bytes(m.size)}
                        </span>
                      </li>
                    ))}
                    {data.ollama.models.length === 0 && (
                      <li className="text-[var(--tt-fg-muted)]">No models listed.</li>
                    )}
                  </ul>
                </div>
                {data.ollama.running.length > 0 && (
                  <div>
                    <div className="text-[10px] uppercase tracking-wider text-[var(--tt-fg-dim)] mb-1.5">
                      Loaded now
                    </div>
                    <ul className="space-y-1">
                      {data.ollama.running.map((m) => (
                        <li key={`run-${m.name}`} className="font-mono text-[11px] text-emerald-400">
                          {m.name}
                          {m.size_vram != null ? (
                            <span className="text-[var(--tt-fg-faint)]"> · VRAM {bytes(m.size_vram)}</span>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            ) : (
              <p className="text-[var(--tt-fg-muted)]">
                Start Ollama on this machine to list installed models. Works on macOS, Linux, and
                Windows (loopback :11434).
              </p>
            )}
          </div>
        )}
      </Card>

      <Card padding="lg">
        <CardHeader>
          <CardTitle>
            <Cpu size={14} className="text-amber-400" /> GPU snapshot
          </CardTitle>
          {data?.gpu?.available ? (
            <Badge variant="success" size="sm">NVIDIA</Badge>
          ) : (
            <Badge variant="neutral" size="sm">Optional</Badge>
          )}
        </CardHeader>
        {data?.gpu?.available && data.gpu.gpus.length > 0 ? (
          <ul className="space-y-3">
            {data.gpu.gpus.map((g) => (
              <li key={g.index} className="text-[12px]">
                <div className="font-medium text-[var(--tt-fg)]">{g.name}</div>
                <div className="mt-1 grid grid-cols-3 gap-2 text-[11px] text-[var(--tt-fg-muted)]">
                  <span className="flex items-center gap-1">
                    <HardDrive size={11} />{" "}
                    {g.memory_used_mb != null && g.memory_total_mb != null
                      ? `${Math.round(g.memory_used_mb)} / ${Math.round(g.memory_total_mb)} MB`
                      : "—"}
                  </span>
                  <span>Util {g.utilization_pct != null ? `${g.utilization_pct.toFixed(0)}%` : "—"}</span>
                  <span>Power {g.power_w != null ? `${g.power_w.toFixed(0)} W` : "—"}</span>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[12px] text-[var(--tt-fg-muted)]">
            {data?.gpu?.reason ||
              "No nvidia-smi reading (Apple Silicon / AMD use power config + Measure instead)."}
            {data?.hf_usage ? (
              <span className="block mt-2 text-[var(--tt-fg-faint)]">
                Hugging Face cache: {data.hf_usage}
              </span>
            ) : null}
          </p>
        )}
      </Card>
    </div>
  );
}
