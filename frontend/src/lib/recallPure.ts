// Pure helpers for the Recall UI. No imports, so node tests can load this file.

const normPath = (v: string) => v.replace(/\\/g, "/").replace(/\/+$/, "");

/** The indexed project a path or key refers to: exact key first, else the longest parent. */
export function resolveRecallProject<P extends { key: string }>(projects: P[], wanted: string): P | null {
  const w = normPath(wanted);
  const exact = projects.find((p) => normPath(p.key) === w);
  if (exact) return exact;
  return projects
    .filter((p) => w.startsWith(normPath(p.key) + "/"))
    .sort((a, b) => b.key.length - a.key.length)[0] ?? null;
}

/** True when a backend project key is the project the caller means (canonical key or raw path). */
export function sameRecallProject(backendKey: string | null | undefined, canonicalKey: string, rawProject: string): boolean {
  if (!backendKey) return false;
  const k = normPath(backendKey);
  return k === normPath(canonicalKey) || k === normPath(rawProject);
}

/** Ready-line sentence for the semantic settings, by provider. */
export function embeddedWithText(s: {
  provider?: string; model?: string; api?: { model?: string } | null; ollama?: { model?: string } | null;
}): string {
  if (s.provider === "api") return `Embedded through the embedding API with ${s.api?.model ?? s.model ?? "the configured model"}`;
  return `Embedded locally with ${s.ollama?.model ?? s.model ?? "the configured model"}`;
}
