import assert from "node:assert/strict";
import { test } from "node:test";

// Node needs the runtime `.ts` suffix while the app compiler resolves the
// extensionless type import. A URL keeps both contracts explicit.
const layoutModuleUrl = new URL("./agentSwimlaneLayout.ts", import.meta.url);
const {
  buildAgentSwimlaneLayout,
  formatSwimlaneDuration,
} = await import(layoutModuleUrl.href) as typeof import("./agentSwimlaneLayout");

test("aligns agents with absolute timestamps on one shared time domain", () => {
  const entries = [
    {
      agent_id: "research",
      description: "Research the API",
      started_at: "2026-08-13T10:00:00Z",
      completed_at: "2026-08-13T10:00:10Z",
    },
    {
      agent_id: "implementation",
      description: "Implement the API",
      started_at: "2026-08-13T10:00:05Z",
      completed_at: "2026-08-13T10:00:20Z",
    },
  ];

  const layout = buildAgentSwimlaneLayout(entries);

  assert.equal(layout.mode, "absolute");
  assert.equal(layout.durationMs, 20_000);
  assert.deepEqual(
    layout.lanes.map(({ leftPct, widthPct, timing }) => ({ leftPct, widthPct, timing })),
    [
      { leftPct: 0, widthPct: 50, timing: "absolute" },
      { leftPct: 25, widthPct: 75, timing: "absolute" },
    ],
  );
});

test("derives an absolute window from a start time and duration", () => {
  const layout = buildAgentSwimlaneLayout([
    {
      agent_id: "agent-a",
      started_at: 1_723_546_800,
      duration_ms: 12_000,
    },
  ]);

  assert.equal(layout.mode, "absolute");
  assert.equal(layout.lanes[0].startMs, 1_723_546_800_000);
  assert.equal(layout.lanes[0].durationMs, 12_000);
  assert.equal(layout.lanes[0].widthPct, 100);
});

test("uses duration-only entries as relative lanes without inventing start times", () => {
  const layout = buildAgentSwimlaneLayout([
    { agent_id: "quick", duration_ms: 5_000 },
    { agent_id: "slow", duration_ms: 20_000 },
  ]);

  assert.equal(layout.mode, "relative");
  assert.deepEqual(
    layout.lanes.map(({ leftPct, widthPct, timing }) => ({ leftPct, widthPct, timing })),
    [
      { leftPct: 0, widthPct: 25, timing: "relative" },
      { leftPct: 0, widthPct: 100, timing: "relative" },
    ],
  );
});

test("keeps relative lanes relative when mixed with timestamped entries", () => {
  const layout = buildAgentSwimlaneLayout([
    {
      agent_id: "timestamped",
      started_at: "2026-08-13T10:00:00Z",
      completed_at: "2026-08-13T10:00:10Z",
    },
    { agent_id: "duration-only", duration_ms: 5_000 },
  ]);

  assert.equal(layout.mode, "mixed");
  assert.equal(layout.lanes[1].timing, "relative");
  assert.equal(layout.lanes[1].leftPct, 0);
  assert.equal(layout.lanes[1].widthPct, 50);
});

test("marks entries without usable timing as unknown", () => {
  const source = { child_session_id: "child-1", nickname: "Luna" };
  const layout = buildAgentSwimlaneLayout([source]);

  assert.equal(layout.mode, "unknown");
  assert.equal(layout.lanes[0].id, "child-1");
  assert.equal(layout.lanes[0].label, "Luna");
  assert.equal(layout.lanes[0].timing, "unknown");
  assert.equal(layout.lanes[0].entry, source);
});

test("returns every lane for large delegations so the view can cap and scroll", () => {
  const entries = Array.from({ length: 63 }, (_, index) => ({
    agent_id: `agent-${index}`,
    duration_ms: (index + 1) * 1_000,
  }));

  const layout = buildAgentSwimlaneLayout(entries);

  assert.equal(layout.lanes.length, 63);
  assert.equal(layout.durationMs, 63_000);
  assert.equal(layout.lanes.at(-1)?.widthPct, 100);
});

test("formats compact, accessible elapsed labels", () => {
  assert.equal(formatSwimlaneDuration(0), "0s");
  assert.equal(formatSwimlaneDuration(12_450), "12.5s");
  assert.equal(formatSwimlaneDuration(125_000), "2m 5s");
  assert.equal(formatSwimlaneDuration(7_205_000), "2h 5s");
});
