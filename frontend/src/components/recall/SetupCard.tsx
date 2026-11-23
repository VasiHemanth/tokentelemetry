"use client";

import { useEffect, useRef, useState } from "react";
import { Download, KeyRound, Loader2, TriangleAlert, Check } from "lucide-react";
import { Button } from "@/components/ui";
import { cn } from "@/lib/cn";
import {
  putRecallSettings, streamModelPull,
  type ApiFormat, type RecallCapability, type RecallSettings,
} from "@/lib/recall";
import { CapabilityNote } from "./CapabilityNote";

const FORMAT_DEFAULTS: Record<ApiFormat, { label: string; endpoint: string; model: string; images: boolean }> = {
  openai: {
    label: "OpenAI-compatible", endpoint: "https://api.openai.com/v1/embeddings",
    model: "text-embedding-3-small", images: false,
  },
  gemini: {
    label: "Gemini", endpoint: "https://generativelanguage.googleapis.com/v1beta",
    model: "gemini-embedding-2", images: true,
  },
  voyage: {
    label: "Voyage", endpoint: "https://api.voyageai.com/v1/multimodalembeddings",
    model: "voyage-multimodal-3.5", images: true,
  },
};
const DIMS = [128, 256, 512, 768] as const;
const LOCAL_MODEL = "embeddinggemma-2:740m";

type Tab = "local" | "api";

function endpointProblem(url: string): string | null {
  let u: URL;
  try { u = new URL(url); } catch { return "Enter a full URL."; }
  if (u.protocol === "https:") return null;
  const loopback = ["localhost", "127.0.0.1", "[::1]"].includes(u.hostname);
  if (u.protocol === "http:" && loopback) return null;
  return "The endpoint must use https, or http on this machine.";
}

const fieldCls =
  "h-9 w-full px-3 rounded-[var(--tt-radius)] bg-[var(--tt-panel)] border border-[var(--tt-border)] text-[13px] text-[var(--tt-fg)] placeholder:text-[var(--tt-fg-faint)] hover:border-[var(--tt-border-strong)] focus:outline-none focus:ring-1 focus:ring-[color:var(--tt-brand)]/30";

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <label className="block space-y-1">
      <span className="text-[11px] font-medium text-[var(--tt-fg-muted)]">{label}</span>
      {children}
      {hint && <span className="block text-[11px] text-[var(--tt-fg-dim)]">{hint}</span>}
    </label>
  );
}

