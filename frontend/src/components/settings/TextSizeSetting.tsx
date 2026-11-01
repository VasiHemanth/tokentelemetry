"use client";

import { useId, useState } from "react";
import { Minus, Plus, RotateCcw, Type } from "lucide-react";
import { useTextSize } from "../TextSizeProvider";
import { TEXT_SIZE_DEFAULT, TEXT_SIZE_MAX, TEXT_SIZE_MIN, TEXT_SIZE_STEP } from "@/lib/textSize";

const PRESETS = [
  { label: "Small", percent: 90 },
  { label: "Default", percent: 100 },
  { label: "Large", percent: 115 },
  { label: "Extra large", percent: 130 },
];
const button = "inline-flex min-h-9 items-center justify-center gap-1.5 rounded-md border border-[var(--tt-border)] px-3 py-1.5 text-sm text-[var(--tt-fg-muted)] hover:bg-[var(--tt-raised)] hover:text-[var(--tt-fg)] disabled:cursor-not-allowed disabled:opacity-40";

export function TextSizeSetting() {
  const { percent, setPercent } = useTextSize();
  const [persisted, setPersisted] = useState(true);
  const rangeId = useId();
  const descriptionId = useId();
  const apply = (next: number) => setPersisted(setPercent(next));
  return <div className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-2 text-sm font-medium text-[var(--tt-fg)]"><Type size={17} />Application font size</div>
      <output htmlFor={rangeId} aria-live="polite" className="font-mono text-sm font-medium tabular-nums text-[var(--tt-fg)]">{percent}%</output>
    </div>
    <div className="flex items-center gap-3">
      <button type="button" aria-label="Decrease font size" disabled={percent <= TEXT_SIZE_MIN} onClick={() => apply(percent - TEXT_SIZE_STEP)} className={button}><Minus size={16} /></button>
      <label htmlFor={rangeId} className="sr-only">Font size</label>
      <input id={rangeId} type="range" min={TEXT_SIZE_MIN} max={TEXT_SIZE_MAX} step={TEXT_SIZE_STEP} value={percent} onChange={event => apply(Number(event.target.value))} aria-describedby={descriptionId} aria-valuetext={`${percent} percent`} className="min-w-0 flex-1 cursor-pointer accent-[var(--tt-brand)]" />
      <button type="button" aria-label="Increase font size" disabled={percent >= TEXT_SIZE_MAX} onClick={() => apply(percent + TEXT_SIZE_STEP)} className={button}><Plus size={16} /></button>
    </div>
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Font size presets">
      {PRESETS.map(preset => <button key={preset.percent} type="button" aria-pressed={percent === preset.percent} onClick={() => apply(preset.percent)} className={`${button} ${percent === preset.percent ? "border-[var(--tt-border-focus)] bg-[var(--tt-brand-glow)] text-[var(--tt-brand)]" : ""}`}>{preset.label} <span className="font-mono text-xs">{preset.percent}%</span></button>)}
      <button type="button" onClick={() => apply(TEXT_SIZE_DEFAULT)} className={button}><RotateCcw size={13} />Reset font size</button>
    </div>
    <div aria-label="Font size preview" className="rounded-lg border border-[var(--tt-border)] bg-[var(--tt-canvas)] p-4">
      <div className="text-base font-medium text-[var(--tt-fg)]">A comfortable size for every screen</div>
      <p className="mt-1 text-sm leading-relaxed text-[var(--tt-fg-muted)]">Read conversations, inspect traces, and compare usage across the application.</p>
      <p className="mt-2 font-mono text-xs text-[var(--tt-fg-muted)]">trace.ts · 12,480 tokens · recorded evidence</p>
    </div>
    <p id={descriptionId} className="text-xs leading-relaxed text-[var(--tt-fg-muted)]">Applies across the entire application. Changes take effect immediately and are saved automatically in this browser on this device. Choose a smaller size on your laptop or a larger size on your monitor.</p>
    {!persisted && <p role="status" className="text-xs text-[var(--tt-warn-fg)]">Browser storage is unavailable. This size applies in the current tab until you reload.</p>}
  </div>;
}
