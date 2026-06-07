export const FAQ_ITEMS = [
  {
    q: "What is Token Telemetry?",
    a: "Token Telemetry (also written TokenTelemetry, sometimes misspelled as 'token telementry' or 'tokentelementry') is a free, open-source, 100% local observability dashboard for AI coding agents like Claude Code, Codex, Gemini CLI, Cursor, and GitHub Copilot. It tracks tokens, cost, tool calls, and reasoning by reading the log files those agents already write — no SDK, no signup, no cloud.",
  },
  {
    q: "How do I track Claude Code token usage?",
    a: "Install TokenTelemetry, run Claude Code normally, and open http://localhost:3000. TokenTelemetry auto-detects Claude Code sessions from ~/.claude/ logs — no instrumentation, no SDK, no config.",
  },
  {
    q: "How do I monitor Gemini CLI and Codex costs?",
    a: "TokenTelemetry auto-reads logs from Gemini CLI, OpenAI Codex CLI, Cursor, GitHub Copilot, Qwen CLI, OpenCode, Vibe, Antigravity, and Grok Build (xAI). Token counts and dollar costs appear in the local dashboard automatically.",
  },
  {
    q: "Is there a free tool to monitor AI coding agent token usage?",
    a: "Yes — TokenTelemetry is free, open-source (MIT), and runs 100% locally. No account, no signup, no cloud.",
  },
  {
    q: "Does TokenTelemetry send my data to the cloud?",
    a: "No usage data, ever. The dashboard reads session log files from your local filesystem and serves a UI on localhost — your logs, sessions, tokens, and costs never leave your computer. The only outbound call is an optional update check that fetches the latest version and release notes from GitHub (no usage data sent); turn it off in Settings → Updates & privacy, or with TT_NO_UPDATE_CHECK=1.",
  },
  {
    q: "How does TokenTelemetry compare to Langfuse or Helicone?",
    a: "TokenTelemetry is purpose-built for AI coding agents and is zero-config — no SDK instrumentation. Langfuse and Helicone are general LLM-app observability platforms that require code changes and (typically) a cloud account.",
  },
  {
    q: "Which agents does it support?",
    a: "Ten coding agents (Claude Code, OpenAI Codex, Gemini CLI, Cursor, GitHub Copilot, Qwen CLI, OpenCode, Vibe, Antigravity, Grok Build) plus Hermes Agent — Nous Research's autonomous agent, which gets its own dedicated dashboard at /hermes with gateway health, scheduled-job monitoring, skills + memory observability, and 38 source platforms (CLI / Telegram / Discord / Feishu / DingTalk / cron / webhook / …).",
  },
  {
    q: "Why does Hermes Agent get its own page?",
    a: "Hermes is structurally different from coding agents — it runs across messaging platforms (Telegram / Discord / Slack / WhatsApp / Signal / Matrix / Feishu / DingTalk / WeChat), supports persistent skills and memory, delegates to subagents, and runs scheduled cron jobs. Forcing it into the same UI as Claude Code would hide most of what it does, so it gets a dedicated surface that respects its shape.",
  },
  {
    q: "Can I use TokenTelemetry from inside Hermes Dashboard?",
    a: "Yes — there's a Hermes Dashboard plugin that registers a 'TokenTelemetry' tab inside Hermes's web UI at port 9119. It's a thin launcher: deep-link cards open the relevant TokenTelemetry page (Hermes Overview, Skills, Memory, Analytics, Projects) in a new browser tab, so you don't have to remember a second port. Install with `./scripts/install-hermes-plugin.sh` from the TokenTelemetry repo, then run `hermes dashboard`.",
  },
];

export default function FAQ() {
  return (
    <section id="faq" className="border-t border-[var(--tt-border)]">
      <div className="max-w-3xl mx-auto px-5 sm:px-8 py-14 sm:py-28">
        <div className="text-center mb-8 sm:mb-10">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--tt-fg-dim)] mb-3">FAQ</p>
          <h2 className="text-[26px] sm:text-[38px] leading-[1.1] tracking-[-0.02em] font-semibold text-[var(--tt-fg)]">
            Common questions
          </h2>
        </div>
        <div className="space-y-2">
          {FAQ_ITEMS.map((item, i) => (
            <details
              key={i}
              className="group rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)] open:bg-[var(--tt-raised)] transition-colors"
            >
              <summary className="flex items-center justify-between cursor-pointer list-none gap-4 px-5 py-4">
                <h3 className="text-[var(--tt-fg)] font-medium text-[15px] sm:text-[16px] tracking-[-0.005em]">
                  {item.q}
                </h3>
                <span className="text-[var(--tt-fg-dim)] text-xl leading-none transition-transform group-open:rotate-45 select-none">
                  +
                </span>
              </summary>
              <p className="px-5 pb-5 -mt-1 text-[13.5px] text-[var(--tt-fg-muted)] leading-relaxed">
                {item.a}
              </p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}
