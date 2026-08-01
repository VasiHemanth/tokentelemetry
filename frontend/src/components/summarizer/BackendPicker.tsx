"use client";

import { useEffect, useState } from "react";
import { Check, Ban, Loader2, Plug, AlertCircle } from "lucide-react";
import { getAgent } from "@/lib/agents";
import { cn } from "@/lib/cn";
import {
  listCodexModels, listOllamaModels, testOpenAICompat,
  DEFAULT_OPENAI_COMPAT,
  type CodexModel, type OllamaModel, type SummarizerBackend,
  type OpenAICompatConfig,
} from "@/lib/summarizer";

interface BackendPickerProps {
  backends: SummarizerBackend[];
  /** null == "Skip / no AI summaries" selected */
  selected: string | null;
  onSelect: (backend: string | null) => void;
  /** Whether to render the "no AI summaries" opt-out tile. */
  allowSkip?: boolean;
  /** Currently chosen model (meaningful for Ollama + Codex + openai_compat). */
  model?: string | null;
  /** Notified when the user picks a different model. */
  onModelChange?: (model: string | null) => void;
  /** openai_compat tuning (endpoint + sampling params). */
  openaiCompat?: OpenAICompatConfig;
  /** Notified when any openai_compat field changes. */
  onOpenAICompatChange?: (cfg: OpenAICompatConfig) => void;
}

/**
 * Shared backend selector — reused by the first-run onboarding modal and the
 * settings surface. Tints each option by its agent hex via getAgent().
 *
 * For Ollama and Codex, a sub-dropdown appears so the user can pin a specific
 * model — useful when the default model isn't installed (Ollama) or isn't
 * available on the user's API tier (Codex / no Pro/Plus). Model lists are
 * fetched lazily on first selection of that backend.
 */
export function BackendPicker({
  backends, selected, onSelect, allowSkip = true,
  model = null, onModelChange,
  openaiCompat, onOpenAICompatChange,
}: BackendPickerProps) {
  const [ollamaModels, setOllamaModels] = useState<OllamaModel[] | null>(null);
  const [ollamaErr, setOllamaErr] = useState<string | null>(null);
  const [ollamaLoading, setOllamaLoading] = useState(false);

  const [codexModels, setCodexModels] = useState<CodexModel[] | null>(null);
  const [codexErr, setCodexErr] = useState<string | null>(null);
  const [codexLoading, setCodexLoading] = useState(false);

  // Lazy-load the model list for whichever backend the user picks.
  useEffect(() => {
    if (selected === "ollama" && ollamaModels === null && !ollamaLoading) {
      setOllamaLoading(true);
      listOllamaModels()
        .then(setOllamaModels)
        .catch((e) => setOllamaErr(e instanceof Error ? e.message : String(e)))
        .finally(() => setOllamaLoading(false));
    }
    if (selected === "codex" && codexModels === null && !codexLoading) {
      setCodexLoading(true);
      listCodexModels()
        .then(setCodexModels)
        .catch((e) => setCodexErr(e instanceof Error ? e.message : String(e)))
        .finally(() => setCodexLoading(false));
    }
  }, [selected, ollamaModels, ollamaLoading, codexModels, codexLoading]);

  return (
    <div className="space-y-3">
      <div className="grid gap-2">
        {backends.map((b) => {
          const meta = getAgent(b.name);
          const Icon = meta.icon;
          const active = selected === b.name;
          return (
            <div key={b.name}>
              <button
                type="button"
                onClick={() => onSelect(b.name)}
                className={cn(
                  "group relative w-full flex items-center gap-3 rounded-[var(--tt-radius-lg)] border px-3.5 py-3 text-left transition-colors",
                  active
                    ? "border-[var(--tt-border-strong)] bg-[var(--tt-raised)]"
                    : "border-[var(--tt-border)] bg-[var(--tt-panel)] hover:border-[var(--tt-border-strong)] hover:bg-[var(--tt-sunken)]",
                )}
              >
                <div
                  className="h-8 w-8 shrink-0 grid place-items-center rounded-md"
                  style={{ backgroundColor: `${meta.hex}14`, color: meta.hex }}
                >
                  <Icon size={16} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-[13px] font-semibold text-[var(--tt-fg)] truncate">{b.display_name}</div>
                  <div className="text-[11px] text-[var(--tt-fg-dim)] truncate">
                    {b.name === "openai_compat"
                      ? "POST traces to any OpenAI-compatible server you run."
                      : `Summaries generated locally via ${b.display_name}.`}
                  </div>
                </div>
                {active && (
                  <span
                    className="h-5 w-5 grid place-items-center rounded-full"
                    style={{ backgroundColor: meta.hex, color: "#fff" }}
                  >
                    <Check size={12} strokeWidth={3} />
                  </span>
                )}
              </button>

              {active && b.name === "ollama" && (
                <ModelDropdown
                  label="Model"
                  value={model}
                  onChange={onModelChange}
                  loading={ollamaLoading}
                  error={ollamaErr}
                  empty={ollamaModels !== null && ollamaModels.length === 0}
                  emptyHint={<>No Ollama models installed. Run <code className="font-mono">ollama pull llama3</code> (or similar) first.</>}
                  options={(ollamaModels || []).map((m) => ({
                    value: m.name,
                    label: m.size ? `${m.name} · ${m.size}` : m.name,
                  }))}
                  autoOption="Auto — use first installed"
                  hint={model ? "Local inference is CPU-bound — larger models take several minutes per summary." : undefined}
                />
              )}

              {active && b.name === "codex" && (
                <ModelDropdown
                  label="Model"
                  value={model}
                  onChange={onModelChange}
                  loading={codexLoading}
                  error={codexErr}
                  empty={false}
                  options={(codexModels || []).map((m) => ({
                    value: m.name,
                    label: m.label,
                    hint: m.hint,
                  }))}
                  autoOption="Auto — use Codex default (~/.codex/config.toml)"
                  hint="Pick a cheaper model if you don't have ChatGPT Pro/Plus or hit 'incorrect API key' / quota errors on the default."
                />
              )}

              {active && b.name === "openai_compat" && (
                <OpenAICompatForm
                  model={model}
                  onModelChange={onModelChange}
                  config={openaiCompat ?? DEFAULT_OPENAI_COMPAT}
                  onChange={onOpenAICompatChange}
                />
              )}
            </div>
          );
        })}

        {allowSkip && (
          <button
            type="button"
            onClick={() => onSelect(null)}
            className={cn(
              "flex items-center gap-3 rounded-[var(--tt-radius-lg)] border px-3.5 py-3 text-left transition-colors",
              selected === null
                ? "border-[var(--tt-border-strong)] bg-[var(--tt-raised)]"
                : "border-[var(--tt-border)] bg-[var(--tt-panel)] hover:border-[var(--tt-border-strong)] hover:bg-[var(--tt-sunken)]",
            )}
          >
            <div className="h-8 w-8 shrink-0 grid place-items-center rounded-md tt-tint-2 text-[var(--tt-fg-dim)]">
              <Ban size={16} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-[13px] font-semibold text-[var(--tt-fg)]">Skip — no AI summaries</div>
              <div className="text-[11px] text-[var(--tt-fg-dim)]">
                Only the deterministic brief is shown. Nothing leaves your machine.
              </div>
            </div>
            {selected === null && (
              <span className="h-5 w-5 grid place-items-center rounded-full bg-[var(--tt-fg-muted)] text-[var(--tt-canvas)]">
                <Check size={12} strokeWidth={3} />
              </span>
            )}
          </button>
        )}
      </div>
    </div>
  );
}

