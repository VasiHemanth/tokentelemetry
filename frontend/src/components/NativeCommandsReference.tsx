"use client";

import { getAgent, ALL_AGENT_KEYS } from "@/lib/agents";
import { Section, Card } from "@/components/ui";

// What each agent's OWN in-session command shows, from researching each agent's
// docs/source. TokenTelemetry sources the tokens/cost/cache above from local
// session files regardless of whether the agent ships a command at all — this
// block is the orientation map: where the *live* figure lives per agent.
type Confidence = "confirmed" | "partial" | "none";

const NATIVE_COMMAND: Record<string, { command: string; confidence: Confidence }> = {
  claude:      { command: "/usage, /cost, /context", confidence: "confirmed" },
  codex:       { command: "/status, /usage", confidence: "confirmed" },
  gemini:      { command: "/stats (alias /usage)", confidence: "confirmed" },
  antigravity: { command: "/context, /credits (docs conflict)", confidence: "partial" },
  // Qwen commands verified against QwenLM/qwen-code source + tested on v0.19.6
  // (thanks @Pauliehedron): /stats has altNames ['usage']; /context, /summary,
  // /recap, /statusline, /export are all native too.
  qwen:        { command: "/stats (alias /usage), /context, /summary", confidence: "confirmed" },
  vibe:        { command: "no /status — --max-tokens / --max-price flags only", confidence: "partial" },
  cursor:      { command: "Settings → Usage only, no CLI command", confidence: "none" },
  copilot:     { command: "/usage (CLI, session-scoped only)", confidence: "confirmed" },
  opencode:    { command: "opencode stats (shell, not in-TUI)", confidence: "partial" },
  hermes:      { command: "hermes insights (fields undocumented)", confidence: "partial" },
  grok:        { command: "no command — xAI Console only", confidence: "none" },
  cline:       { command: "task header, live — no slash command", confidence: "partial" },
  smallcode:   { command: "/stats, /tokens, /budget", confidence: "confirmed" },
};

// Session-limit & reset model per agent, from researching each provider's docs
// (July 2026). Deliberately qualitative — the exact hourly/weekly numbers churn,
// and TokenTelemetry can't see your *live remaining* quota (that lives on the
// provider's servers; the agent's own command queries it). What's durable is
// the SHAPE of the limit, when it resets, and where the live figure comes from.
interface LimitInfo { model: string; reset: string; note: string }
const LIMIT_INFO: Record<string, LimitInfo> = {
  claude: {
    model: "5h session + weekly cap",
    reset: "5h after 1st prompt · weekly",
    note: "Live % via /usage; quota is shared with claude.ai and all your devices. TT counts your local tokens only.",
  },
  codex: {
    model: "5h window + weekly cap",
    reset: "rolling 5h · weekly",
    note: "Live limits via /status (counted in messages, not tokens, and shown as % remaining).",
  },
  gemini: {
    model: "Daily request cap",
    reset: "daily",
    note: "Free tier ~1k req/day, 60 rpm. /stats shows session tokens; /model shows the quota.",
  },
  qwen: {
    model: "Daily request cap",
    reset: "daily",
    note: "Native /context, /statusline, /summary, /recap, /export (tested v0.19.6). Sessions logged to ~/.qwen/…/chats/*.jsonl.",
  },
  antigravity: {
    model: "Model credits",
    reset: "periodic (docs vary)",
    note: "/credits and /context; reset cadence isn't clearly documented.",
  },
  copilot: {
    model: "Monthly credits",
    reset: "1st of month, 00:00 UTC",
    note: "Premium-request / AI-credit allotment. The CLI /usage is session-scoped only; monthly quota lives on the GitHub dashboard.",
  },
  cursor: {
    model: "Monthly usage credits",
    reset: "your billing date",
    note: "No CLI command — Settings → Usage. The $-credit pool resets each cycle.",
  },
  vibe: {
    model: "API rate limits",
    reset: "n/a — bound to API key",
    note: "No live usage command; cap a run with --max-tokens / --max-price. Limited by your provider key.",
  },
  opencode: {
    model: "API rate limits",
    reset: "n/a — bound to API key",
    note: "`opencode stats` is a shell cmd, not in-TUI. Bounded by your API key.",
  },
  hermes: {
    model: "API rate limits",
    reset: "n/a — bound to API key",
    note: "`hermes insights --days N` (shell). Bounded by the underlying API key's limits.",
  },
  grok: {
    model: "API rate limits",
    reset: "n/a — bound to API key",
    note: "No in-session command; usage lives in the xAI Console. Bounded by your xAI key.",
  },
  cline: {
    model: "API rate limits",
    reset: "no window — per API call",
    note: "Live token count sits in the task header; you pay per request, no reset.",
  },
  smallcode: {
    model: "Per-session token budget",
    reset: "per session",
    note: "/budget and /tokens show a session budget, not a provider reset window.",
  },
};
const LIMIT_FALLBACK: LimitInfo = {
  model: "API rate limits",
  reset: "n/a — bound to API key",
  note: "Bounded by the underlying provider key's rate limits.",
};

