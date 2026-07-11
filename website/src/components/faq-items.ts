// FAQ data, kept in a plain (non-"use client") module so it can be imported by
// both the server layout (for FAQPage JSON-LD) and the client FAQ component
// (which tracks `faq_open`). A "use client" module's exports become client
// references on the server, so the data must live outside it.

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
    q: "How do I monitor Google Antigravity, Codex, and Gemini CLI costs?",
    a: "TokenTelemetry auto-reads logs from Google Antigravity (Google's agentic coding CLI), OpenAI Codex CLI, Gemini CLI, Cursor, GitHub Copilot, Qwen CLI, OpenCode, Vibe, Grok Build (xAI), and Pi (Earendil Works). Token counts and dollar costs appear in the local dashboard automatically.",
  },
  {
    q: "Is there a free tool to monitor AI coding agent token usage?",
    a: "Yes — TokenTelemetry is free, open-source (MIT), and runs 100% locally. No account, no signup, no cloud.",
  },
  {
    q: "Does TokenTelemetry send my data to the cloud?",
    a: "Your logs, sessions, prompts, tokens, and costs never leave your computer — the dashboard reads local files and serves a UI on localhost. The app does send anonymous, content-free usage stats (which pages and features you use — never your code, prompts, paths, or costs) so we know what to improve; it's on by default and you can see the exact payload and turn it off in Settings → Usage & privacy, or with DO_NOT_TRACK=1. There's also an optional GitHub update check (no usage data); disable with TT_NO_UPDATE_CHECK=1.",
  },
  {
    q: "How does TokenTelemetry compare to Langfuse or Helicone?",
    a: "TokenTelemetry is purpose-built for AI coding agents and is zero-config — no SDK instrumentation. Langfuse and Helicone are general LLM-app observability platforms that require code changes and (typically) a cloud account.",
  },
  {
    q: "Which agents does it support?",
    a: "Eleven coding agents (Claude Code, OpenAI Codex, Gemini CLI, Cursor, GitHub Copilot, Qwen CLI, OpenCode, Vibe, Antigravity, Grok Build, Pi) plus Hermes Agent — Nous Research's autonomous agent, which gets its own dedicated dashboard at /hermes with gateway health, scheduled-job monitoring, skills + memory observability, and 38 source platforms (CLI / Telegram / Discord / Feishu / DingTalk / cron / webhook / …).",
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
