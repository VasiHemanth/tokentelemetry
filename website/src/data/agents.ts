export type Agent = {
  name: string;
  vendor: string;
  captures: string[];
  logPath: string;
  /** Hex color used for chip + accent — matches the app's agent registry. */
  hex: string;
};

export const AGENTS: Agent[] = [
  { name: "Claude Code",    vendor: "Anthropic", captures: ["tokens", "traces", "reasoning", "cost", "subagents"], logPath: "~/.claude/projects/",            hex: "#f97316" },
  { name: "Codex",          vendor: "OpenAI",    captures: ["tokens", "traces", "reasoning", "cost"],              logPath: "~/.codex/sessions/",              hex: "#a855f7" },
  { name: "Gemini CLI",     vendor: "Google",    captures: ["tokens", "traces", "cost"],                           logPath: "~/.gemini/",                      hex: "#06b6d4" },
  { name: "Antigravity",    vendor: "Google",    captures: ["traces", "artifacts", "screenshots", "browser recs"], logPath: "~/.gemini/antigravity/",          hex: "#10b981" },
  { name: "Qwen CLI",       vendor: "Alibaba",   captures: ["tokens", "traces"],                                   logPath: "~/.qwen/",                        hex: "#3b82f6" },
  { name: "Vibe",           vendor: "Local",     captures: ["tokens", "traces", "model"],                          logPath: "~/.vibe/",                        hex: "#f472b6" },
  { name: "Cursor",         vendor: "Cursor",    captures: ["tokens", "traces", "plans"],                          logPath: "~/.cursor/ + workspaceStorage/",  hex: "#60a5fa" },
  { name: "GitHub Copilot", vendor: "GitHub",    captures: ["tokens", "traces", "cost"],                           logPath: "VS Code chatSessions/",           hex: "#6366f1" },
  { name: "OpenCode",       vendor: "OpenCode",  captures: ["tokens", "traces"],                                   logPath: "~/.local/share/opencode/",        hex: "#f59e0b" },
  { name: "Grok Build",     vendor: "xAI",       captures: ["tokens", "traces", "reasoning", "cost"],              logPath: "~/.grok/sessions/",               hex: "#d4d4d8" },
  { name: "Cline",          vendor: "Cline (open source)", captures: ["tokens", "traces", "cost", "model", "provider"], logPath: "~/.cline/ + VS Code taskHistory", hex: "#7c3aed" },
  { name: "SmallCode",      vendor: "SmallCode (open source)", captures: ["tokens", "traces", "model", "tool steps"], logPath: "<project>/.smallcode/traces/",    hex: "#0d9488" },
  { name: "Pi",             vendor: "Earendil Works", captures: ["tokens", "traces", "reasoning", "cost", "model"], logPath: "~/.pi/agent/sessions/",           hex: "#fafafa" },
  { name: "Hermes Agent",   vendor: "Nous Research", captures: ["tokens", "traces", "cost", "subagents", "skills", "memory", "cron", "38 sources"], logPath: "~/.hermes/",                      hex: "#eab308" },
];
