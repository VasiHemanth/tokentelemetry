"use client";

import { useEffect, useState } from "react";
import { Settings2, Sparkles, Check, Loader2, RefreshCw } from "lucide-react";
import { cn } from "@/lib/cn";
import { PageHeader, Section, Card, CardHeader, CardTitle, Button, Badge, Skeleton } from "@/components/ui";
import { BackendPicker } from "@/components/summarizer/BackendPicker";
import { BillingSettings } from "@/components/settings/BillingSettings";
import {
  getSummarizerConfig, getAvailableBackends, putSummarizerConfig,
  DEFAULT_OPENAI_COMPAT,
  type SummarizerConfig, type SummarizerBackend, type OpenAICompatConfig,
} from "@/lib/summarizer";
import { getUpdateCheck, setUpdateCheck, type UpdateCheckState } from "@/lib/version";

// Backends that carry a per-backend model selection.
const MODEL_BACKENDS = new Set(["ollama", "codex", "openai_compat"]);

export default function SettingsPage() {
  const [config, setConfig] = useState<SummarizerConfig | null>(null);
  const [backends, setBackends] = useState<SummarizerBackend[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  // Only meaningful when selected === "ollama"; null = "auto-pick first model".
  const [model, setModel] = useState<string | null>(null);
  // Only meaningful when selected === "openai_compat".
  const [openaiCompat, setOpenaiCompat] = useState<OpenAICompatConfig>(DEFAULT_OPENAI_COMPAT);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Update-check preference (independent of the summarizer config above).
  const [updateCheck, setUpdateCheckState] = useState<UpdateCheckState | null>(null);
  const [togglingUpdate, setTogglingUpdate] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getUpdateCheck()
      .then((s) => { if (!cancelled) setUpdateCheckState(s); })
      .catch(() => { /* non-fatal: section just stays in its loading state */ });
    return () => { cancelled = true; };
  }, []);

  const toggleUpdateCheck = async () => {
    if (!updateCheck || updateCheck.env_forced_off) return;
    setTogglingUpdate(true);
    const next = !updateCheck.enabled;
    try {
      setUpdateCheckState(await setUpdateCheck(next));
    } catch {
      /* leave previous state; the toggle simply won't flip */
    } finally {
      setTogglingUpdate(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    Promise.all([getSummarizerConfig(), getAvailableBackends()])
      .then(([cfg, list]) => {
        if (cancelled) return;
        setConfig(cfg);
        setBackends(list);
        setSelected(cfg.enabled ? cfg.backend : null);
        setModel(cfg.model);
        if (cfg.openai_compat) setOpenaiCompat(cfg.openai_compat);
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Failed to load settings.");
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const save = async () => {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const next = await putSummarizerConfig({
        enabled: selected !== null,
        backend: selected,
        // Model field is meaningful for backends that support per-backend
        // model selection (ollama + codex + openai_compat); null otherwise.
        model: selected && MODEL_BACKENDS.has(selected) ? model : null,
        // Persist endpoint/tuning whenever openai_compat is the active backend.
        ...(selected === "openai_compat" ? { openai_compat: openaiCompat } : {}),
      });
      setConfig(next);
      setSelected(next.enabled ? next.backend : null);
      setModel(next.model);
      if (next.openai_compat) setOpenaiCompat(next.openai_compat);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save settings.");
    } finally {
      setSaving(false);
    }
  };

  const dirty = config
    ? (selected !== (config.enabled ? config.backend : null))
        || (!!selected && MODEL_BACKENDS.has(selected) && model !== config.model)
        || (selected === "openai_compat"
            && JSON.stringify(openaiCompat) !== JSON.stringify(config.openai_compat ?? DEFAULT_OPENAI_COMPAT))
    : false;

  return (
    <div className="px-8 py-8 max-w-[900px] mx-auto space-y-10 pb-20">
      <PageHeader
        eyebrow="Configuration"
        title="Settings"
        description="Configure how TokenTelemetry summarizes your session traces."
        icon={<Settings2 size={20} strokeWidth={2.25} />}
      />

      <Section
        title="AI trace summaries"
        description="Pick a coding agent to generate narrative summaries, or disable AI summaries entirely."
      >
        <Card>
          <CardHeader>
            <CardTitle>
              <Sparkles size={14} className="text-[var(--tt-brand)]" />
              Summarizer backend
            </CardTitle>
            {config && (
              <Badge variant={config.enabled ? "success" : "neutral"} size="sm">
                {config.enabled ? `Enabled · ${config.backend}` : "Disabled"}
              </Badge>
            )}
          </CardHeader>

          {loading ? (
            <div className="space-y-2">
              <Skeleton className="h-14 w-full" />
              <Skeleton className="h-14 w-full" />
            </div>
          ) : (
            <div className="space-y-4">
              <BackendPicker
                backends={backends}
                selected={selected}
                onSelect={(name) => {
                  setSelected(name);
                  // Drop the model when switching to a backend that doesn't
                  // use one — keeps the dirty-check honest and avoids saving
                  // an irrelevant model name into config.
                  if (!name || !MODEL_BACKENDS.has(name)) setModel(null);
                }}
                model={model}
                onModelChange={setModel}
                openaiCompat={openaiCompat}
                onOpenAICompatChange={setOpenaiCompat}
              />

              {error && <p className="text-[12px] text-[var(--tt-danger-fg)]">{error}</p>}

              <div className="flex items-center justify-end gap-3 pt-1">
                {saved && (
                  <span className="flex items-center gap-1.5 text-[12px] text-[var(--tt-success-fg)]">
                    <Check size={13} /> Saved
                  </span>
                )}
                <Button variant="primary" onClick={save} disabled={saving || !dirty}>
                  {saving ? <><Loader2 size={13} className="animate-spin" /> Saving…</> : "Save changes"}
                </Button>
              </div>
            </div>
          )}
        </Card>
      </Section>

      <Section
        title="Billing & cost"
        description="How you pay for each agent. The cost figure is always the API-list-price equivalent — this only changes how it's framed (a real bill for pay-per-token API plans, an equivalent for flat subscriptions). Auto-detected where possible; override any agent here."
      >
        <BillingSettings />
      </Section>

      <Section
        title="Updates & privacy"
        description="TokenTelemetry never sends your logs, sessions, tokens, or costs anywhere — those stay on your machine. The only outbound network call is this optional update check."
      >
        <Card>
          <CardHeader>
            <CardTitle>
              <RefreshCw size={14} className="text-[var(--tt-brand)]" />
              Check for updates
            </CardTitle>
            {updateCheck && (
              <Badge variant={updateCheck.effective ? "success" : "neutral"} size="sm">
                {updateCheck.env_forced_off ? "Off · env" : updateCheck.enabled ? "On" : "Off"}
              </Badge>
            )}
          </CardHeader>

          {!updateCheck ? (
            <Skeleton className="h-14 w-full" />
          ) : (
            <div className="space-y-4">
              <div className="flex items-start justify-between gap-4">
                <p className="text-[13px] leading-relaxed text-[var(--tt-fg-dim)] max-w-[560px]">
                  When on, the dashboard fetches the latest version and release notes from GitHub
                  (about once an hour) so you know when new features land. This sends no usage data —
                  only a version request, which exposes your IP and app name to GitHub like any web
                  request. {updateCheck.env_forced_off
                    ? "It is currently forced off by the TT_NO_UPDATE_CHECK environment variable."
                    : "You can also disable it with TT_NO_UPDATE_CHECK=1."}
                </p>
                <button
                  onClick={toggleUpdateCheck}
                  role="switch"
                  aria-checked={updateCheck.enabled}
                  aria-label="Toggle automatic update checks"
                  disabled={togglingUpdate || updateCheck.env_forced_off}
                  className={cn(
                    "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border transition-colors mt-0.5",
                    "border-[var(--tt-border)]",
                    updateCheck.enabled ? "tt-tint-1" : "",
                    updateCheck.env_forced_off ? "opacity-50 cursor-not-allowed" : "cursor-pointer",
                  )}
                >
                  <span
                    className={cn(
                      "absolute h-3.5 w-3.5 rounded-full transition-transform",
                      updateCheck.enabled
                        ? "translate-x-[18px] bg-[var(--tt-brand)]"
                        : "translate-x-0.5 bg-[var(--tt-fg-muted)]",
                    )}
                  />
                </button>
              </div>
            </div>
          )}
        </Card>
      </Section>
    </div>
  );
}
