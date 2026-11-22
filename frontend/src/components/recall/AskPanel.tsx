"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowRight, Loader2, MessageSquare, Search, BookOpen, Settings2, Square, Trash2 } from "lucide-react";

import { useResource } from "@/lib/api";
import { getAgent } from "@/lib/agents";
import { Button } from "@/components/ui";
import { SummaryErrorCard } from "@/components/summarizer/SummaryPanel";
import type { SummaryErrorInfo } from "@/lib/summarizer";
import {
  AskHttpError, deleteRecallConversation, describeStep, fetchRecallConversation, recallSessionHref, recallSessionsPath, streamRecallAsk,
  type AskEvent, type RecallConversation, type RecallConversationSummary, type RecallSessionsResponse,
} from "@/lib/recall";
import { AnswerText, citationDoc, isDocCitation } from "./AnswerText";
import { DocumentDrawer, RecallImage, type OpenDoc } from "./DocumentDrawer";
import { AskHistory } from "./AskHistory";
import { DocTypeIcon } from "./docTypes";

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

function conversationId(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join("-");
}

export function AskPanel({ project, projectName, agents }: { project: string; projectName: string | null; agents: string[] }) {
  const [input, setInput] = useState("");
  const [run, setRun] = useState<RunState>(IDLE);
  const ctlRef = useRef<AbortController | null>(null);
  const [openDoc, setOpenDoc] = useState<OpenDoc | null>(null);
  const [chat, setChat] = useState<RecallConversation | null>(null);
  const [loadingChat, setLoadingChat] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const chatRequest = useRef<AbortController | null>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const transcript = useRef<HTMLDivElement>(null);
  const history = useResource<{ conversations: RecallConversationSummary[] }>("/recall/conversations");
  const { refetch } = history;
  const scopeProject = chat ? chat.project : project || null;
  const scopeAgents = chat ? chat.agents : agents;

  // Titles for "Reading <agent> session "title"" lines, from the same scope as the question.
  const sessionsPath = recallSessionsPath(scopeProject, scopeAgents, 200);
  const { data: sessionsData } = useResource<RecallSessionsResponse>(sessionsPath);
  const titles = useMemo(() => {
    const m = new Map<string, { title: string; ts: string | null }>();
    for (const s of sessionsData?.sessions ?? []) m.set(`${s.agent}:${s.id}`, { title: s.title, ts: s.last_ts });
    return m;
  }, [sessionsData]);
  const titlesRef = useRef(titles);
  useEffect(() => { titlesRef.current = titles; }, [titles]);

  // Closing the page or leaving the tab aborts the request so the backend stops spending quota.
  useEffect(() => () => {
    ctlRef.current?.abort();
    ctlRef.current = null;
    chatRequest.current?.abort();
  }, []);

  const loadChat = async (id: string) => {
    const ctl = new AbortController();
    chatRequest.current?.abort();
    chatRequest.current = ctl;
    setLoadingChat(true);
    setChatError(null);
    try {
      const item = await fetchRecallConversation(id, ctl.signal);
      if (ctl.signal.aborted) return;
      setChat(item);
      setRun(IDLE);
      setInput("");
      setOpenDoc(null);
    } catch (e) {
      if (!ctl.signal.aborted) setChatError(e instanceof Error ? e.message : "Could not open the conversation.");
    } finally {
      if (!ctl.signal.aborted) setLoadingChat(false);
    }
  };

  const startNew = () => {
    setChat(null);
    setInput("");
    setRun(IDLE);
    setOpenDoc(null);
    setChatError(null);
    composer.current?.focus();
  };

  const removeChat = async () => {
    if (!chat || !window.confirm("Delete this Ask conversation and its messages?")) return;
    const ctl = new AbortController();
    chatRequest.current = ctl;
    setLoadingChat(true);
    try {
      await deleteRecallConversation(chat.id);
      if (ctl.signal.aborted) return;
      startNew();
      refetch();
    } catch (e) {
      if (!ctl.signal.aborted) setChatError(e instanceof Error ? e.message : "Could not delete the conversation.");
    } finally {
      if (!ctl.signal.aborted) setLoadingChat(false);
    }
  };

  const stop = () => ctlRef.current?.abort();

  const ask = async () => {
    const question = input.trim();
    if (!question || ctlRef.current || loadingChat) return;
    const id = chat?.id ?? conversationId();
    const ctl = new AbortController();
    ctlRef.current = ctl;
    setInput("");
    setChatError(null);
    setRun({ ...IDLE, phase: "running", question });
    let accepted = false;
    let gotAnswer = false;
    try {
      for await (const ev of streamRecallAsk(
        { question, project: scopeProject, agent: scopeAgents.join(",") || null, conversation_id: id },
        ctl.signal,
      )) {
        if (ctl.signal.aborted) break;
        if (ev.type === "status") {
          accepted = true;
          refetch();
          setRun((r) => ({ ...r, status: ev }));
        } else if (ev.type === "step") {
          const text = describeStep(ev, (a, sid) => titlesRef.current.get(`${a}:${sid}`) ?? null, (a) => getAgent(a).label);
          setRun((r) => ({ ...r, lines: [...r.lines, { key: `s${ev.n}-${r.lines.length}`, kind: "step", text }] }));
        } else if (ev.type === "observation") {
          setRun((r) => ({ ...r, lines: [...r.lines, { key: `o${ev.n}-${r.lines.length}`, kind: "obs", text: ev.summary }] }));
        } else if (ev.type === "answer") {
          gotAnswer = true;
          setRun((r) => ({ ...r, answer: ev }));
        } else if (ev.type === "error") {
          setRun((r) => ({ ...r, errorInfo: ev.error_info }));
        }
      }
    } catch (e) {
      if (!ctl.signal.aborted) {
        if (e instanceof AskHttpError && e.status === 409) {
          setRun((r) => ({ ...r, summariesOff: true }));
        } else {
          setRun((r) => ({ ...r, message: e instanceof Error ? e.message : String(e) }));
        }
      }
    } finally {
      if (ctlRef.current !== ctl) return;
      if (accepted) {
        const refresh = new AbortController();
        chatRequest.current = refresh;
        try {
          const item = await fetchRecallConversation(id, refresh.signal);
          if (refresh.signal.aborted) return;
          setChat(item);
          setRun((r) => ({
            ...r, phase: gotAnswer ? "done" : "failed", question: "", answer: null,
            message: r.message ?? (gotAnswer || r.errorInfo ? null :
              ctl.signal.aborted ? "Stopped." : "The connection closed before an answer arrived."),
          }));
        } catch {
          if (refresh.signal.aborted) return;
          setChatError("Could not reload the saved chat. Open it from Ask history to try again.");
          setRun((r) => ({ ...r, phase: gotAnswer ? "done" : "failed" }));
        }
        refetch();
      } else {
        if (ctl.signal.aborted) refetch();
        setInput(question);
        setRun((r) => ({ ...r, phase: "failed", question: "", message: r.message ??
          (r.summariesOff ? null : ctl.signal.aborted ? "Stopped." : "The request ended before it was saved.") }));
      }
      ctlRef.current = null;
    }
  };

  const running = run.phase === "running";
  const turnCount = chat?.turns.length ?? 0;
  const chatId = chat?.id;
  useEffect(() => {
    const pane = transcript.current;
    if (pane) pane.scrollTop = pane.scrollHeight;
  }, [chatId, running, turnCount]);

  return (
    <div className="grid min-w-0 gap-4 lg:grid-cols-[clamp(14rem,20%,20rem)_minmax(0,1fr)]">
      <AskHistory items={history.data?.conversations ?? []} activeId={chat?.id}
        loading={history.loading} error={history.error} disabled={running || loadingChat}
        onSelect={(id) => void loadChat(id)} onNew={startNew} onRetry={refetch} />
      <div className="min-w-0 space-y-4 rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] p-3 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-2 border-b border-[var(--tt-border)] pb-3">
          <div className="min-w-0 flex-1">
            <h2 className="break-words text-[15px] font-semibold text-[var(--tt-fg)]">{chat?.title ?? "New conversation"}</h2>
            <p className="mt-1 text-[12px] text-[var(--tt-fg-muted)]">
              {chat ? chat.project_name || "All projects" : projectName ?? "All projects"}
              {scopeAgents.length > 0 && ` · ${scopeAgents.map((a) => getAgent(a).label).join(", ")}`}
            </p>
          </div>
          {chat && <Button size="sm" variant="ghost" aria-label="Delete chat" disabled={running || loadingChat} onClick={() => void removeChat()}>
            <Trash2 size={14} />
          </Button>}
        </div>

        {loadingChat && <p role="status" className="text-xs text-[var(--tt-fg-muted)]">Loading conversation…</p>}
        {chatError && <p role="alert" className="text-xs text-[var(--tt-danger-fg)]">{chatError}</p>}
        <div ref={transcript} aria-label="Conversation messages" className="max-h-[min(62vh,48rem)] space-y-5 overflow-y-auto">
          {!chat && !run.question && !run.summariesOff && (
            <div className="space-y-1 py-8 text-center">
              <p className="text-sm font-semibold text-[var(--tt-fg)]">What did we decide, and what should we do next?</p>
              <p className="text-xs text-[var(--tt-fg-muted)]">Ask about past work or brainstorm with the sources Recall finds.</p>
            </div>
          )}
          {chat?.turns.map((turn) => (
            <div key={turn.id} className="space-y-3">
              <Question text={turn.question} />
              {turn.answer ? <ChatAnswer answer={turn.answer} project={scopeProject || ""} setOpenDoc={setOpenDoc} /> : (
                <p className="text-xs text-[var(--tt-fg-muted)]">No answer saved.</p>
              )}
            </div>
          ))}

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
              <Question text={run.question} />

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

              {run.answer && <ChatAnswer answer={run.answer} project={scopeProject || ""} setOpenDoc={setOpenDoc} />}

              {run.errorInfo && <SummaryErrorCard info={run.errorInfo} />}
              {run.message && !run.errorInfo && (
                <p className="text-[12px] text-[var(--tt-fg-muted)]">{run.message}</p>
              )}
            </div>
          )}
          {!run.question && run.phase === "done" && run.lines.length > 0 && (
            <details className="text-[12px] text-[var(--tt-fg-muted)]">
              <summary className="cursor-pointer">Research steps</summary>
              <ol className="mt-2 space-y-1">
                {run.lines.map((line) => <li key={line.key} className={line.kind === "obs" ? "pl-3" : ""}>{line.text}</li>)}
              </ol>
            </details>
          )}
        </div>
        {!run.question && run.errorInfo && <SummaryErrorCard info={run.errorInfo} />}
        {!run.question && run.message && <p role="status" className="text-xs text-[var(--tt-fg-muted)]">{run.message}</p>}
        <div className="space-y-2 border-t border-[var(--tt-border)] pt-3">
          <textarea
            ref={composer}
            aria-label="Question about past sessions"
            rows={3}
            maxLength={1000}
            value={input}
            placeholder={chat ? "Ask a follow-up…" : "Ask about a decision, change, or next step…"}
            disabled={running || loadingChat}
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
            <Button variant="primary" onClick={() => void ask()} disabled={running || loadingChat || !input.trim()}>
              <MessageSquare size={14} /> Ask
            </Button>
            {running && (
              <Button onClick={stop}><Square size={12} /> Stop</Button>
            )}
            <span className="text-[11px] text-[var(--tt-fg-dim)]">
              Enter to ask, Shift+Enter for a new line.
            </span>
          </div>
        </div>

        <DocumentDrawer doc={openDoc} project={scopeProject || ""} onClose={() => setOpenDoc(null)} />
      </div>
    </div>
  );
}


