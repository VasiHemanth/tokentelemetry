/**
 * Prime trace -> span tree. Pair calls by id, falling back to tool name for older recordings.
 */
import type { TraceValue } from "../../traceEvents";
import type { HarnessAdapter } from "../index";
import { buildGroupedTrace } from "./groupedTrace";
import { toolLabel } from "./simpleLabels";

function describe(payload: TraceValue): { title: string; label?: string; input?: unknown } {
  return { title: String(payload.tool ?? "tool"), label: toolLabel(payload.args), input: payload.args };
}

export const primeAdapter: HarnessAdapter = {
  timing: "real",
  build: (events) =>
    buildGroupedTrace(events, {
      pair: "callIdOrName", isNotification: () => false, describe,
      isError: (_content, payload) => payload.is_error === true,
      tokens: (usage) => ({ input: Number(usage.input) || 0, output: Number(usage.output) || 0,
        cacheRead: Number(usage.cacheRead) || 0, cacheWrite: Number(usage.cacheWrite) || 0 }),
    }),
};
