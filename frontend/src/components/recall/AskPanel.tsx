"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowRight, Loader2, MessageSquare, Search, BookOpen, Settings2, Square } from "lucide-react";

import { useResource } from "@/lib/api";
import { getAgent } from "@/lib/agents";
import { Button } from "@/components/ui";
import { SummaryErrorCard } from "@/components/summarizer/SummaryPanel";
import type { SummaryErrorInfo } from "@/lib/summarizer";
import {
  AskHttpError, describeStep, recallSessionsPath, streamRecallAsk,
  type AskEvent, type RecallSessionsResponse,
} from "@/lib/recall";
import { AnswerText } from "./AnswerText";

type StepEv = Extract<AskEvent, { type: "step" }>;
type AnswerEv = Extract<AskEvent, { type: "answer" }>;
type StatusEv = Extract<AskEvent, { type: "status" }>;

interface Line { key: string; kind: "step" | "obs"; text: string }

interface RunState {
  phase: "idle" | "running" | "done" | "failed";
  question: string;
  status: StatusEv | null;
  lines: Line[];
  answer: AnswerEv | null;
  errorInfo: SummaryErrorInfo | null;
  /** 409: AI summaries are off. */
  summariesOff: boolean;
  message: string | null;
}

const IDLE: RunState = {
  phase: "idle", question: "", status: null, lines: [], answer: null,
  errorInfo: null, summariesOff: false, message: null,
};

