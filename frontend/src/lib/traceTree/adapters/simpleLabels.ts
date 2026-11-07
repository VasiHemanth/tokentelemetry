/**
 * Small helpers shared by the opencode, hermes and prime adapters: event
 * timestamps and the short, never-a-shell-command labels shown on spans.
 */
import type { Event, TraceValue } from "../../traceEvents";
import type { SpanContent } from "../types";

export function clip(text: unknown, max = 120): string {
  const flat = String(text ?? "").replace(/\s+/g, " ").trim();
  return flat.length > max ? `${flat.slice(0, max - 1)}…` : flat;
}

/** Join step texts; a single part is returned as is, nothing yields undefined. */
export function joinText(parts: string[]): string | undefined {
  const kept = parts.filter(Boolean);
  return kept.length ? (kept.length === 1 ? kept[0] : kept.join("\n\n")) : undefined;
}

/** SpanContent with only the fields that are set, or undefined when none are. */
export function contentOf(input?: unknown, output?: unknown, reasoning?: unknown): SpanContent | undefined {
  const content: SpanContent = {};
  if (input !== undefined && input !== null && input !== "") content.input = input;
  if (reasoning !== undefined && reasoning !== null && reasoning !== "") content.reasoning = reasoning;
  if (output !== undefined && output !== null && output !== "") content.output = output;
  return Object.keys(content).length ? content : undefined;
}

export function eventTime(event: Event): number | undefined {
  if (typeof event.normalized_timestamp === "number") return event.normalized_timestamp;
  const raw: unknown = event.payload?.timestamp ?? event.timestamp;
  if (typeof raw === "number") return raw;
  if (typeof raw === "string") {
    const parsed = Date.parse(raw);
    return Number.isNaN(parsed) ? undefined : parsed;
  }
  return undefined;
}

export function basename(path: string): string {
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] || path;
}

function hostname(url: string): string | undefined {
  try {
    return new URL(url).hostname || undefined;
  } catch {
    return undefined;
  }
}

const first = (input: TraceValue, keys: string[]): string | undefined => {
  for (const key of keys) {
    const value = input?.[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return undefined;
};

/** Description/title, else file basename, else query/pattern, else url host. Shell commands are never used. */
export function toolLabel(input: TraceValue): string | undefined {
  if (!input || typeof input !== "object") return undefined;
  const described = first(input, ["description", "title"]);
  if (described) return clip(described);
  const path = first(input, ["filePath", "file_path", "path", "file", "filename"]);
  if (path) return clip(basename(path));
  const query = first(input, ["query", "pattern", "q", "search"]);
  if (query) return clip(query);
  const url = first(input, ["url", "uri"]);
  if (url) return hostname(url) ?? clip(url);
  return undefined;
}
