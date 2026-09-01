"use client";

import { useEffect, useState } from "react";
import { Settings2, Sparkles, Check, Loader2, RefreshCw, CreditCard, Bot, Database, Shield, Plug, Keyboard } from "lucide-react";
import { cn } from "@/lib/cn";
import { PageHeader, Section, Card, CardHeader, CardTitle, Button, Badge, Skeleton } from "@/components/ui";
import { BackendPicker } from "@/components/summarizer/BackendPicker";
import { BillingSettings } from "@/components/settings/BillingSettings";
import { AgentFeatureFlags } from "@/components/settings/AgentFeatureFlags";
import { RetentionSettings } from "@/components/settings/RetentionSettings";
import UsagePrivacySettings from "@/components/settings/UsagePrivacySettings";
import { ShortcutSettings } from "@/components/settings/ShortcutSettings";
import { ThemeSetting } from "@/components/settings/ThemeSetting";
import { SettingsNav } from "@/components/settings/SettingsNav";
import { SETTINGS_CATEGORIES, categoryAnchor } from "@/components/settings/categories";
import { ConnectDevice } from "@/components/ConnectDevice";
import {
  getSummarizerConfig, getAvailableBackends, putSummarizerConfig,
  DEFAULT_OPENAI_COMPAT,
  type SummarizerConfig, type SummarizerBackend, type OpenAICompatConfig,
} from "@/lib/summarizer";
import { getUpdateCheck, setUpdateCheck, type UpdateCheckState } from "@/lib/version";

// Backends that carry a per-backend model selection.
const MODEL_BACKENDS = new Set(["ollama", "codex", "openai_compat"]);

const CATEGORY_ICONS: Record<string, typeof Settings2> = {
  general: Settings2,
  agents: Bot,
  billing: CreditCard,
  data: Database,
  privacy: Shield,
  access: Plug,
  shortcuts: Keyboard,
};

