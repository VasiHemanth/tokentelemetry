// Coerce a reasoning/content value of unknown shape into a display string.
//
// Agent session payloads represent reasoning inconsistently. Codex Desktop can
// send it as a plain string, an array of `{ type, text }` summary objects, or a
// nested object. React crashes ("Objects are not valid as a React child") if any
// of these object shapes reaches JSX as a child directly, so every reasoning
// value must pass through here before it is rendered.
export function coerceReasoningText(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    return value.map((item) => coerceReasoningText(item)).filter(Boolean).join("\n\n");
  }
  if (typeof value === "object") {
    const o = value as Record<string, unknown>;
    return coerceReasoningText(o.text ?? o.thinking ?? o.summary ?? o.content ?? o.value ?? "");
  }
  return String(value);
}
