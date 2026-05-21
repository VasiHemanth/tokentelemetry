"use client";

import { useEffect, useRef, useState } from "react";
import { MessageSquarePlus, X } from "lucide-react";
import { cn } from "@/lib/cn";
import FeedbackMenu from "./FeedbackMenu";

export default function FeedbackFloatingButton() {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={wrapRef} className="fixed bottom-6 right-6 z-[120] flex flex-col items-end gap-2">
      {open && <FeedbackMenu align="right" onSelect={() => setOpen(false)} />}
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? "Close feedback menu" : "Send feedback"}
        className={cn(
          "h-11 w-11 rounded-full grid place-items-center shadow-lg transition-all",
          "bg-gradient-to-br from-[var(--tt-brand)] to-[var(--tt-brand-deep)] text-white",
          "hover:scale-105 hover:shadow-[0_0_22px_-4px_var(--tt-brand-glow)]",
        )}
      >
        {open ? <X size={18} strokeWidth={2.5} /> : <MessageSquarePlus size={18} strokeWidth={2.25} />}
      </button>
    </div>
  );
}