function DashboardPreferencesToggle() {
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    // Preserve hydration by reading browser-only storage after mount.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setEnabled(localStorage.getItem("tt-show-local-dash") === "true");
  }, []);

  const toggle = () => {
    const next = !enabled;
    setEnabled(next);
    localStorage.setItem("tt-show-local-dash", next.toString());
    window.dispatchEvent(new Event("storage"));
  };

  return (
    <button
      onClick={toggle}
      role="switch"
      aria-checked={enabled}
      className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border transition-colors mt-0.5 border-[var(--tt-border)] cursor-pointer ${enabled ? "tt-tint-1" : ""}`}
    >
      <span className={`absolute h-3.5 w-3.5 rounded-full transition-transform ${enabled ? "translate-x-[18px] bg-[var(--tt-brand)]" : "translate-x-0.5 bg-[var(--tt-fg-muted)]"}`} />
    </button>
  );
}

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
  const [active, setActive] = useState<string | null>(null);

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

  // Highlight the category currently in view (Google-Cloud-style sidebar).
  useEffect(() => {
    const sections = SETTINGS_CATEGORIES.map((c) => document.getElementById(categoryAnchor(c.id)));
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting);
        if (visible.length > 0) {
          const id = visible[visible.length - 1].target.getAttribute("data-cat");
          if (id) setActive(id);
        }
      },
      { rootMargin: "-40% 0px -55% 0px", threshold: 0 },
    );
    for (const el of sections) {
      if (!el) continue;
      el.setAttribute("data-cat", el.id.replace("cat-", ""));
      observer.observe(el);
    }
    return () => observer.disconnect();
  }, []);

  // Deep-link from the `?` shortcut (`/settings?section=shortcuts`).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("section") === "shortcuts") {
      document.getElementById(categoryAnchor("shortcuts"))?.scrollIntoView({ block: "start" });
    }
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

  const cat = (id: string, children: React.ReactNode) => {
    const Icon = CATEGORY_ICONS[id] ?? Settings2;
    return (
      <section id={categoryAnchor(id)} className="scroll-mt-24">
        <div className="mb-5 flex items-center gap-2 border-b border-[var(--tt-border)] pb-2">
          <Icon size={15} className="text-[var(--tt-fg-muted)]" />
          <h2 className="text-[13px] font-semibold uppercase tracking-[0.18em] text-[var(--tt-fg-muted)]">
            {SETTINGS_CATEGORIES.find((c) => c.id === id)?.label}
          </h2>
        </div>
        <div className="space-y-6">{children}</div>
      </section>
    );
  };

  return (
    <div className="px-6 py-8 lg:grid lg:grid-cols-[230px_minmax(0,1fr)] lg:gap-10 mx-auto max-w-6xl">
      <aside className="mb-8 lg:mb-0 lg:sticky lg:top-6 lg:self-start lg:h-fit">
        <SettingsNav active={active} />
      </aside>

      <div className="min-w-0 max-w-[860px] space-y-12">
        <PageHeader
          eyebrow="Configuration"
          title="Settings"
          description="Configure summaries, billing, retention, privacy and shortcuts."
          icon={<Settings2 size={20} strokeWidth={2.25} />}
        />

        {cat("general", (
          <>
            <Section title="Theme" description="Light, dark, or follow your system preference.">
              <Card>
                <div className="p-5">
                  <ThemeSetting />
                </div>
              </Card>
            </Section>
            <Section title="Dashboard preferences" description="Customize what you see on the main dashboard.">
              <Card>
                <div className="flex items-start justify-between gap-4 p-5">
                  <div>
                    <CardTitle className="mb-1 text-[13px]">Show local power & energy on dashboard</CardTitle>
                    <p className="text-[12px] text-[var(--tt-fg-dim)] max-w-[560px]">
                      By default, local power insights are only shown on the Local Models page. Turn this on to also display them on the main dashboard.
                    </p>
                  </div>
                  <DashboardPreferencesToggle />
                </div>
              </Card>
            </Section>
          </>
        ))}

        {cat("agents", (
          <>
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
              title="Agent feature flags"
              description="Experimental and preview features each agent has enabled in its own local config — read-only. There's no shared 'experimental mode' across harnesses, so this covers the agents that expose it on disk (Copilot, Codex, Claude Code); agents that gate features server-side or in opaque stores aren't listed."
            >
              <AgentFeatureFlags />
            </Section>
          </>
        ))}

        {cat("billing", (
          <Section
            title="Billing & cost"
            description="How you pay for each agent. The cost figure is always the API-list-price equivalent — this only changes how it's framed (a real bill for pay-per-token API plans, an equivalent for flat subscriptions). Auto-detected where possible; override any agent here."
          >
            <BillingSettings />
          </Section>
        ))}

        {cat("data", (
          <Section
            title="Agent history & retention"
            description="Keep analytics history alive after agents prune their own transcripts. Core session stats are always retained; opt in per agent to also archive full transcripts, and reclaim space anytime without losing your history."
          >
            <RetentionSettings />
          </Section>
        ))}

        {cat("privacy", (
          <>
            <div id="usage-privacy" className="scroll-mt-20">
              <Section
                title="Anonymous usage stats"
                description="Content-free product telemetry. Read exactly what would be sent, or turn it off entirely."
              >
                <UsagePrivacySettings />
              </Section>
            </div>
            <Section
              title="Update checks"
              description="Check GitHub for new releases, about once an hour."
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
          </>
        ))}

        {cat("access", (
          <>
            {/* Only renders when remote access is enabled; showWhenOff keeps the
                category from appearing empty on a default loopback-only run. */}
            <ConnectDevice showWhenOff />
          </>
        ))}

        {cat("shortcuts", (
          <Section
            title="Keyboard shortcuts"
            description="Navigation shortcuts for the dashboard, rebindable and stored on this machine."
          >
            <ShortcutSettings />
          </Section>
        ))}
      </div>
    </div>
  );
}
