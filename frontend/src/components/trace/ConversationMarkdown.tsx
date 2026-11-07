"use client";

import { isValidElement, memo, useState, type ReactNode } from "react";
import { Check, Code2, Copy } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

function ConversationMarkdown({ text, compact = false }: { text: string; compact?: boolean }) {
  return <div className={`conversation-prose text-[var(--tt-fg)] ${compact ? "text-sm leading-6" : "text-[15px] leading-7"}`}>
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
      pre: ({ children }) => <CodePanel>{children}</CodePanel>,
      img: ({ alt }) => <span className="text-sm text-[var(--tt-fg-muted)]">{`[image${alt ? `: ${alt}` : ""}]`}</span>,
      table: ({ children }) => <div className="my-4 max-w-full overflow-x-auto rounded-lg border border-[var(--tt-border)]"><table>{children}</table></div>,
    }}>{text}</ReactMarkdown>
  </div>;
}

export default memo(ConversationMarkdown);

function CodePanel({ children }: { children: ReactNode }) {
  const [copied, setCopied] = useState(false);
  const code = isValidElement<{ className?: string; children?: ReactNode }>(children) ? children.props : null;
  const source = typeof code?.children === "string" ? code.children : null;
  const language = /language-([^\s]+)/.exec(code?.className ?? "")?.[1] ?? "Code";
  return <div className="my-4 min-w-0 overflow-hidden rounded-lg border border-[var(--tt-border-strong)] bg-[var(--tt-canvas)]">
    <div className="flex items-center justify-between gap-3 border-b border-[var(--tt-border)] px-3 py-2 text-xs text-[var(--tt-fg-muted)]"><span className="inline-flex items-center gap-2 font-mono"><Code2 size={13} />{language}</span>{source !== null && <button type="button" aria-label="Copy code" className="inline-flex items-center gap-1.5 rounded px-1.5 py-1 hover:bg-[var(--tt-raised)] hover:text-[var(--tt-fg)]" onClick={async () => { try { await navigator.clipboard.writeText(source); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { setCopied(false); } }}>{copied ? <Check size={12} /> : <Copy size={12} />}{copied ? "Copied" : "Copy"}</button>}</div>
    <pre className="m-0 overflow-x-auto px-4 py-3 font-mono text-xs leading-6">{children}</pre>
  </div>;
}
