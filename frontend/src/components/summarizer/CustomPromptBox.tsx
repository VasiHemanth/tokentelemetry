"use client";

import { useEffect, useRef, useState } from "react";
import { MessageSquareText, Loader2, RefreshCw } from "lucide-react";
import { Badge, Button } from "@/components/ui";
import { cn } from "@/lib/cn";
import {
  getCustomSummaries, generateCustomSummary,
  CUSTOM_PROMPT_PRESETS, MAX_CUSTOM_PROMPT_CHARS,
  type CustomSummary, type SummaryErrorInfo,
} from "@/lib/summarizer";
import { SummaryErrorView } from "./SummaryPanel";
import SafeMarkdown from "./SafeMarkdown";

const FOCUS_RING = "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--tt-brand)]";

/**
 * Ask the configured summarizer backend a question of your own about this
 * session ("list the decisions", "what is still open"). Answers are cached per
 * prompt, so reopening the page shows them without another model call.
 */
export default function CustomPromptBox({ sessionId, agent }: { sessionId: string; agent: string }) {
  const [prompt, setPrompt] = useState("");
  const [items, setItems] = useState<CustomSummary[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorInfo, setErrorInfo] = useState<SummaryErrorInfo | null>(null);
  const [errorFor, setErrorFor] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [unsaved, setUnsaved] = useState(false);

  // The latest session id, so a run that resolves after navigation is dropped.
  const sessionRef = useRef(sessionId);
  // Set synchronously so a held key or double click cannot start two runs.
  const inFlight = useRef(false);

  useEffect(() => {
    sessionRef.current = sessionId;
    setPrompt("");
    setItems([]);
    setRunning(false);
    setError(null);
    setErrorInfo(null);
    setErrorFor(null);
    setLoadFailed(false);
    setUnsaved(false);
    inFlight.current = false;
    let cancelled = false;
    getCustomSummaries(sessionId, agent)
      .then((r) => {
        if (cancelled) return;
        // Merge so a run that finished before this list arrived is not lost.
        setItems((prev) => [...prev, ...r.filter((x) => !prev.some((p) => p.prompt_hash === x.prompt_hash))]);
      })
      .catch(() => { if (!cancelled) setLoadFailed(true); });
    return () => { cancelled = true; };
  }, [sessionId, agent]);

  const run = async (text: string, force = false) => {
    const trimmed = text.trim();
    if (!trimmed || inFlight.current) return;
    const sid = sessionId;
    inFlight.current = true;
    setRunning(true);
    setError(null);
    setErrorInfo(null);
    setErrorFor(null);
    setUnsaved(false);
    try {
      const res = await generateCustomSummary(sid, agent, trimmed, force);
      if (sessionRef.current !== sid) return;
      if (res.error) {
        setError(res.error);
        setErrorFor(trimmed);
        if (res.error_info) setErrorInfo(res.error_info);
      } else if (res.item) {
        const item = res.item;
        setItems((prev) => [item, ...prev.filter((p) => p.prompt_hash !== item.prompt_hash)]);
        if (res.persisted === false) setUnsaved(true);
        // Keep anything typed while the model was running, and leave a draft
        // alone when this was a re-run of an existing answer.
        if (!force) setPrompt((cur) => (cur.trim() === trimmed ? "" : cur));
      }
    } catch (e) {
      if (sessionRef.current !== sid) return;
      setError(e instanceof Error ? e.message : "Failed to run the prompt.");
      setErrorFor(trimmed);
    } finally {
      if (sessionRef.current === sid) {
        inFlight.current = false;
        setRunning(false);
      }
    }
  };

  const clearError = () => {
    setError(null);
    setErrorInfo(null);
    setErrorFor(null);
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--tt-fg-dim)]">
        <MessageSquareText size={12} /> Ask about this session
      </div>

      <div role="group" aria-label="Example prompts" className="flex flex-wrap gap-1.5">
        {CUSTOM_PROMPT_PRESETS.map((p) => (
          <button
            key={p.label}
            type="button"
            onClick={() => { setPrompt(p.prompt); clearError(); }}
            className={cn(
              "h-6 px-2 rounded-md border border-[var(--tt-border)] bg-[var(--tt-sunken)] text-[11px] text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] hover:border-[var(--tt-border-strong)]",
              FOCUS_RING,
            )}
          >
            {p.label}
          </button>
        ))}
      </div>

      <textarea
        value={prompt}
        onChange={(e) => { setPrompt(e.target.value.slice(0, MAX_CUSTOM_PROMPT_CHARS)); if (error) clearError(); }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            if (!e.repeat && !e.nativeEvent.isComposing) run(prompt);
          }
        }}
        rows={3}
        aria-label="Question about this session"
        aria-describedby="custom-prompt-hint"
        placeholder="e.g. What did we decide about caching, and why?"
        className="w-full rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-sunken)] px-3 py-2 text-[12px] text-[var(--tt-fg)] placeholder:text-[var(--tt-fg-faint)] focus:outline-none focus:border-[var(--tt-brand)]"
      />
      <div className="flex items-center justify-between gap-3">
        <span id="custom-prompt-hint" className="text-[10px] text-[var(--tt-fg-faint)]">
          Sent to your summarizer backend with a condensed brief and message excerpts. Cmd/Ctrl+Enter to run.
        </span>
        <Button size="sm" variant="primary" onClick={() => run(prompt)} disabled={running || !prompt.trim()}>
          {running ? <><Loader2 size={13} className="animate-spin" /> <span aria-live="polite">Running…</span></> : "Run"}
        </Button>
      </div>

      {(errorInfo || error) && (
        <div role="alert" className="space-y-1">
          {errorFor && (
            <p className="text-[10px] text-[var(--tt-fg-faint)] truncate">Failed: {errorFor}</p>
          )}
          <SummaryErrorView info={errorInfo} message={error} />
        </div>
      )}
      {loadFailed && (
        <p className="text-[10px] text-[var(--tt-fg-faint)]">Could not load saved answers.</p>
      )}
      {unsaved && (
        <p className="text-[10px] text-[var(--tt-fg-faint)]">This answer could not be saved and will be gone after a reload.</p>
      )}

      {items.map((it) => (
        <div key={it.prompt_hash} className="rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-panel)]/60 p-3.5">
          <div className="flex items-start justify-between gap-3 mb-2">
            <p className="text-[11px] font-medium text-[var(--tt-fg-muted)] whitespace-pre-wrap break-words">{it.prompt}</p>
            <div className="flex items-center gap-2 shrink-0">
              {it.stale && <Badge variant="warn" size="xs">Stale</Badge>}
              <button
                type="button"
                title="Run again"
                aria-label={`Run again: ${it.prompt}`}
                onClick={() => run(it.prompt, true)}
                disabled={running}
                className={cn("text-[var(--tt-fg-faint)] hover:text-[var(--tt-fg)]", FOCUS_RING, running && "opacity-50")}
              >
                <RefreshCw size={12} />
              </button>
            </div>
          </div>
          <SafeMarkdown>{it.answer}</SafeMarkdown>
          <div className="mt-2 text-[10px] font-mono text-[var(--tt-fg-faint)]">
            {it.backend}{it.model ? ` · ${it.model}` : ""} · {new Date(it.generated_at).toLocaleString()}
          </div>
        </div>
      ))}
    </div>
  );
}
