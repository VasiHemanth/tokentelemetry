/**
 * Prime trace -> span tree. Tool calls and results carry no ids, so each result
 * closes the oldest unpaired call of the same tool name. No token counts, no
 * error flag, no subagents.
 */
import type { TraceValue } from "../../traceEvents";
import type { HarnessAdapter } from "../index";
import { buildGroupedTrace } from "./groupedTrace";
import { toolLabel } from "./simpleLabels";

function describe(payload: TraceValue): { title: string; label?: string } {
  return { title: String(payload.tool ?? "tool"), label: toolLabel(payload.args) };
}

export const primeAdapter: HarnessAdapter = {
  timing: "real",
  build: (events) =>
    buildGroupedTrace(events, { pair: "toolName", isNotification: () => false, describe, isError: () => false }),
};
