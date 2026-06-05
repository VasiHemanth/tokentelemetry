"use client";

import { useEffect, useState } from "react";
import { Sparkles, X } from "lucide-react";
import { Button } from "@/components/ui";
import { BackendPicker } from "./BackendPicker";
import {
  getSummarizerConfig,
  getAvailableBackends,
  putSummarizerConfig,
  isConfigUnset,
  ONBOARDING_FLAG,
  DEFAULT_OPENAI_COMPAT,
  type SummarizerBackend,
  type OpenAICompatConfig,
} from "@/lib/summarizer";

// Backends that carry a per-backend model selection.
const MODEL_BACKENDS = new Set(["ollama", "codex", "openai_compat"]);

/**
 * First-run onboarding. On app load it reads /config/summarizer; if the config
 * has never been set (enabled=false && backend=null) AND the user hasn't already
 * dismissed it (localStorage flag), it offers a one-time AI-summaries opt-in.
 */
export default function OnboardingModal() {
  const [open, setOpen] = useState(false);
  const [backends, setBackends] = useState<SummarizerBackend[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  // Only meaningful when selected === "ollama".
  const [model, setModel] = useState<string | null>(null);
  // Only meaningful when selected === "openai_compat".
  const [openaiCompat, setOpenaiCompat] = useState<OpenAICompatConfig>(DEFAULT_OPENAI_COMPAT);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (typeof window !== "undefined" && localStorage.getItem(ONBOARDING_FLAG)) return;

    (async () => {
      try {
        const cfg = await getSummarizerConfig();
        if (cancelled || !isConfigUnset(cfg)) return;
        const list = await getAvailableBackends();
        if (cancelled) return;
        setBackends(list);
        setSelected(list[0]?.name ?? null);
        setOpen(true);
      } catch {
        // Backend unreachable — stay silent, don't block the app.
      }
    })();

    return () => { cancelled = true; };
  }, []);

  const dismiss = () => {
    localStorage.setItem(ONBOARDING_FLAG, "1");
    setOpen(false);
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await putSummarizerConfig({
        enabled: selected !== null,
        backend: selected,
        model: selected && MODEL_BACKENDS.has(selected) ? model : null,
        ...(selected === "openai_compat" ? { openai_compat: openaiCompat } : {}),
      });
      dismiss();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save preference.");
    } finally {
      setSaving(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center p-4">
      <div
        aria-hidden
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={dismiss}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="tt-onboarding-title"
        className="relative w-full max-w-md rounded-[var(--tt-radius-lg)] border border-[var(--tt-border-strong)] bg-[var(--tt-panel)] shadow-[0_24px_60px_-20px_rgba(0,0,0,0.6)]"
      >
        <button
          onClick={dismiss}
          aria-label="Dismiss"
          className="absolute right-3 top-3 h-7 w-7 grid place-items-center rounded-md text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)] hover:tt-tint-1 transition-colors"
        >
          <X size={15} />
        </button>

        <div className="p-6 space-y-5">
          <div className="flex items-start gap-3">
            <div className="h-10 w-10 grid place-items-center rounded-[var(--tt-radius)] bg-[color:var(--tt-brand-glow)] text-[var(--tt-brand)]">
              <Sparkles size={18} />
            </div>
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-[var(--tt-fg-dim)] mb-1">
                One-time setup
              </div>
              <h2 id="tt-onboarding-title" className="text-[18px] font-semibold tracking-tight text-[var(--tt-fg)]">
                Enable AI trace summaries?
              </h2>
            </div>
          </div>

          <p className="text-[13px] leading-relaxed text-[var(--tt-fg-muted)]">
            TokenTelemetry can turn each session trace into a short narrative — intent &amp; outcome,
            key actions, efficiency, and notable moments — using a coding agent you already have
            installed. The deterministic brief always works without this.
          </p>

          <BackendPicker
            backends={backends}
            selected={selected}
            onSelect={(name) => {
              setSelected(name);
              if (!name || !MODEL_BACKENDS.has(name)) setModel(null);
            }}
            model={model}
            onModelChange={setModel}
            openaiCompat={openaiCompat}
            onOpenAICompatChange={setOpenaiCompat}
          />

          {error && (
            <p className="text-[12px] text-[var(--tt-danger-fg)]">{error}</p>
          )}

          <div className="flex items-center justify-end gap-2 pt-1">
            <Button variant="ghost" onClick={dismiss} disabled={saving}>
              Maybe later
            </Button>
            <Button variant="primary" onClick={save} disabled={saving}>
              {saving ? "Saving…" : selected === null ? "Continue without AI" : "Enable summaries"}
            </Button>
          </div>
          <p className="text-center text-[10px] text-[var(--tt-fg-faint)]">
            You can change this anytime in Settings.
          </p>
        </div>
      </div>
    </div>
  );
}