export function AskPanel({ project, agents }: { project: string; agents: string[] }) {
  const [input, setInput] = useState("");
  const [run, setRun] = useState<RunState>(IDLE);
  const ctlRef = useRef<AbortController | null>(null);

  // Titles for "Reading <agent> session "title"" lines, from the same scope as the question.
  const sessionsPath = recallSessionsPath(project || null, agents, 200);
  const { data: sessionsData } = useResource<RecallSessionsResponse>(sessionsPath);
  const titles = useMemo(() => {
    const m = new Map<string, { title: string; ts: string | null }>();
    for (const s of sessionsData?.sessions ?? []) m.set(`${s.agent}:${s.id}`, { title: s.title, ts: s.last_ts });
    return m;
  }, [sessionsData]);
  const titlesRef = useRef(titles);
  useEffect(() => { titlesRef.current = titles; }, [titles]);

  // Closing the page or leaving the tab aborts the request so the backend stops spending quota.
  useEffect(() => () => ctlRef.current?.abort(), []);

  const stop = useCallback(() => {
    ctlRef.current?.abort();
    ctlRef.current = null;
    setRun((r) => (r.phase === "running" ? { ...r, phase: "idle", message: "Stopped." } : r));
  }, []);

  const ask = useCallback(async () => {
    const question = input.trim();
    if (!question) return;
    ctlRef.current?.abort();
    const ctl = new AbortController();
    ctlRef.current = ctl;
    setRun({ ...IDLE, phase: "running", question });
    const mine = ctl;
    const live = () => ctlRef.current === mine && !mine.signal.aborted;
    let finished = false;
    try {
      for await (const ev of streamRecallAsk(
        { question, project: project || null, agent: agents.length ? agents.join(",") : null },
        ctl.signal,
      )) {
        if (!live()) return;
        if (ev.type === "status") {
          setRun((r) => ({ ...r, status: ev }));
        } else if (ev.type === "step") {
          const text = describeStep(ev as StepEv, (a, id) => titlesRef.current.get(`${a}:${id}`) ?? null, (a) => getAgent(a).label);
          setRun((r) => ({ ...r, lines: [...r.lines, { key: `s${ev.n}-${r.lines.length}`, kind: "step", text }] }));
        } else if (ev.type === "observation") {
          setRun((r) => ({ ...r, lines: [...r.lines, { key: `o${ev.n}-${r.lines.length}`, kind: "obs", text: ev.summary }] }));
        } else if (ev.type === "answer") {
          finished = true;
          setRun((r) => ({ ...r, phase: "done", answer: ev }));
        } else if (ev.type === "error") {
          finished = true;
          setRun((r) => ({ ...r, phase: "failed", errorInfo: ev.error_info }));
        }
      }
      if (live() && !finished) {
        setRun((r) => ({ ...r, phase: "failed", message: "The connection closed before an answer arrived." }));
      }
    } catch (e) {
      if (!live()) return;
      if (e instanceof AskHttpError && e.status === 409) {
        setRun((r) => ({ ...r, phase: "failed", summariesOff: true }));
      } else {
        setRun((r) => ({
          ...r, phase: "failed", message: e instanceof Error ? e.message : String(e),
        }));
      }
    } finally {
      if (ctlRef.current === mine && mine.signal.aborted === false) ctlRef.current = null;
    }
  }, [input, project, agents]);

  const running = run.phase === "running";

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <textarea
          aria-label="Question about past sessions"
          rows={3}
          maxLength={1000}
          value={input}
          placeholder="Ask about this project's history, e.g. why did we move the render queue to a worker?"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              void ask();
            }
          }}
          className="w-full px-3 py-2 rounded-[var(--tt-radius)] bg-[var(--tt-panel)] border border-[var(--tt-border)] text-[13px] leading-relaxed text-[var(--tt-fg)] placeholder:text-[var(--tt-fg-faint)] hover:border-[var(--tt-border-strong)] focus:border-[color:var(--tt-brand)]/40 focus:outline-none focus:ring-1 focus:ring-[color:var(--tt-brand)]/30 transition-colors resize-y"
        />
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="primary" onClick={() => void ask()} disabled={running || !input.trim()}>
            <MessageSquare size={14} /> Ask
          </Button>
          {running && (
            <Button onClick={stop}><Square size={12} /> Stop</Button>
          )}
          <span className="text-[11px] text-[var(--tt-fg-dim)]">
            Enter to ask, Shift+Enter for a new line.
            {" "}{project ? "Scoped to the selected project." : "Searches all projects."}
          </span>
        </div>
      </div>

      {run.summariesOff && (
        <div role="status" className="flex items-start gap-3 rounded-[var(--tt-radius)] border border-[var(--tt-warn-bd)] bg-[var(--tt-warn-bg)] px-3 py-2.5 text-[12px] text-[var(--tt-warn-fg)]">
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <div className="space-y-1">
            <p>Ask needs AI summaries, which are turned off. Enable a summarizer in Settings, then ask again.</p>
            <Link href="/settings" className="inline-flex items-center gap-1.5 font-medium underline">
              <Settings2 size={12} /> Open Settings <ArrowRight size={12} />
            </Link>
          </div>
        </div>
      )}

      {run.question && !run.summariesOff && (
        <div className="rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] p-4 space-y-3" aria-busy={running}>
          <p className="text-[13px] font-semibold text-[var(--tt-fg)] break-words">{run.question}</p>

          {run.status && (
            <p className="text-[11px] text-[var(--tt-fg-dim)]">
              Answering with <span className="font-mono">{run.status.summarizer}</span>
              {" "}({run.status.mode} search{run.status.project ? `, ${run.status.project.name}` : ""})
            </p>
          )}

          {run.lines.length > 0 && (
            <ul className="space-y-1" aria-live="polite">
              {run.lines.map((l) => (
                <li
                  key={l.key}
                  className={l.kind === "step"
                    ? "flex items-start gap-2 text-[12px] text-[var(--tt-fg-muted)]"
                    : "flex items-start gap-2 pl-5 text-[11px] text-[var(--tt-fg-dim)]"}
                >
                  {l.kind === "step" && (
                    /^Reading/.test(l.text)
                      ? <BookOpen size={12} className="mt-0.5 shrink-0" />
                      : <Search size={12} className="mt-0.5 shrink-0" />
                  )}
                  <span className="min-w-0 break-words">{l.text}</span>
                </li>
              ))}
            </ul>
          )}

          {running && (
            <div className="flex items-center gap-2 text-[12px] text-[var(--tt-fg-dim)]" role="status">
              <Loader2 size={12} className="animate-spin" />
              {run.lines.length === 0 ? "Starting" : "Working"}
            </div>
          )}

          {run.answer && (
            <div className="border-t border-[var(--tt-border)] pt-3 space-y-3">
              <AnswerText text={run.answer.text} citations={run.answer.citations} />
              {run.answer.citations.length > 0 && (
                <ul className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-[var(--tt-fg-dim)]">
                  {run.answer.citations.map((c) => (
                    <li key={c.label} className="min-w-0">
                      <span className="font-mono">{c.label}</span>{" "}
                      <span className="truncate">{getAgent(c.agent).label}: {c.title || "(untitled)"}</span>
                    </li>
                  ))}
                </ul>
              )}
              <p className="text-[11px] text-[var(--tt-fg-dim)] tabular">
                {run.status ? `${run.status.summarizer} · ` : ""}
                {run.answer.elapsed_s.toFixed(1)} s · {run.answer.steps} {run.answer.steps === 1 ? "step" : "steps"}
              </p>
            </div>
          )}

          {run.errorInfo && <SummaryErrorCard info={run.errorInfo} />}
          {run.message && !run.errorInfo && (
            <p className="text-[12px] text-[var(--tt-fg-muted)]">{run.message}</p>
          )}
        </div>
      )}
    </div>
  );
}
