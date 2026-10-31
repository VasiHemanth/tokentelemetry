export type WorkspaceView = "conversation" | "execution" | "events";

/** Fixed-height execution rows keep DOM work proportional to viewport size. */
export function windowRows(count: number, scroll: number, height: number, rowHeight: number, overscan = 8) {
  if (!count) return { start: 0, end: 0 };
  const visible = Math.max(1, Math.ceil(height / rowHeight));
  const first = Math.min(Math.max(0, Math.floor(scroll / rowHeight)), Math.max(0, count - visible));
  return { start: Math.max(0, first - overscan), end: Math.min(count, first + visible + overscan) };
}

export function readWorkspaceLocation(params: Pick<URLSearchParams, "get">): { view: WorkspaceView; span: string | null } {
  const view = params.get("view");
  return {
    view: view === "execution" || view === "events" ? view : "conversation",
    span: params.get("span")?.slice(0, 1024) || null,
  };
}

export function updateWorkspaceLocation(params: { toString(): string }, patch: { view?: WorkspaceView; span?: string | null }): URLSearchParams {
  const next = new URLSearchParams(params.toString());
  if (patch.view !== undefined) next.set("view", patch.view);
  if (patch.span === null) next.delete("span");
  else if (patch.span !== undefined) next.set("span", patch.span);
  return next;
}
