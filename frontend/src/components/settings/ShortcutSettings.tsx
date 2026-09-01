"use client";

import { useEffect, useState } from "react";
import { Pencil, X, RotateCcw } from "lucide-react";
import { Badge } from "@/components/ui";
import {
  SHORTCUTS, loadBindings, saveBindings, defaultBindings, shortcutKey, chordTokens,
  type ShortcutId,
} from "@/lib/shortcuts";

function Chord({ tokens }: { tokens: string[] }) {
  return (
    <span className="inline-flex items-center gap-1">
      {tokens.map((token, i) => (
        <kbd
          key={i}
          className="inline-flex h-6 min-w-6 items-center justify-center rounded-[var(--tt-radius-sm)] border border-[var(--tt-border)] bg-[var(--tt-sunken)] px-1.5 font-mono text-[11px] text-[var(--tt-fg)]"
        >
          {token}
        </kbd>
      ))}
    </span>
  );
}

export function ShortcutSettings() {
  const [bindings, setBindings] = useState<Record<ShortcutId, string>>(() => loadBindings());
  const [recording, setRecording] = useState<ShortcutId | null>(null);

  const commit = (next: Record<ShortcutId, string>) => {
    setBindings(next);
    saveBindings(next);
    window.dispatchEvent(new Event("tt-shortcuts-changed"));
  };

  // While recording, capture the next shortcut key (a bare letter / `?`).
  useEffect(() => {
    if (!recording) return;
    const onKey = (e: KeyboardEvent) => {
      const key = shortcutKey(e);
      if (!key || key === "g") return; // ignore modifiers and the leader key
      e.preventDefault();
      e.stopPropagation();
      commit({ ...bindings, [recording]: key });
      setRecording(null);
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [recording, bindings]);

  return (
    <div className="space-y-4">
      <p className="text-[12px] text-[var(--tt-fg-dim)] max-w-[560px]">
        Navigation uses a leader key: press <Badge variant="neutral" size="sm">G</Badge> then a letter
        (e.g. <Badge variant="neutral" size="sm">G</Badge> <Badge variant="neutral" size="sm">A</Badge> for
        Analytics). Press <Badge variant="neutral" size="sm">?</Badge> anywhere to open this reference.
        Click the pencil beside a shortcut to re-record it.
      </p>

      <div className="divide-y divide-[var(--tt-border)] rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] overflow-hidden">
        {SHORTCUTS.map((s) => {
          const key = bindings[s.id] ?? s.defaultKey;
          const isRecording = recording === s.id;
          return (
            <div key={s.id} className="flex items-center justify-between gap-4 px-4 py-3">
              <div className="min-w-0">
                <p className="text-[13px] text-[var(--tt-fg)] font-medium">{s.label}</p>
                <p className="text-[12px] text-[var(--tt-fg-dim)]">{s.description}</p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {isRecording ? (
                  <span className="text-[11px] uppercase tracking-[0.14em] text-[var(--tt-brand)] animate-pulse">
                    Press a key…
                  </span>
                ) : (
                  <Chord tokens={chordTokens(s, key)} />
                )}
                <button
                  onClick={() => setRecording(isRecording ? null : s.id)}
                  aria-label={isRecording ? "Cancel recording" : `Change shortcut for ${s.label}`}
                  title={isRecording ? "Cancel" : "Change"}
                  className="grid h-7 w-7 place-items-center rounded-[var(--tt-radius-sm)] text-[var(--tt-fg-muted)] hover:bg-[var(--tt-tint)] hover:text-[var(--tt-fg)]"
                >
                  {isRecording ? <X size={14} /> : <Pencil size={14} />}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <button
        onClick={() => commit(defaultBindings())}
        className="inline-flex items-center gap-1.5 rounded-[var(--tt-radius)] border border-[var(--tt-border)] px-3 py-1.5 text-[12px] text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] hover:border-[var(--tt-border-strong)] transition-colors"
      >
        <RotateCcw size={13} /> Reset to defaults
      </button>
    </div>
  );
}
