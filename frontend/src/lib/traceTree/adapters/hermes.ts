/**
 * Hermes trace -> span tree. Calls and results are separate events paired by
 * callID. MCP calls come wrapped as tool "tool_call" with the real tool name in
 * args.name. There is no error flag, so a result whose content is a JSON object
 * with an "error" key counts as one. Hermes has no subagent spans: the delegation
 * child ids are compaction continuations that replay the parent, so nothing nests.
 */
import type { TraceValue } from "../../traceEvents";
import type { HarnessAdapter } from "../index";
import { buildGroupedTrace } from "./groupedTrace";
import { clip, toolLabel } from "./simpleLabels";

const INJECTED = /^\[(ASYNC DELEGATION COMPLETE|CONTEXT COMPACTION|Note: model was just switched|System:)/;

function describe(payload: TraceValue): { title: string; label?: string } {
  const tool = String(payload.tool ?? "tool");
  const args = payload.args ?? {};
  if (tool === "tool_call" && typeof args.name === "string") {
    return { title: args.name, label: toolLabel(args.arguments) };
  }
  const label = toolLabel(args) ?? (typeof args.name === "string" ? clip(args.name) : undefined);
  return { title: tool, label };
}

function isError(content: unknown): boolean {
  if (typeof content !== "string" || !content.startsWith("{")) return false;
  try {
    const parsed = JSON.parse(content);
    // Successful results often carry `"error": null`, so only a real value counts.
    return !!parsed && typeof parsed === "object" && !Array.isArray(parsed) && parsed.error != null && parsed.error !== "";
  } catch {
    return false;
  }
}

export const hermesAdapter: HarnessAdapter = {
  timing: "real",
  build: (events) =>
    buildGroupedTrace(events, { pair: "callId", isNotification: (text) => INJECTED.test(text), describe, isError }),
};
