"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Markdown for model output. The text can be steered by transcript content, so
 * images are never loaded (a remote image URL would send data to a third party
 * without a click) and links open in a new tab without a referrer. Raw HTML is
 * not interpreted, and the default URL transform drops javascript: links.
 */
export default function SafeMarkdown({ children }: { children: string }) {
  return (
    <div
      className={
        "prose prose-sm max-w-none text-[var(--tt-fg)] text-[12px] leading-relaxed break-words " +
        "[&_pre]:overflow-x-auto [&_pre]:text-[10px] [&_table]:block [&_table]:overflow-x-auto " +
        "[&_th]:text-left [&_th]:px-2 [&_td]:px-2 [&_td]:border [&_td]:border-[var(--tt-border)]"
      }
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          img: ({ alt }) => (
            <span className="text-[var(--tt-fg-faint)]">[image{alt ? `: ${alt}` : ""}]</span>
          ),
          a: ({ href, children: kids }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[var(--tt-brand)] underline"
            >
              {kids}
            </a>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