export function SetupCard({ settings, capability, capabilityLoading, onChanged, onRecheck }: {
  settings: RecallSettings | null;
  capability: RecallCapability | null;
  capabilityLoading: boolean;
  /** Called with fresh settings after a save or a finished model download. */
  onChanged: (s: RecallSettings | null) => void;
  onRecheck: (sampleProject?: boolean) => void;
}) {
  const sem = settings?.semantic;
  const [tab, setTab] = useState<Tab>("local");
  const seeded = useRef(false);
  const [format, setFormat] = useState<ApiFormat>("openai");
  const [endpoint, setEndpoint] = useState(FORMAT_DEFAULTS.openai.endpoint);
  const [model, setModel] = useState(FORMAT_DEFAULTS.openai.model);
  const [dims, setDims] = useState<number>(256);
  const [images, setImages] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const [pull, setPull] = useState<{ running: boolean; status: string; percent: number | null; error: string | null; fix: string | null }>(
    { running: false, status: "", percent: null, error: null, fix: null },
  );
  const pullCtl = useRef<AbortController | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; pullCtl.current?.abort(); };
  }, []);

  // Seed the form once from saved settings. The key is never part of settings, so it stays blank.
  useEffect(() => {
    if (!sem || seeded.current) return;
    seeded.current = true;
    /* eslint-disable react-hooks/set-state-in-effect */
    if (sem.provider === "api") setTab("api");
    if (sem.api) {
      setFormat(sem.api.format);
      setEndpoint(sem.api.endpoint);
      setModel(sem.api.model);
    }
    if (sem.dims) setDims(sem.dims);
    if (sem.images != null && sem.provider === "api") setImages(sem.images);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [sem]);

  const keySet = !!(sem?.api?.api_key_set ?? sem?.api_key_set);
  const installed = capability?.ollama?.model_installed ?? settings?.ollama.model_installed ?? false;
  const reachable = capability?.ollama?.reachable ?? settings?.ollama.reachable ?? false;

  const changeFormat = (f: ApiFormat) => {
    setFormat(f);
    setEndpoint(FORMAT_DEFAULTS[f].endpoint);
    setModel(FORMAT_DEFAULTS[f].model);
    setImages(false);
  };

  const runPull = async () => {
    pullCtl.current?.abort();
    const ctl = new AbortController();
    pullCtl.current = ctl;
    setPull({ running: true, status: "Starting", percent: null, error: null, fix: null });
    let ok = false;
    try {
      for await (const ev of streamModelPull(ctl.signal)) {
        if (!alive.current) return;
        if (ev.type === "error") {
          setPull({ running: false, status: "", percent: null, error: ev.message ?? "The download failed.", fix: ev.fix ?? null });
          return;
        }
        if (ev.status === "success") ok = true;
        const pct = typeof ev.percent === "number"
          ? ev.percent
          : ev.total ? (100 * (ev.completed ?? 0)) / ev.total : null;
        setPull((p) => ({ ...p, status: ev.status, percent: pct ?? p.percent }));
      }
      if (!alive.current) return;
      if (!ok) {
        setPull({ running: false, status: "", percent: null, error: "The download stopped before it finished.", fix: "Try again; partial layers are kept." });
        return;
      }
      setPull({ running: false, status: "success", percent: 100, error: null, fix: null });
      onRecheck();
    } catch (e) {
      if (ctl.signal.aborted || !alive.current) return;
      setPull({ running: false, status: "", percent: null, error: e instanceof Error ? e.message : String(e), fix: null });
    }
  };

  const save = async (provider: Tab) => {
    setSaving(true); setError(null); setSaved(false);
    try {
      const next = provider === "local"
        ? await putRecallSettings({ enabled: true, provider: "ollama", dims, images: true })
        : await putRecallSettings({
          enabled: true, provider: "api", dims, images,
          api: { format, endpoint, model, ...(apiKey ? { api_key: apiKey } : {}) },
        });
      if (!alive.current) return;
      setApiKey("");
      setSaved(true);
      onChanged(next);
    } catch (e) {
      if (alive.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (alive.current) setSaving(false);
    }
  };

  const epProblem = tab === "api" ? endpointProblem(endpoint) : null;
  const loopback = tab === "api" && !epProblem && ["localhost", "127.0.0.1", "[::1]"].includes(new URL(endpoint.trim()).hostname);
  const apiReady = !epProblem && model.trim() !== "" && (loopback || keySet || apiKey.trim() !== "");
  const canImages = FORMAT_DEFAULTS[format].images;
  const enabledNow = !!sem?.enabled;

  return (
    <div className="rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] p-4 space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-[13px] font-semibold text-[var(--tt-fg)]">Set up semantic search</h3>
        <div role="tablist" aria-label="Embedding provider" className="inline-flex rounded-[var(--tt-radius)] border border-[var(--tt-border)] p-0.5">
          {([["local", "Local (Ollama)"], ["api", "API"]] as const).map(([id, label]) => (
            <button
              key={id} role="tab" type="button" aria-selected={tab === id} onClick={() => setTab(id)}
              className={cn(
                "h-7 px-3 rounded-[calc(var(--tt-radius)-2px)] text-[12px] font-medium transition-colors",
                tab === id ? "tt-tint-2 text-[var(--tt-fg)]" : "text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)]",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {tab === "local" ? (
        <div className="space-y-3">
          <p className="text-[12px] text-[var(--tt-fg-muted)]">
            Runs on this machine through Ollama with <span className="font-mono">{LOCAL_MODEL}</span> (text and images).
            Nothing leaves your computer.
          </p>
          {capabilityLoading && !capability ? (
            <div className="h-10 rounded-[var(--tt-radius)] tt-tint-1 animate-pulse" aria-busy />
          ) : (
            <CapabilityNote cap={capability} />
          )}
          <div className="flex flex-wrap items-center gap-3">
            {!installed && (
              <Button
                variant="primary" size="sm"
                disabled={pull.running || !reachable || capability?.status === "blocked"}
                onClick={() => void runPull()}
                title={!reachable ? "Start Ollama first" : undefined}
              >
                {pull.running ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
                Download model (1.3 GB)
              </Button>
            )}
            {installed && (
              <span className="inline-flex items-center gap-1.5 text-[12px] text-[var(--tt-success-fg)]">
                <Check size={13} /> Model installed
              </span>
            )}
            <Button size="sm" variant={installed ? "primary" : "secondary"} disabled={saving || !installed} onClick={() => void save("local")}>
              {enabledNow && sem?.provider !== "api" ? "Save" : "Use local model"}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => onRecheck(true)} disabled={capabilityLoading}
              title="Time up to 32 redacted project chunks on this machine">Check indexing speed</Button>
          </div>
          {(pull.running || pull.status === "success") && (
            <div className="space-y-1" aria-live="polite">
              <div className="h-1.5 rounded-full tt-tint-2 overflow-hidden">
                <div
                  className={cn("h-full bg-[var(--tt-brand)] transition-all", pull.percent == null && "animate-pulse w-full")}
                  style={pull.percent != null ? { width: `${Math.min(100, Math.max(0, pull.percent))}%` } : undefined}
                />
              </div>
              <p className="text-[11px] text-[var(--tt-fg-dim)] tabular">
                {pull.status}{pull.percent != null ? ` · ${Math.round(pull.percent)}%` : ""}
              </p>
            </div>
          )}
          {pull.error && (
            <p className="text-[12px] text-[var(--tt-danger-fg)]">
              {pull.error}{pull.fix ? ` ${pull.fix}` : ""}
            </p>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-start gap-2.5 rounded-[var(--tt-radius)] border border-[var(--tt-warn-bd)] bg-[var(--tt-warn-bg)] px-3 py-2.5 text-[12px] text-[var(--tt-warn-fg)]">
            <TriangleAlert size={14} className="mt-0.5 shrink-0" />
            <p>
              The text of your sessions and files, after secret redaction, is sent to this provider to be embedded.
              It leaves this machine.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Format">
              <select value={format} onChange={(e) => changeFormat(e.target.value as ApiFormat)} className={fieldCls}>
                {(Object.keys(FORMAT_DEFAULTS) as ApiFormat[]).map((f) => (
                  <option key={f} value={f}>{FORMAT_DEFAULTS[f].label}</option>
                ))}
              </select>
            </Field>
            <Field label="Model">
              <input value={model} onChange={(e) => setModel(e.target.value)} className={cn(fieldCls, "font-mono")} spellCheck={false} />
            </Field>
            <div className="sm:col-span-2">
              <Field label="Endpoint" hint={epProblem ?? undefined}>
                <input value={endpoint} onChange={(e) => setEndpoint(e.target.value)} className={cn(fieldCls, "font-mono")} spellCheck={false} />
              </Field>
            </div>
            <Field
              label="API key"
              hint={keySet ? "A key is saved. Leave blank to keep it, or type a new one to replace it." : loopback ? "Optional for a loopback endpoint." : "Stored on this machine, never shown again."}
            >
              <div className="relative">
                <KeyRound size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--tt-fg-dim)] pointer-events-none" />
                <input
                  type="password" autoComplete="off" value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={keySet ? "key saved" : "paste key"}
                  className={cn(fieldCls, "pl-9")}
                />
              </div>
              {keySet && (
                <span className="inline-flex items-center gap-1 text-[11px] text-[var(--tt-success-fg)]">
                  <Check size={11} /> key saved
                </span>
              )}
            </Field>
            <Field label="Dimensions" hint="Smaller is faster and lighter. 256 suits most projects.">
              <select value={dims} onChange={(e) => setDims(Number(e.target.value))} className={fieldCls}>
                {DIMS.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </Field>
          </div>
          <label className={cn("flex items-start gap-2 text-[12px]", canImages ? "text-[var(--tt-fg-muted)] cursor-pointer" : "text-[var(--tt-fg-faint)]")}>
            <input
              type="checkbox" className="mt-0.5 accent-[var(--tt-brand)]"
              checked={images && canImages} disabled={!canImages}
              onChange={(e) => setImages(e.target.checked)}
            />
            <span>
              Also embed images. Text and images leave this machine; images cannot be redacted.
              {!canImages && " This format does not accept images."}
            </span>
          </label>
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="primary" size="sm" disabled={saving || !apiReady} onClick={() => void save("api")}>
              {saving && <Loader2 size={13} className="animate-spin" />} Save API settings
            </Button>
            <span className="text-[11px] text-[var(--tt-fg-dim)]">
              Changing provider, model or dimensions marks existing indexes for a full re-index.
            </span>
          </div>
        </div>
      )}

      {saved && <p className="text-[12px] text-[var(--tt-success-fg)]" role="status">Saved.</p>}
      {error && <p className="text-[12px] text-[var(--tt-danger-fg)]">{error}</p>}
    </div>
  );
}
