export type Feature = {
  id: string;
  label: string;
  headline: string;
  bullets: string[];
  screenshot: string; // /screenshots/<id>.png
};

export const FEATURES: Feature[] = [
  {
    id: "hermes",
    label: "Hermes Agent",
    headline: "Autonomous agent observability — a different class of agent, its own surface.",
    bullets: [
      "Dedicated /hermes dashboard: gateway health, scheduled-job status, source breakdown across 38 platforms (CLI / Telegram / Discord / Slack / Feishu / DingTalk / cron / webhook / …).",
      "Per-API-call latency and cache-hit % parsed from agent.log — none of the other agents emit this.",
      "Subagent delegation rendered inline: each delegate_task call expands to show the child's summary, tokens, duration, and tool trace.",
      "Skills + memory pages: 90 loaded skills with platform conditions, MEMORY.md / USER.md with char-limit progress bars.",
      "Cost anomaly detection: silent reasoning-token waste (MiMo thinking-mode) flagged automatically.",
      "Hermes Dashboard plugin: one-command install adds a TokenTelemetry tab inside Hermes's own web UI (port 9119) — deep-link launcher to Overview, Skills, Memory, Analytics, Projects.",
    ],
    screenshot: "/screenshots/hermes.png",
  },
  {
    id: "dashboard",
    label: "Dashboard",
    headline: "A bird's-eye view of your entire agent fleet.",
    bullets: [
      "Real-time monitoring of active traces across all detected tools.",
      "High-level metrics for total sessions, token burn, and cost estimates.",
      "Agent distribution and model usage leaderboards, updated live.",
    ],
    screenshot: "/screenshots/dashboard.png",
  },
  {
    id: "traces",
    label: "Traces",
    headline: "Every prompt, tool call, and reasoning block — replayable.",
    bullets: [
      "Step-by-step playback with kind-aware highlighting (reasoning amber, tools sky, response emerald).",
      "Tool calls paired with their results and timing, surfaced as a waterfall.",
      "Encrypted reasoning (Claude extended thinking) labeled honestly — no fake content.",
    ],
    screenshot: "/screenshots/traces.png",
  },
  {
    id: "analytics",
    label: "Analytics",
    headline: "Tokens by agent, by model, by day.",
    bullets: [
      "Stacked daily area chart shows where your budget is actually going.",
      "Model leaderboard ranked by usage, cost, and cache hit rate.",
      "All math runs locally — your analytics data never leaves your machine.",
    ],
    screenshot: "/screenshots/analytics.png",
  },
  {
    id: "projects",
    label: "Projects",
    headline: "One card per working directory.",
    bullets: [
      "Aliases collapse renamed folders into one project.",
      "Per-project plans library — every plan-mode output, searchable.",
      "Configuration tab: MCP servers, subagents, skills, slash commands.",
    ],
    screenshot: "/screenshots/projects.png",
  },
  {
    id: "artifacts",
    label: "Artifacts",
    headline: "Screenshots, browser recordings, generated docs.",
    bullets: [
      "Antigravity browser_recordings sampled into thumbnail strips.",
      "Inline image and video viewer — no copy-paste to find a screenshot.",
      "Document artifacts (task.md, plan.md, walkthrough.md) viewable in-browser.",
    ],
    screenshot: "/screenshots/artifacts.png",
  },
];