function Question({ text }: { text: string }) {
  return (
    <p className="ml-auto w-fit max-w-[92%] whitespace-pre-wrap break-words rounded-[var(--tt-radius-lg)] bg-[var(--tt-sunken)] px-3 py-2 text-[13px] text-[var(--tt-fg)]">
      {text}
    </p>
  );
}

function ChatAnswer({ answer, project, setOpenDoc }: { answer: AnswerEv; project: string; setOpenDoc: (doc: OpenDoc) => void }) {
  return (
    <div className="space-y-3 min-w-0">
      <AnswerText text={answer.text} citations={answer.citations} onOpenDoc={setOpenDoc} />
      {answer.citations.length > 0 && (
        <ul className="flex flex-wrap gap-x-4 gap-y-2 text-[11px] text-[var(--tt-fg-dim)]">
          {answer.citations.map((c) => {
            const doc = isDocCitation(c);
            const d = doc ? citationDoc(c) : null;
            return (
              <li key={c.label} className="min-w-0 flex items-start gap-1.5">
                <DocTypeIcon type={doc ? c.doc_type ?? "markdown" : "session"} size={12} className="mt-0.5 shrink-0" />
                <span className="min-w-0 space-y-1">
                  <span>
                    <span className="font-mono">{c.label}</span>{" "}
                    {d ? (
                      <button type="button" onClick={() => setOpenDoc(d)} className="truncate text-left hover:underline text-[var(--tt-brand)]">
                        {getAgent(c.agent).label}: {c.title || "(untitled)"}
                      </button>
                    ) : (
                      <Link href={recallSessionHref(c.agent, c.id)} className="truncate hover:underline text-[var(--tt-brand)]">
                        {getAgent(c.agent).label}: {c.title || "(untitled)"}
                      </Link>
                    )}
                  </span>
                  {d && d.type === "image" && (
                    <span className="block"><RecallImage docId={d.docId} project={project} alt={c.title || "Cited image"} className="max-h-24 rounded border border-[var(--tt-border)]" /></span>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      <p className="text-[11px] text-[var(--tt-fg-dim)] tabular">

        {answer.elapsed_s.toFixed(1)} s · {answer.steps} {answer.steps === 1 ? "step" : "steps"}
      </p>
    </div>
  );
}
