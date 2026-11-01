/**
 * Turns a span's raw content value into display text. Values are the trace's
 * own objects and can be megabytes, so nothing here serializes more than the
 * display cap: strings are sliced and objects are walked with an early stop.
 */

export const CONTENT_CAP = 20_000;

export interface FormattedContent {
  kind: "text" | "json" | "empty";
  text: string;
  truncated: boolean;
  /** Exact for strings; a lower bound for large objects (the walk stops at the cap). */
  fullLength: number;
}

const EMPTY: FormattedContent = { kind: "empty", text: "", truncated: false, fullLength: 0 };
const MAX_DEPTH = 40;
const MAX_PARSE = 2_000_000;

class Acc {
  parts: string[] = [];
  len = 0;
  total = 0;
  over = false;
  cap: number;
  constructor(cap: number) {
    this.cap = cap;
  }
  add(s: string) {
    this.total += s.length;
    if (this.over) return;
    const room = this.cap - this.len;
    if (s.length > room) {
      this.parts.push(s.slice(0, Math.max(0, room)));
      this.len = this.cap;
      this.over = true;
    } else {
      this.parts.push(s);
      this.len += s.length;
    }
  }
  get text() {
    return this.parts.join("");
  }
}

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);

function isBlockArray(v: unknown[]): boolean {
  return v.length > 0 && v.every((b) => typeof b === "string" || (isObj(b) && (typeof b.type === "string" || "functionResponse" in b || "functionCall" in b || typeof b.text === "string")));
}

function writeJson(acc: Acc, v: unknown, indent: string, depth: number) {
  if (acc.over) return;
  if (v === null || typeof v === "number" || typeof v === "boolean") return acc.add(String(v));
  if (typeof v === "string") return acc.add(JSON.stringify(v.length > acc.cap + 2 ? v.slice(0, acc.cap + 2) : v));
  if (typeof v !== "object") return acc.add(JSON.stringify(String(v)));
  if (depth > MAX_DEPTH) return acc.add('"..."');
  const inner = indent + "  ";
  if (Array.isArray(v)) {
    if (!v.length) return acc.add("[]");
    acc.add("[\n");
    for (let i = 0; i < v.length && !acc.over; i++) {
      acc.add(inner);
      writeJson(acc, v[i], inner, depth + 1);
      acc.add(i < v.length - 1 ? ",\n" : "\n");
    }
    return acc.add(indent + "]");
  }
  const keys = Object.keys(v);
  if (!keys.length) return acc.add("{}");
  acc.add("{\n");
  for (let i = 0; i < keys.length && !acc.over; i++) {
    acc.add(`${inner}${JSON.stringify(keys[i])}: `);
    writeJson(acc, (v as Obj)[keys[i]], inner, depth + 1);
    acc.add(i < keys.length - 1 ? ",\n" : "\n");
  }
  acc.add(indent + "}");
}

/** Text of one content block, appended to acc. Returns false when the block added nothing. */
function writeBlock(acc: Acc, b: unknown, depth: number): boolean {
  if (typeof b === "string") {
    acc.add(b);
    return b.length > 0;
  }
  if (!isObj(b) || depth > MAX_DEPTH) {
    writeJson(acc, b, "", depth);
    return true;
  }
  const type = typeof b.type === "string" ? b.type : "";
  if (typeof b.text === "string" && (type === "text" || type === "" || type === "input_text" || type === "output_text" || type === "summary_text" || type === "reasoning_text")) {
    acc.add(b.text);
    return b.text.length > 0;
  }
  if (type === "thinking" && typeof b.thinking === "string") {
    acc.add(b.thinking);
    return true;
  }
  if (type === "image" || type === "input_image" || type === "image_url") {
    acc.add("[image]");
    return true;
  }
  if (type === "tool_result" && "content" in b) return writeValue(acc, b.content, depth + 1);
  if (isObj(b.functionResponse)) return writeValue(acc, (b.functionResponse as Obj).response ?? b.functionResponse, depth + 1);
  if (type === "tool_use" || isObj(b.functionCall)) {
    const name = typeof b.name === "string" ? b.name : isObj(b.functionCall) ? String((b.functionCall as Obj).name ?? "") : "";
    acc.add(`[tool call${name ? `: ${name}` : ""}]`);
    return true;
  }
  if (type) {
    acc.add(`[${type} block]`);
    return true;
  }
  writeJson(acc, b, "", depth);
  return true;
}

