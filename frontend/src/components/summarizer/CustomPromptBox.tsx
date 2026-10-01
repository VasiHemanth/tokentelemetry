"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { MessageSquareText, Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui";
import { cn } from "@/lib/cn";
import {
  getCustomSummaries, generateCustomSummary,
  CUSTOM_PROMPT_PRESETS, MAX_CUSTOM_PROMPT_CHARS,
  type CustomSummary, type SummaryErrorInfo,
} from "@/lib/summarizer";
import { SummaryErrorCard } from "./SummaryPanel";

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

  useEffect(() => {
    let cancelled = false;
    getCustomSummaries(sessionId)
      .then((r) => { if (!cancelled) setItems(r); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [sessionId]);

  const run = async (text: string, force = false) => {
    const trimmed = text.trim();
    if (!trimmed || running) return;
    setRunning(true);
    setError(null);
    setErrorInfo(null);
    try {
      const res = await generateCustomSummary(sessionId, agent, trimmed, force);
      if (res.error) {
        setError(res.error);
        if (res.error_info) setErrorInfo(res.error_info);
      } else if (res.item) {
        const item = res.item;
        setItems((prev) => [item, ...prev.filter((p) => p.prompt_hash !== item.prompt_hash)]);
        setPrompt("");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to run the prompt.");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-3 border-t border-[var(--tt-border)] pt-5">
      <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--tt-fg-dim)]">
        <MessageSquareText size={12} /> Ask about this session
      </div>

      <div className="flex flex-wrap gap-1.5">
        {CUSTOM_PROMPT_PRESETS.map((p) => (
          <button
            key={p.label}
            type="button"
            onClick={() => setPrompt(p.prompt)}
            className="h-6 px-2 rounded-md border border-[var(--tt-border)] bg-[var(--tt-sunken)] text-[11px] text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] hover:border-[var(--tt-border-strong)]"
          >
            {p.label}
          </button>
        ))}
      </div>

      <textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value.slice(0, MAX_CUSTOM_PROMPT_CHARS))}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) run(prompt);
        }}
        rows={3}
        placeholder="e.g. What did we decide about caching, and why?"
        className="w-full rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-sunken)] px-3 py-2 text-[12px] text-[var(--tt-fg)] placeholder:text-[var(--tt-fg-faint)] focus:outline-none focus:border-[var(--tt-brand)]"
      />
      <div className="flex items-center justify-between gap-3">
        <span className="text-[10px] text-[var(--tt-fg-faint)]">
          Sent to your summarizer backend with a condensed brief and message excerpts. Cmd/Ctrl+Enter to run.
        </span>
        <Button size="sm" variant="primary" onClick={() => run(prompt)} disabled={running || !prompt.trim()}>
          {running ? <><Loader2 size={13} className="animate-spin" /> Running…</> : "Run"}
        </Button>
      </div>

      {errorInfo ? (
        <SummaryErrorCard info={errorInfo} />
      ) : error ? (
        <p className="text-[12px] text-[var(--tt-danger-fg)]">{error}</p>
      ) : null}

      {items.map((it) => (
        <div key={it.prompt_hash} className="rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-panel)]/60 p-3.5">
          <div className="flex items-start justify-between gap-3 mb-2">
            <p className="text-[11px] font-medium text-[var(--tt-fg-muted)] whitespace-pre-wrap">{it.prompt}</p>
            <button
              type="button"
              title="Run again"
              onClick={() => run(it.prompt, true)}
              disabled={running}
              className={cn("shrink-0 text-[var(--tt-fg-faint)] hover:text-[var(--tt-fg)]", running && "opacity-50")}
            >
              <RefreshCw size={12} />
            </button>
          </div>
          <div className="prose prose-sm max-w-none text-[var(--tt-fg)] text-[12px] leading-relaxed">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{it.answer}</ReactMarkdown>
          </div>
          <div className="mt-2 text-[10px] font-mono text-[var(--tt-fg-faint)]">
            {it.backend}{it.model ? ` · ${it.model}` : ""} · {new Date(it.generated_at).toLocaleString()}
          </div>
        </div>
      ))}
    </div>
  );
}
