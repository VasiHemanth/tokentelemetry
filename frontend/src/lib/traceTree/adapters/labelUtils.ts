/**
 * Small text helpers shared by the codex, gemini and qwen adapters. Tool args
 * can hold raw shell commands, prompts and file contents, so labels are built
 * from a short whitelist of descriptive fields and never from the command.
 */
import type { TraceValue } from "../../traceEvents";

export const LABEL_MAX = 120;

export function collapse(text: unknown, max = LABEL_MAX): string {
  const s = String(text ?? "").replace(/\s+/g, " ").trim();
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

export function baseName(path: unknown): string {
  const s = String(path ?? "").replace(/^file:\/\//, "").replace(/[\\/]+$/, "");
  return s.split(/[\\/]/).pop() || "";
}

export function hostName(url: unknown): string {
  try {
    return new URL(String(url)).hostname;
  } catch {
    return "";
  }
}

const PATH_KEYS = ["file_path", "absolute_path", "path", "dir_path", "directory", "filename"];

/** description, else file basename, else query/pattern, else url host. Never a command. */
export function toolLabel(args: TraceValue): string {
  if (!args || typeof args !== "object") return "";
  for (const key of ["description", "instruction"]) {
    if (typeof args[key] === "string" && args[key].trim()) return collapse(args[key]);
  }
  for (const key of PATH_KEYS) {
    if (typeof args[key] === "string" && args[key]) return collapse(baseName(args[key]));
  }
  for (const key of ["query", "pattern", "q"]) {
    if (typeof args[key] === "string" && args[key].trim()) return collapse(args[key]);
  }
  if (typeof args.url === "string") return collapse(hostName(args.url) || args.url);
  if (Array.isArray(args.todos)) return `${args.todos.length} todos`;
  return "";
}

/** Epoch ms for a normalized event or ISO string, or undefined. */
export function eventMs(e: TraceValue): number | undefined {
  if (typeof e?.normalized_timestamp === "number") return e.normalized_timestamp;
  const t = Date.parse(e?.timestamp ?? e);
  return Number.isNaN(t) ? undefined : t;
}

/** Text of a message body that is a string or an array of {text} parts. */
export function partsText(content: TraceValue): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .map((p: TraceValue) => (typeof p === "string" ? p : p && !p.thought && typeof p.text === "string" ? p.text : ""))
    .filter(Boolean)
    .join(" ");
}