function writeValue(acc: Acc, v: unknown, depth: number): boolean {
  if (Array.isArray(v) && isBlockArray(v)) {
    let any = false;
    for (const b of v) {
      if (acc.over) break;
      const before = acc.total;
      if (any) acc.add("\n\n");
      if (writeBlock(acc, b, depth)) any = true;
      else if (acc.total === before + 2) acc.total -= 2;
    }
    return any;
  }
  if (typeof v === "string") {
    acc.add(v);
    return v.length > 0;
  }
  writeJson(acc, v, "", depth);
  return true;
}

function looksJson(s: string): boolean {
  const t = s.trimStart();
  return (t[0] === "{" || t[0] === "[") && s.length <= MAX_PARSE;
}

export function formatContent(value: unknown, cap = CONTENT_CAP): FormattedContent {
  if (value == null) return EMPTY;
  let v = value;

  if (typeof v === "string") {
    if (!v.trim()) return EMPTY;
    if (looksJson(v)) {
      try {
        const parsed = JSON.parse(v);
        if (typeof parsed === "object" && parsed !== null) v = parsed;
      } catch {
        // not JSON, show as text
      }
    }
    if (typeof v === "string") {
      const truncated = v.length > cap;
      return { kind: "text", text: truncated ? v.slice(0, cap) : v, truncated, fullLength: v.length };
    }
  }

  if (Array.isArray(v) && !v.length) return EMPTY;
  if (isObj(v) && !Object.keys(v).length) return EMPTY;

  const acc = new Acc(cap);
  if (Array.isArray(v) && isBlockArray(v)) {
    const any = writeValue(acc, v, 0);
    if (!any || !acc.text.trim()) return EMPTY;
    return { kind: "text", text: acc.text, truncated: acc.over, fullLength: acc.total };
  }
  if (typeof v === "object") {
    // A bare tool_result / functionResponse block reads better as its inner text.
    if (isObj(v) && (v.type === "tool_result" || isObj(v.functionResponse) || (typeof v.type === "string" && typeof v.text === "string"))) {
      writeBlock(acc, v, 0);
      return acc.text.trim() ? { kind: "text", text: acc.text, truncated: acc.over, fullLength: acc.total } : EMPTY;
    }
    writeJson(acc, v, "", 0);
    return { kind: "json", text: acc.text, truncated: acc.over, fullLength: acc.total };
  }
  return { kind: "text", text: String(v), truncated: false, fullLength: String(v).length };
}


/** Read only saved reasoning text/summary fields, with the same bounded walk as payloads. */
export function formatReasoningContent(value: unknown, cap = CONTENT_CAP): FormattedContent {
  const acc = new Acc(cap);
  function visit(part: unknown, depth: number) {
    if (acc.over || depth > MAX_DEPTH || part == null) return;
    if (typeof part === "string") {
      if (!part.trim() || /^gAAAAA[\w-]{40,}/.test(part)) return;
      if (acc.len) acc.add("\n\n");
      acc.add(part);
    } else if (Array.isArray(part)) {
      for (const item of part) { visit(item, depth + 1); if (acc.over) break; }
    } else if (isObj(part) && part.type !== "redacted_thinking") {
      visit(part.text ?? part.thinking ?? part.summary ?? part.content ?? part.value, depth + 1);
    }
  }
  visit(value, 0);
  return acc.len ? { kind: "text", text: acc.text, truncated: acc.over, fullLength: acc.total } : EMPTY;
}
