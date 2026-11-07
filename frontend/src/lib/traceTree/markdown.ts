/** Presentation hint only. Readers can always switch between formatted and raw text. */
export function looksLikeMarkdown(text: string): boolean {
  if (/^(?:diff --git |@@ |Traceback \(|[ \t]*File "[^"]+", line \d+)/m.test(text)) return false;
  return /(?:^|\n) {0,3}(?:#{1,6}\s+\S|```|~~~|>\s+\S|(?:[-+*]|\d+[.)])\s+\S)/.test(text)
    || /^[ \t]*\|?[ \t]*:?-{3,}:?[ \t]*\|[ \t]*:?-{3,}:?/m.test(text)
    || /\[[^\]\n]+\]\([^\s)]+\)/.test(text)
    || /(?:^|[^`])`[^`\n]+`(?!`)/m.test(text)
    || /\*\*[^*\n]+\*\*|(?:^|\s)__[^_\n]+__(?=\s|$)/m.test(text);
}
