"use client";

import { useEffect, useRef, useState } from "react";
import { MessagesSquare, Loader2, Trash2 } from "lucide-react";
import { Button } from "@/components/ui";
import { cn } from "@/lib/cn";
import {
  sendSessionChat, MAX_CHAT_MSG_CHARS,
  type ChatMessage, type SummaryErrorInfo,
} from "@/lib/summarizer";
import { SummaryErrorView } from "./SummaryPanel";
import SafeMarkdown from "./SafeMarkdown";

const FOCUS_RING = "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--tt-brand)]";
// Mirrors MAX_CHAT_HISTORY on the server; older messages are not sent.
const HISTORY_SENT = 10;

/**
 * Multi-turn chat about one session. The conversation lives here, in memory,
 * and is sent with every turn. The server searches the transcript for the parts
 * that match the latest question, so nothing is stored and a reload starts over.
 */
export default function SessionChat({ sessionId, agent }: { sessionId: string; agent: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorInfo, setErrorInfo] = useState<SummaryErrorInfo | null>(null);

  const sessionRef = useRef(sessionId);
  // Bumped on every send, clear and session change. A response is applied only
  // if its number is still current.
  const requestRef = useRef(0);
  const inFlight = useRef(false);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    sessionRef.current = sessionId;
    requestRef.current += 1;
    inFlight.current = false;
    setMessages([]);
    setInput("");
    setRunning(false);
    setError(null);
    setErrorInfo(null);
  }, [sessionId, agent]);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [messages, running]);

  const send = async () => {
    const text = input.trim().slice(0, MAX_CHAT_MSG_CHARS);
    if (!text || inFlight.current) return;
    const sid = sessionId;
    const myRequest = ++requestRef.current;
    const history = messages;
    const next: ChatMessage[] = [...history, { role: "user", content: text }];
    inFlight.current = true;
    setMessages(next);
    setInput("");
    setRunning(true);
    setError(null);
    setErrorInfo(null);

    const stillCurrent = () => sessionRef.current === sid && requestRef.current === myRequest;
    // On failure the question goes back into the box so it can be resent.
    const fail = (msg: string | null, info: SummaryErrorInfo | null) => {
      setMessages(history);
      setInput((cur) => cur || text);
      setError(msg);
      setErrorInfo(info);
    };
    try {
      const res = await sendSessionChat(sid, agent, next);
      if (!stillCurrent()) return;
      if (res.reply) {
        const { role, content } = res.reply;
        setMessages([...next, { role, content }]);
      } else {
        fail(res.error ?? "No answer came back.", res.error_info ?? null);
      }
    } catch (e) {
      if (!stillCurrent()) return;
      fail(e instanceof Error ? e.message : "Chat request failed.", null);
    } finally {
      if (stillCurrent()) {
        inFlight.current = false;
        setRunning(false);
      }
    }
  };

  const clear = () => {
    requestRef.current += 1;
    inFlight.current = false;
    setMessages([]);
    setRunning(false);
    setError(null);
    setErrorInfo(null);
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--tt-fg-dim)]">
          <MessagesSquare size={12} /> Chat about this session
        </div>
        <button
          type="button"
          onClick={clear}
          disabled={messages.length === 0 && !running}
          className={cn(
            "inline-flex items-center gap-1 text-[11px] text-[var(--tt-fg-faint)] hover:text-[var(--tt-fg)] disabled:opacity-40",
            FOCUS_RING,
          )}
        >
          <Trash2 size={11} /> Clear conversation
        </button>
      </div>

      <p className="text-[10px] text-[var(--tt-fg-faint)]">
        Each message is a separate call to your summarizer backend and uses your own quota
        (a local model such as ollama costs nothing). Answers cite turns like [t12], the Nth
        message you sent in the session. The conversation is not saved.
      </p>

      {(messages.length > 0 || running) && (
        <div
          role="log"
          aria-live="polite"
          aria-label="Conversation"
          className="max-h-96 space-y-2 overflow-y-auto rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-panel)]/60 p-3"
        >
          {messages.map((m, i) => (
            <div
              key={i}
              className={cn(
                "rounded-md px-3 py-2",
                m.role === "user"
                  ? "ml-8 bg-[var(--tt-sunken)] border border-[var(--tt-border)]"
                  : "mr-8",
              )}
            >
              <div className="mb-1 text-[9px] font-semibold uppercase tracking-[0.14em] text-[var(--tt-fg-dim)]">
                {m.role === "user" ? "You" : "Answer"}
              </div>
              {m.role === "user" ? (
                <p className="text-[12px] text-[var(--tt-fg)] whitespace-pre-wrap break-words">{m.content}</p>
              ) : (
                <SafeMarkdown>{m.content}</SafeMarkdown>
              )}
            </div>
          ))}
          {running && (
            <div className="flex items-center gap-2 text-[12px] text-[var(--tt-fg-muted)]">
              <Loader2 size={13} className="animate-spin text-[var(--tt-brand)]" /> Thinking…
            </div>
          )}
          <div ref={endRef} />
        </div>
      )}
      {messages.length > HISTORY_SENT && (
        <p className="text-[10px] text-[var(--tt-fg-faint)]">Only the last {HISTORY_SENT} messages are sent with each question.</p>
      )}

      {(errorInfo || error) && (
        <div role="alert">
          <SummaryErrorView info={errorInfo} message={error} />
        </div>
      )}

      <textarea
        value={input}
        onChange={(e) => setInput(e.target.value.slice(0, MAX_CHAT_MSG_CHARS))}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            if (!e.repeat && !e.nativeEvent.isComposing) send();
          }
        }}
        rows={2}
        aria-label="Message about this session"
        aria-describedby="session-chat-hint"
        placeholder="e.g. Why did the deploy fail, and what fixed it?"
        className="w-full rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-sunken)] px-3 py-2 text-[12px] text-[var(--tt-fg)] placeholder:text-[var(--tt-fg-faint)] focus:outline-none focus:border-[var(--tt-brand)]"
      />
      <div className="flex items-center justify-between gap-3">
        <span id="session-chat-hint" className="text-[10px] text-[var(--tt-fg-faint)]">
          Cmd/Ctrl+Enter to send.
        </span>
        <Button size="sm" variant="primary" onClick={send} disabled={running || !input.trim()}>
          {running ? <><Loader2 size={13} className="animate-spin" /> Sending…</> : "Send"}
        </Button>
      </div>
    </div>
  );
}
