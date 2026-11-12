"use client";

import { useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { artifactUrl } from "@/lib/api";

const IMAGE_RE = /\.(png|jpe?g|gif|webp|bmp)$/i;
const PATH_KEYS = ["file_path", "filePath", "path", "absolute_path", "AbsolutePath", "Path", "target_file", "TargetFile", "filename", "file"];

export function isImagePath(path: string | null | undefined): path is string {
  return typeof path === "string" && IMAGE_RE.test(path);
}

/** The image path a tool call was pointed at, if its input names one. */
export function imagePathOf(input: unknown): string | null {
  let v = input;
  if (typeof v === "string") {
    const t = v.trim();
    if (!t.startsWith("{")) return isImagePath(t) && !t.includes("\n") ? t : null;
    try { v = JSON.parse(t); } catch { return null; }
  }
  if (!v || typeof v !== "object") return null;
  for (const k of PATH_KEYS) {
    const c = (v as Record<string, unknown>)[k];
    if (typeof c === "string" && isImagePath(c.trim())) return c.trim();
  }
  return null;
}

interface Props {
  path: string;
  /** Defaults to the session in the current route. */
  sessionId?: string;
  agent?: string;
  variant?: "thumb" | "preview";
}

/**
 * An image the session read, served from disk if it still exists. Loaded
 * lazily, so nothing is fetched until it scrolls into view. Renders nothing
 * when the file is gone or was never an image the session read.
 */
export default function ReadImage({ path, sessionId, agent, variant = "preview" }: Props) {
  const params = useParams();
  const search = useSearchParams();
  const [state, setState] = useState<"loading" | "ok" | "gone">("loading");
  const id = sessionId ?? (typeof params?.id === "string" ? params.id : "");
  const ag = agent ?? search.get("agent") ?? "";
  if (!id || !ag || !isImagePath(path)) return null;

  const src = artifactUrl(`/sessions/${encodeURIComponent(id)}/read-image?agent=${encodeURIComponent(ag)}&path=${encodeURIComponent(path)}`);
  const name = path.replace(/\\/g, "/").split("/").pop() || path;

  if (state === "gone") {
    return variant === "thumb" ? null : (
      <div className="rounded border border-dashed border-[var(--tt-border)] px-3 py-2 text-[11px] text-[var(--tt-fg-faint)]">
        {name} is no longer on disk, so it cannot be shown.
      </div>
    );
  }

  const img = (
    // eslint-disable-next-line @next/next/no-img-element -- local file served by the backend, not a static asset
    <img
      src={src}
      alt={`Image the agent read: ${name}`}
      loading="lazy"
      decoding="async"
      onLoad={() => setState("ok")}
      onError={() => setState("gone")}
      className={variant === "thumb"
        ? "h-10 w-10 rounded border border-[var(--tt-border)] bg-[var(--tt-sunken)] object-cover"
        : "max-h-[320px] w-auto max-w-full rounded border border-[var(--tt-border)] bg-[var(--tt-sunken)] object-contain"}
    />
  );

  return (
    <a href={src} target="_blank" rel="noreferrer" title={`Open ${name} at full size`} className={variant === "thumb" ? "block shrink-0" : "block"}>
      {img}
      {variant === "preview" && state === "ok" && (
        <div className="mt-1 text-[11px] text-[var(--tt-fg-faint)]">The file as it is on disk now. It may have changed since the agent read it.</div>
      )}
    </a>
  );
}

const EMBED_TYPES = new Set(["image/png", "image/jpeg", "image/gif", "image/webp"]);

export interface EmbeddedImage { mediaType: string; data: string }

/**
 * Images recorded inside a tool result (Anthropic-style base64 image blocks).
 * These are already in the loaded trace, so showing one costs no extra fetch.
 */
export function embeddedImages(output: unknown, max = 4): EmbeddedImage[] {
  let v = output;
  if (typeof v === "string") {
    if (!v.includes("base64") || !v.includes("image")) return [];
    try { v = JSON.parse(v); } catch { return []; }
  }
  const out: EmbeddedImage[] = [];
  const visit = (x: unknown, depth: number) => {
    if (out.length >= max || depth > 3 || !x || typeof x !== "object") return;
    if (Array.isArray(x)) { for (const y of x) visit(y, depth + 1); return; }
    const o = x as Record<string, unknown>;
    const src = o.source as Record<string, unknown> | undefined;
    if (o.type === "image" && src && src.type === "base64" && typeof src.data === "string" && typeof src.media_type === "string" && EMBED_TYPES.has(src.media_type)) {
      out.push({ mediaType: src.media_type, data: src.data });
      return;
    }
    if (o.content !== undefined) visit(o.content, depth + 1);
  };
  visit(v, 0);
  return out;
}

/** The image exactly as the agent received it. Rendered only for the selected span. */
export function EmbeddedImages({ images, name }: { images: EmbeddedImage[]; name?: string }) {
  if (!images.length) return null;
  return (
    <div className="space-y-2">
      {images.map((im, i) => (
        // eslint-disable-next-line @next/next/no-img-element -- inline data from the recorded tool result
        <img
          key={i}
          src={`data:${im.mediaType};base64,${im.data}`}
          alt={`Image the agent received${name ? `: ${name}` : ""}`}
          decoding="async"
          className="max-h-[320px] w-auto max-w-full rounded border border-[var(--tt-border)] bg-[var(--tt-sunken)] object-contain"
        />
      ))}
      <div className="text-[11px] text-[var(--tt-fg-faint)]">Recorded in the session: this is the image the agent received.</div>
    </div>
  );
}