const CONFIDENCE_STYLE: Record<Confidence, string> = {
  confirmed: "text-[var(--tt-success-fg)] bg-[var(--tt-success-fg)]/10",
  partial: "text-[var(--tt-warn-fg,#b45309)] bg-[var(--tt-warn-fg,#b45309)]/10",
  none: "text-[var(--tt-fg-dim)] bg-[var(--tt-fg-dim)]/10",
};
const CONFIDENCE_LABEL: Record<Confidence, string> = {
  confirmed: "Has native cmd",
  partial: "Docs disagree",
  none: "No native cmd",
};

function AgentRefCard({ agent }: { agent: string }) {
  const meta = getAgent(agent);
  const Icon = meta.icon;
  const native = NATIVE_COMMAND[agent];
  const limit = LIMIT_INFO[agent] ?? LIMIT_FALLBACK;
  return (
    <Card padding="sm" className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 min-w-0">
          <span
            className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md"
            style={{ background: `${meta.hex}1a`, color: meta.hex }}
          >
            <Icon size={13} />
          </span>
          <span className="truncate text-[12px] font-semibold text-[var(--tt-fg)]">{meta.label}</span>
        </span>
        {native && (
          <span className={`shrink-0 rounded px-1.5 py-0.5 text-[9.5px] font-medium whitespace-nowrap ${CONFIDENCE_STYLE[native.confidence]}`}>
            {CONFIDENCE_LABEL[native.confidence]}
          </span>
        )}
      </div>
      {native && (
        <code className="block truncate text-[11px] text-[var(--tt-fg-muted)]" title={native.command}>
          {native.command}
        </code>
      )}
      <div className="mt-auto space-y-1 border-t border-[var(--tt-border)] pt-2">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-[9.5px] uppercase tracking-[0.14em] text-[var(--tt-fg-dim)] shrink-0">Limit</span>
          <span className="text-[11px] text-[var(--tt-fg-muted)] text-right">{limit.model}</span>
        </div>
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-[9.5px] uppercase tracking-[0.14em] text-[var(--tt-fg-dim)] shrink-0">Resets</span>
          <span className="text-[11px] text-[var(--tt-fg-muted)] text-right">{limit.reset}</span>
        </div>
        <p className="text-[10px] leading-snug text-[var(--tt-fg-dim)]">{limit.note}</p>
      </div>
    </Card>
  );
}

/** Per-agent reference: each agent's own usage/stats command and its
 *  limit/reset model. The numbers above are TT's local re-count; this maps
 *  where the *live remaining* quota lives (behind each agent's own command). */
export function NativeCommandsReference() {
  return (
    <Section
      title="Native commands & limits"
      description="Where each agent's own live usage figure lives. TokenTelemetry re-counts your local tokens; the live remaining quota and exact reset countdown sit on each provider's servers — only that agent's own command reads them."
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {ALL_AGENT_KEYS.map((a) => <AgentRefCard key={a} agent={a} />)}
      </div>
    </Section>
  );
}
