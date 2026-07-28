export type ScriptLine = {
  delay: number;
  kind: "user" | "tool" | "reasoning" | "result" | "cost" | "header";
  text: string;
};

export const TERMINAL_SCRIPT: ScriptLine[] = [
  { delay: 0,    kind: "header",    text: "session:claude · model:claude-opus-4-7 · cwd:~/projects/api" },
  { delay: 350,  kind: "user",      text: "› refactor the auth middleware to use JWT" },
  { delay: 900,  kind: "reasoning", text: "thinking · scan auth/, find current strategy …" },
  { delay: 1500, kind: "tool",      text: "→ Read auth/middleware.py" },
  { delay: 1750, kind: "result",    text: "  204 lines · session-cookie based" },
  { delay: 2200, kind: "tool",      text: "→ Grep \"session_token\" --include=*.py" },
  { delay: 2500, kind: "result",    text: "  17 matches across 6 files" },
  { delay: 3000, kind: "reasoning", text: "thinking · plan migration · keep cookies as fallback …" },
  { delay: 3700, kind: "tool",      text: "→ Edit auth/middleware.py" },
  { delay: 4100, kind: "result",    text: "  +47 -12 · jwt.encode imported" },
  { delay: 4600, kind: "cost",      text: "tokens 12,440 · cached 8,210 · cost $0.18" },
  { delay: 5300, kind: "user",      text: "› perfect, write tests" },
];

export const SCRIPT_DURATION_MS = 7000;

/** Hold on the finished script before the replay loops. Loop length = SCRIPT_DURATION_MS + REPLAY_HOLD_MS. */
export const REPLAY_HOLD_MS = 1500;

/** When the cost line prints, relative to loop start. LiveTrace keys its metric count-ups off this. */
export const COST_LINE_DELAY_MS = TERMINAL_SCRIPT.find((l) => l.kind === "cost")!.delay;

/* ---- Hero boot sequence -------------------------------------------------- */

export type BootLine = {
  /** ms from boot start */
  delay: number;
  /**
   * Render prefixes belong to the consumer, keyed off `kind`:
   * command → "$ " prompt, text typed at BOOT_TYPE_MS_PER_CHAR with a block cursor;
   * found   → "✓ " check plus a leading dot (colored via `agentVar` when present);
   * url     → "→ " arrow.
   */
  kind: "command" | "found" | "url";
  text: string;
  /** Identity-color CSS var for the line's leading dot, e.g. "--agent-claude". Only on per-agent lines. */
  agentVar?: string;
};

/** Typing cadence for the hero's one typed command. */
export const BOOT_TYPE_MS_PER_CHAR = 28;

export const BOOT_SCRIPT: BootLine[] = [
  { delay: 0,    kind: "command", text: "tokentelemetry" },
  { delay: 450,  kind: "found",   text: "Claude Code · ~/.claude/projects · 218 sessions", agentVar: "--agent-claude" },
  { delay: 900,  kind: "found",   text: "Codex · ~/.codex/sessions · 96 sessions", agentVar: "--agent-codex" },
  { delay: 1350, kind: "found",   text: "11 more agents found" },
  { delay: 1750, kind: "found",   text: "13 agents · 510 sessions" },
  { delay: 2100, kind: "url",     text: "http://localhost:3000" },
];