interface ModelDropdownProps {
  label: string;
  value: string | null;
  onChange?: (v: string | null) => void;
  loading: boolean;
  error: string | null;
  empty: boolean;
  emptyHint?: React.ReactNode;
  options: { value: string; label: string; hint?: string }[];
  autoOption: string;
  hint?: string;
}

/** Shared dropdown UI for the model sub-picker. */
function ModelDropdown({
  label, value, onChange, loading, error, empty, emptyHint,
  options, autoOption, hint,
}: ModelDropdownProps) {
  return (
    <div className="mt-2 ml-11 mr-1">
      <label className="block text-[10.5px] font-medium uppercase tracking-[0.1em] text-[var(--tt-fg-muted)] mb-1.5">
        {label}
      </label>
      {loading ? (
        <div className="text-[12px] text-[var(--tt-fg-dim)] italic">Loading…</div>
      ) : error ? (
        <div className="text-[12px] text-[var(--tt-danger-fg)]">{error}</div>
      ) : empty ? (
        <div className="text-[12px] text-[var(--tt-fg-dim)]">{emptyHint}</div>
      ) : (
        <select
          value={value ?? ""}
          onChange={(e) => onChange?.(e.target.value || null)}
          className="w-full h-9 px-3 rounded-md bg-[var(--tt-sunken)] border border-[var(--tt-border-strong)] text-[13px] text-[var(--tt-fg)] focus:outline-none focus:border-[var(--tt-border-focus)] transition-colors"
        >
          <option value="">{autoOption}</option>
          {options.map((o) => (
            <option key={o.value} value={o.value} title={o.hint}>
              {o.label}{o.hint ? ` — ${o.hint}` : ""}
            </option>
          ))}
        </select>
      )}
      {hint && (
        <p className="text-[10.5px] text-[var(--tt-fg-dim)] mt-1.5">{hint}</p>
      )}
    </div>
  );
}

const FIELD_CLS =
  "w-full h-9 px-3 rounded-md bg-[var(--tt-sunken)] border border-[var(--tt-border-strong)] text-[13px] text-[var(--tt-fg)] focus:outline-none focus:border-[var(--tt-border-focus)] transition-colors";
const LABEL_CLS =
  "block text-[10.5px] font-medium uppercase tracking-[0.1em] text-[var(--tt-fg-muted)] mb-1.5";

interface OpenAICompatFormProps {
  model: string | null;
  onModelChange?: (model: string | null) => void;
  config: OpenAICompatConfig;
  onChange?: (cfg: OpenAICompatConfig) => void;
}

