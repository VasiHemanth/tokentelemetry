import * as React from "react";
import Link from "next/link";
import { recallSessionHref, type AskCitation } from "@/lib/recall";

// Renders model output as React nodes only: paragraphs, lists, code, bold.
// Nothing is parsed as HTML. [S1] markers link to the session when resolved.

type Block =
  | { t: "p"; text: string }
  | { t: "h"; text: string }
  | { t: "ul" | "ol"; items: string[] }
  | { t: "code"; text: string };

export function parseBlocks(src: string): Block[] {
  const lines = src.replace(/\r\n?/g, "\n").split("\n");
  const out: Block[] = [];
  let para: string[] = [];
  let list: { t: "ul" | "ol"; items: string[] } | null = null;
  const flushPara = () => { if (para.length) { out.push({ t: "p", text: para.join(" ") }); para = []; } };
  const flushList = () => { if (list) { out.push(list); list = null; } };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (/^\s*```/.test(line)) {
      flushPara(); flushList();
      const buf: string[] = [];
      i++;
      while (i < lines.length && !/^\s*```/.test(lines[i])) buf.push(lines[i++]);
      out.push({ t: "code", text: buf.join("\n") });
      continue;
    }
    if (!line.trim()) { flushPara(); flushList(); continue; }
    const h = line.match(/^#{1,6}\s+(.*)$/);
    if (h) { flushPara(); flushList(); out.push({ t: "h", text: h[1] }); continue; }
    const ul = line.match(/^\s*[-*+]\s+(.*)$/);
    const ol = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (ul || ol) {
      flushPara();
      const t = ul ? "ul" : "ol";
      if (!list || list.t !== t) { flushList(); list = { t, items: [] }; }
      list.items.push((ul ?? ol)![1]);
      continue;
    }
    if (list && /^\s{2,}\S/.test(line)) { list.items[list.items.length - 1] += " " + line.trim(); continue; }
    flushList();
    para.push(line.trim());
  }
  flushPara(); flushList();
  return out;
}

const INLINE_SRC = /(`[^`\n]+`)|(\*\*[^*\n]+\*\*)|\[(S\d+(?:\s*,\s*S\d+)*)\]/;

function Inline({ text, cites }: { text: string; cites: Map<string, AskCitation> }) {
  const nodes: React.ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  const re = new RegExp(INLINE_SRC, "g");
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const k = nodes.length;
    if (m[1]) {
      nodes.push(
        <code key={k} className="font-mono text-[11.5px] px-1 py-0.5 rounded bg-[var(--tt-sunken)] border border-[var(--tt-border)]">
          {m[1].slice(1, -1)}
        </code>,
      );
    } else if (m[2]) {
      nodes.push(<strong key={k} className="font-semibold text-[var(--tt-fg)]">{m[2].slice(2, -2)}</strong>);
    } else {
      const labels = m[3].split(",").map((s) => s.trim());
      nodes.push(
        <span key={k}>
          [
          {labels.map((l, j) => {
            const c = cites.get(l);
            return (
              <React.Fragment key={l + j}>
                {j > 0 && ", "}
                {c ? (
                  <Link
                    href={recallSessionHref(c.agent, c.id)}
                    title={c.title}
                    className="font-mono text-[11px] text-[var(--tt-brand)] hover:underline"
                  >
                    {l}
                  </Link>
                ) : l}
              </React.Fragment>
            );
          })}
          ]
        </span>,
      );
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return <>{nodes}</>;
}

export function AnswerText({ text, citations }: { text: string; citations: AskCitation[] }) {
  const cites = React.useMemo(() => new Map(citations.map((c) => [c.label, c])), [citations]);
  const blocks = React.useMemo(() => parseBlocks(text), [text]);
  return (
    <div className="space-y-3 text-[13px] leading-relaxed text-[var(--tt-fg)] break-words">
      {blocks.map((b, i) => {
        if (b.t === "p") return <p key={i}><Inline text={b.text} cites={cites} /></p>;
        if (b.t === "h") return <p key={i} className="font-semibold"><Inline text={b.text} cites={cites} /></p>;
        if (b.t === "code") {
          return (
            <pre key={i} className="font-mono text-[11.5px] bg-[var(--tt-sunken)] border border-[var(--tt-border)] rounded-[var(--tt-radius)] px-3 py-2 overflow-x-auto whitespace-pre">
              {b.text}
            </pre>
          );
        }
        const L = b.t === "ul" ? "ul" : "ol";
        return (
          <L key={i} className={b.t === "ul" ? "list-disc pl-5 space-y-1" : "list-decimal pl-5 space-y-1"}>
            {b.items.map((it, j) => <li key={j}><Inline text={it} cites={cites} /></li>)}
          </L>
        );
      })}
    </div>
  );
}
