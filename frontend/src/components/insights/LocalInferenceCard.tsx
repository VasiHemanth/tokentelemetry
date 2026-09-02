"use client";

import React from "react";
import { Zap, Gauge, Leaf, Clock, DollarSign } from "lucide-react";
import type { LocalSessionMetrics } from "@/lib/insights";
import { formatEnergy, formatCo2, formatTokPerSec, formatWhPer1M } from "@/lib/insights";
import { formatCost } from "@/lib/format";

interface Props {
  local: LocalSessionMetrics;
  model?: string;
}

export default function LocalInferenceCard({ local, model }: Props) {
  const items = [
    {
      icon: <Gauge size={12} />,
      label: "Throughput",
      value: formatTokPerSec(local.tok_per_sec, local.tok_per_sec_source),
      hint: local.tok_per_sec_source === "measured" ? "Measured" : "Estimated from model size",
    },
    {
      icon: <Clock size={12} />,
      label: "Gen time",
      value:
        local.gen_seconds >= 60
          ? `${(local.gen_seconds / 60).toFixed(1)}m`
          : `${local.gen_seconds.toFixed(1)}s`,
      hint: "Output tokens ÷ tok/s",
    },
    {
      icon: <Zap size={12} />,
      label: "Energy",
      value: formatEnergy(local.energy_wh),
      hint: formatWhPer1M(local.wh_per_1m_output) + " / 1M out",
    },
    {
      icon: <DollarSign size={12} />,
      label: "Electricity",
      value: formatCost(local.electricity_cost),
      hint: `Saved ${formatCost(local.savings_usd)} vs ${local.reference_cloud_model}`,
    },
    {
      icon: <Leaf size={12} />,
      label: "CO₂",
      value: formatCo2(local.co2_g),
      hint: `${local.load_watts} W load`,
    },
  ];

  return (
    <div className="rounded-[var(--tt-radius-lg)] border border-emerald-500/25 bg-emerald-500/5 px-4 py-3">
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-emerald-400/90">
          Local inference
        </div>
        {model ? (
          <div className="font-mono text-[10px] text-[var(--tt-fg-dim)] truncate max-w-[50%]" title={model}>
            {model}
          </div>
        ) : null}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
        {items.map((it) => (
          <div key={it.label} className="min-w-0">
            <div className="flex items-center gap-1 text-[10px] text-[var(--tt-fg-dim)] uppercase tracking-wider">
              {it.icon}
              {it.label}
            </div>
            <div className="text-[13px] font-semibold tabular text-[var(--tt-fg)] truncate">
              {it.value}
            </div>
            <div className="text-[10px] text-[var(--tt-fg-faint)] truncate" title={it.hint}>
              {it.hint}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
