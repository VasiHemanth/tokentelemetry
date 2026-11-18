import { highlightSegments } from "@/lib/recall";

/** Renders text with query needles wrapped in <mark>. Pure React spans, no HTML injection. */
export function Highlight({ text, needles }: { text: string; needles: string[] }) {
  const segs = highlightSegments(text, needles);
  return (
    <>
      {segs.map((s, i) =>
        s.hit ? (
          <mark
            key={i}
            className="rounded-sm px-0.5 bg-[color:var(--tt-brand)]/20 text-[var(--tt-fg)]"
          >
            {s.text}
          </mark>
        ) : (
          <span key={i}>{s.text}</span>
        ),
      )}
    </>
  );
}
