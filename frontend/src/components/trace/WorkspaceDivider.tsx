"use client";

import { useEffect, useRef, type RefObject } from "react";
import { GripVertical } from "lucide-react";
import { clampWorkspaceSplit } from "@/lib/traceTree/workspace";

export default function WorkspaceDivider({ value, onChange, container }: { value: number; onChange: (value: number) => void; container: RefObject<HTMLDivElement | null> }) {
  const dragging = useRef(false);
  useEffect(() => {
    const element = container.current;
    if (!element) return;
    const observer = new ResizeObserver(() => onChange(clampWorkspaceSplit(value, element.clientWidth)));
    observer.observe(element);
    return () => observer.disconnect();
  }, [container, value, onChange]);
  const change = (next: number) => onChange(clampWorkspaceSplit(next, container.current?.clientWidth ?? 0));
  return <div role="separator" aria-label="Resize execution and conversation panels" aria-orientation="vertical" aria-valuemin={Math.round(24_000 / (container.current?.clientWidth || 1000))} aria-valuemax={Math.round(100 * (1 - 332 / (container.current?.clientWidth || 1000)))} aria-valuenow={Math.round(value)} aria-valuetext={`${Math.round(value)} percent execution panel`} tabIndex={0}
    className="group hidden touch-none select-none items-center justify-center rounded text-[var(--tt-fg-dim)] outline-none hover:bg-[var(--tt-brand-glow)] hover:text-[var(--tt-brand)] focus-visible:bg-[var(--tt-brand-glow)] focus-visible:ring-1 focus-visible:ring-[var(--tt-border-focus)] @min-[800px]:flex cursor-col-resize"
    title="Drag to resize · arrow keys to adjust · double-click to reset"
    onPointerDown={e => { if (e.button !== 0) return; dragging.current = true; e.currentTarget.setPointerCapture(e.pointerId); e.preventDefault(); }}
    onPointerMove={e => { if (!dragging.current) return; const rect = container.current?.getBoundingClientRect(); if (rect) change(100 * (e.clientX - rect.left) / rect.width); }}
    onPointerUp={e => { dragging.current = false; if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId); }}
    onLostPointerCapture={() => { dragging.current = false; }} onPointerCancel={() => { dragging.current = false; }}
    onDoubleClick={() => change(34)} onKeyDown={e => { if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return; e.preventDefault(); change(e.key === "Home" ? 0 : e.key === "End" ? 100 : value + (e.key === "ArrowRight" ? 2 : -2)); }}>
    <GripVertical size={12} aria-hidden="true" />
  </div>;
}