/**
 * Config form for the openai_compat backend: endpoint + model + optional bearer
 * token up front, sampling params behind an "Advanced" toggle, and a
 * Test-connection button that pings the server before the user saves.
 */
function OpenAICompatForm({ model, onModelChange, config, onChange }: OpenAICompatFormProps) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null);

  const set = <K extends keyof OpenAICompatConfig>(key: K, value: OpenAICompatConfig[K]) =>
    onChange?.({ ...config, [key]: value });

  const num = (key: keyof OpenAICompatConfig, label: string, step = "0.05") => (
    <div>
      <label className={LABEL_CLS}>{label}</label>
      <input
        type="number"
        step={step}
        value={config[key] as number}
        onChange={(e) => set(key, (e.target.value === "" ? 0 : Number(e.target.value)) as never)}
        className={FIELD_CLS}
      />
    </div>
  );

  const runTest = async () => {
    setTesting(true);
    setResult(null);
    try {
      const r = await testOpenAICompat(model, config);
      setResult(
        r.ok
          ? { ok: true, msg: `Connected — server replied "${(r.sample || "").trim().slice(0, 60)}"` }
          // Prefer the classified hint/message (always human-readable) over the
          // raw error string so a JSON error body never leaks into the UI.
          : { ok: false, msg: r.error_info?.hint || r.error_info?.message || r.error || "Connection failed." },
      );
    } catch (e) {
      setResult({ ok: false, msg: e instanceof Error ? e.message : String(e) });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="mt-2 ml-11 mr-1 space-y-3">
      <div>
        <label className={LABEL_CLS}>Endpoint</label>
        <input
          type="text"
          spellCheck={false}
          placeholder="http://localhost:8080/v1"
          value={config.endpoint}
          onChange={(e) => set("endpoint", e.target.value)}
          className={FIELD_CLS}
        />
        <p className="text-[10.5px] text-[var(--tt-fg-dim)] mt-1.5">
          Base URL of any OpenAI-compatible server (llama.cpp, vLLM, LM Studio, LocalAI…).
          We POST to <code className="font-mono">/chat/completions</code> under it.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className={LABEL_CLS}>Model</label>
          <input
            type="text"
            spellCheck={false}
            placeholder="server model id"
            value={model ?? ""}
            onChange={(e) => onModelChange?.(e.target.value || null)}
            className={FIELD_CLS}
          />
        </div>
        <div>
          <label className={LABEL_CLS}>API key (optional)</label>
          <input
            type="password"
            autoComplete="off"
            placeholder="sk-… (blank if unused)"
            value={config.api_key}
            onChange={(e) => set("api_key", e.target.value)}
            className={FIELD_CLS}
          />
        </div>
      </div>

      <button
        type="button"
        onClick={() => setShowAdvanced((v) => !v)}
        className="text-[11px] font-medium text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)] transition-colors"
      >
        {showAdvanced ? "▾ Hide advanced sampling" : "▸ Advanced sampling"}
      </button>

      {showAdvanced && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            {num("max_tokens", "Max tokens", "1")}
            {num("temperature", "Temperature")}
            {num("top_p", "Top P")}
            {num("top_k", "Top K", "1")}
            {num("min_p", "Min P")}
            {num("presence_penalty", "Presence penalty")}
            {num("repetition_penalty", "Repetition penalty")}
          </div>
          <label className="flex items-center gap-2 text-[12px] text-[var(--tt-fg)] cursor-pointer">
            <input
              type="checkbox"
              checked={config.enable_thinking}
              onChange={(e) => set("enable_thinking", e.target.checked)}
              className="h-3.5 w-3.5 accent-[var(--tt-brand)]"
            />
            Enable thinking (reasoning models — Qwen3 / vLLM)
          </label>
          <p className="text-[10.5px] text-[var(--tt-fg-dim)]">
            Top-K / Min-P / Repetition penalty are non-OpenAI extras; local servers
            honor them and others ignore them.
          </p>
        </div>
      )}

      <div className="flex items-center gap-3 pt-0.5">
        <button
          type="button"
          onClick={runTest}
          disabled={testing || !config.endpoint}
          className="inline-flex items-center gap-1.5 h-8 px-3 rounded-md border border-[var(--tt-border-strong)] bg-[var(--tt-panel)] text-[12px] font-medium text-[var(--tt-fg)] hover:bg-[var(--tt-sunken)] disabled:opacity-50 transition-colors"
        >
          {testing ? <Loader2 size={12} className="animate-spin" /> : <Plug size={12} />}
          Test connection
        </button>
        {result && (
          <span
            className={cn(
              "inline-flex items-center gap-1.5 text-[11.5px]",
              result.ok ? "text-[var(--tt-success-fg)]" : "text-[var(--tt-danger-fg)]",
            )}
          >
            {result.ok ? <Check size={12} /> : <AlertCircle size={12} />}
            {result.msg}
          </span>
        )}
      </div>
    </div>
  );
}
