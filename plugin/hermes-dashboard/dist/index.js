(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  const { React } = SDK;
  const { useState, useEffect, useCallback } = SDK.hooks;
  const { Card, CardHeader, CardTitle, CardContent, Badge, Button, Input, Label } = SDK.components;

  const STORAGE_KEY = "tt.baseUrl";
  const DEFAULT_BASE = "http://localhost:3000";

  function loadBase() {
    try { return localStorage.getItem(STORAGE_KEY) || DEFAULT_BASE; }
    catch (_) { return DEFAULT_BASE; }
  }
  function saveBase(v) {
    try { localStorage.setItem(STORAGE_KEY, v); } catch (_) {}
  }

  function joinUrl(base, path) {
    return base.replace(/\/+$/, "") + path;
  }

  function HealthPill({ status }) {
    const variant =
      status === "ok"      ? { bg: "bg-emerald-500/15", text: "text-emerald-400", dot: "bg-emerald-400", label: "Reachable" } :
      status === "loading" ? { bg: "bg-zinc-500/15",    text: "text-zinc-400",    dot: "bg-zinc-400",    label: "Checking…" } :
                             { bg: "bg-rose-500/15",    text: "text-rose-400",    dot: "bg-rose-400",    label: "Unreachable" };
    return React.createElement(
      "span",
      { className: `inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${variant.bg} ${variant.text}` },
      React.createElement("span", { className: `w-1.5 h-1.5 rounded-full ${variant.dot}` }),
      variant.label
    );
  }

  function LaunchCard({ base, status, target, title, subtitle, icon }) {
    const disabled = status !== "ok";
    const href = joinUrl(base, target);
    const className = `group flex flex-col gap-2.5 p-5 rounded-lg border transition-all ${
      disabled
        ? "border-zinc-800 bg-zinc-900/30 opacity-50 cursor-not-allowed"
        : "border-zinc-800 bg-zinc-900/50 hover:bg-zinc-800/60 hover:border-amber-500/40 cursor-pointer"
    }`;

    const inner = React.createElement(
      React.Fragment,
      null,
      React.createElement(
        "div",
        { className: "flex items-center justify-between" },
        React.createElement("span", { className: "text-2xl" }, icon),
        React.createElement(
          "span",
          {
            className: `text-xs ${
              disabled ? "text-zinc-600" : "text-zinc-500 group-hover:text-amber-400"
            }`
          },
          "Open ↗"
        )
      ),
      React.createElement("div", { className: "text-sm font-semibold text-zinc-100" }, title),
      React.createElement("div", { className: "text-xs text-zinc-400 leading-snug" }, subtitle)
    );

    if (disabled) {
      return React.createElement("div", { className }, inner);
    }
    return React.createElement(
      "a",
      { href, target: "_blank", rel: "noopener noreferrer", className },
      inner
    );
  }

  const INSTALL_CURL =
    "curl -fsSL https://tokentelemetry.com/install.sh | bash";

  const SUPPORTED_AGENTS = [
    "Claude Code", "Codex", "Gemini CLI", "Cursor",
    "Copilot", "Qwen", "OpenCode", "Vibe", "Antigravity",
    "Hermes Agent"
  ];

  function NotInstalledCard({ base, onRefresh }) {
    const [copied, setCopied] = useState(false);
    const copyInstall = () => {
      try {
        navigator.clipboard.writeText(INSTALL_CURL);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      } catch (_) {}
    };

    return React.createElement(
      Card,
      null,
      React.createElement(
        CardContent,
        { className: "py-8 px-6 max-w-2xl mx-auto" },

        // Header
        React.createElement(
          "div",
          { className: "flex items-start justify-between mb-4" },
          React.createElement(
            "div",
            null,
            React.createElement(
              "div",
              { className: "text-[10px] font-medium uppercase tracking-[0.18em] text-amber-400 mb-1" },
              "TokenTelemetry not detected on ", base.replace(/^https?:\/\//, "")
            ),
            React.createElement(
              "h2",
              { className: "text-lg font-semibold text-zinc-100" },
              "One install, observability for every agent you use"
            )
          ),
          React.createElement(
            Button,
            { size: "sm", variant: "outline", onClick: onRefresh },
            "Refresh"
          )
        ),

        // What TT is — multi-agent pitch
        React.createElement(
          "p",
          { className: "text-sm text-zinc-300 leading-relaxed mb-3" },
          React.createElement("strong", { className: "text-zinc-100" }, "TokenTelemetry"),
          " is a free, local observability dashboard for your AI agents — coding agents and autonomous ones. Sessions, costs, traces, tool calls, and reasoning, all in one place. No SDK, no signup, no cloud."
        ),

        // Agent chips
        React.createElement(
          "div",
          { className: "flex flex-wrap gap-1.5 mb-5" },
          ...SUPPORTED_AGENTS.map((name) =>
            React.createElement(
              "span",
              {
                key: name,
                className: name === "Hermes Agent"
                  ? "text-[10px] font-medium px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30"
                  : "text-[10px] font-medium px-2 py-0.5 rounded-full bg-zinc-800/80 text-zinc-300 border border-zinc-700"
              },
              name
            )
          )
        ),

        // Install command card
        React.createElement(
          "div",
          { className: "rounded-lg border border-zinc-800 bg-zinc-950/60 overflow-hidden mb-3" },
          React.createElement(
            "div",
            { className: "flex items-center justify-between px-3 py-2 border-b border-zinc-800 bg-zinc-900/60" },
            React.createElement(
              "span",
              { className: "text-[10px] font-medium uppercase tracking-[0.18em] text-zinc-400" },
              "Install — macOS / Linux"
            ),
            React.createElement(
              "button",
              {
                onClick: copyInstall,
                className: `text-[11px] font-medium px-2 py-0.5 rounded ${
                  copied ? "text-emerald-400" : "text-zinc-400 hover:text-zinc-100"
                }`
              },
              copied ? "✓ Copied" : "Copy"
            )
          ),
          React.createElement(
            "pre",
            { className: "px-3 py-2.5 text-xs font-mono text-zinc-200 overflow-x-auto" },
            INSTALL_CURL
          )
        ),

        // Footer hints
        React.createElement(
          "div",
          { className: "flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-zinc-500" },
          React.createElement(
            "span",
            null,
            "Already installed? Run ",
            React.createElement("code", { className: "font-mono text-zinc-300" }, "./start.sh"),
            " then click Refresh"
          ),
          React.createElement(
            "a",
            {
              href: "https://tokentelemetry.com",
              target: "_blank",
              rel: "noopener noreferrer",
              className: "text-amber-400 hover:text-amber-300"
            },
            "Learn more ↗"
          )
        )
      )
    );
  }

  function TokenTelemetryLauncher() {
    const [base, setBase] = useState(loadBase());
    const [draft, setDraft] = useState(base);
    const [editing, setEditing] = useState(false);
    const [status, setStatus] = useState("loading");

    const probe = useCallback(async (url) => {
      setStatus("loading");
      try {
        await fetch(url, { mode: "no-cors", cache: "no-store" });
        setStatus("ok");
      } catch (_) {
        setStatus("down");
      }
    }, []);

    useEffect(() => { probe(base); }, [base, probe]);

    const apply = () => {
      const v = draft.trim() || DEFAULT_BASE;
      saveBase(v);
      setBase(v);
      setEditing(false);
    };

    const cards = [
      { target: "/hermes",          title: "Hermes Overview",  subtitle: "Sessions, sources, models, cron health", icon: "☤" },
      { target: "/hermes/skills",   title: "Skills",           subtitle: "Loaded skills from your prompt snapshot", icon: "✦" },
      { target: "/hermes/memory",   title: "Memory",           subtitle: "MEMORY.md and USER.md with progress bars", icon: "✎" },
      { target: "/analytics",       title: "Analytics",        subtitle: "Tokens, cost, and trends across all agents", icon: "📈" },
      { target: "/projects",        title: "Projects",         subtitle: "Per-project rollups, all agents combined", icon: "▣" },
      { target: "/",                title: "All Agents",       subtitle: "Connected coding + autonomous agents", icon: "◉" }
    ];

    return React.createElement(
      "div",
      { className: "flex flex-col h-full gap-4 p-4" },

      // Header card
      React.createElement(
        Card,
        null,
        React.createElement(
          CardHeader,
          { className: "flex flex-row items-start justify-between gap-3 pb-3" },
          React.createElement(
            "div",
            { className: "flex flex-col gap-1" },
            React.createElement(
              "div",
              { className: "flex items-center gap-2" },
              React.createElement(CardTitle, { className: "text-lg" }, "TokenTelemetry"),
              React.createElement(HealthPill, { status })
            ),
            React.createElement(
              "p",
              { className: "text-xs text-zinc-400 max-w-prose leading-relaxed" },
              "Local cost / token / trace observability for Hermes Agent and 9 coding agents. Click any tile below to open the relevant TokenTelemetry page in a new tab — no need to remember a second port."
            )
          ),
          React.createElement(
            Button,
            {
              size: "sm",
              variant: "outline",
              onClick: () => probe(base)
            },
            "Refresh"
          )
        ),

        // Base URL row (collapsed by default, click to edit)
        React.createElement(
          CardContent,
          { className: "pt-0 pb-3" },
          editing
            ? React.createElement(
                "div",
                { className: "flex items-end gap-2" },
                React.createElement(
                  "div",
                  { className: "flex flex-col gap-1 grow" },
                  React.createElement(Label, { className: "text-xs text-zinc-400" }, "TokenTelemetry base URL"),
                  React.createElement(Input, {
                    value: draft,
                    onChange: (e) => setDraft(e.target.value),
                    placeholder: DEFAULT_BASE,
                    className: "font-mono text-sm",
                    autoFocus: true,
                    onKeyDown: (e) => { if (e.key === "Enter") apply(); }
                  })
                ),
                React.createElement(Button, { size: "sm", onClick: apply }, "Save"),
                React.createElement(Button, { size: "sm", variant: "ghost", onClick: () => { setDraft(base); setEditing(false); } }, "Cancel")
              )
            : React.createElement(
                "div",
                { className: "flex items-center gap-2 text-xs text-zinc-500" },
                React.createElement("span", null, "Base:"),
                React.createElement("code", { className: "font-mono text-zinc-300 bg-zinc-900/60 rounded px-1.5 py-0.5" }, base),
                React.createElement(
                  "button",
                  {
                    onClick: () => setEditing(true),
                    className: "text-zinc-500 hover:text-amber-400 underline-offset-2 hover:underline"
                  },
                  "edit"
                )
              )
        )
      ),

      // Launch grid
      status === "down"
        ? React.createElement(NotInstalledCard, { base, onRefresh: () => probe(base) })
        : React.createElement(
            "div",
            {
              className: "grid gap-3",
              style: { gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))" }
            },
            ...cards.map((c) =>
              React.createElement(LaunchCard, {
                key: c.target,
                base,
                status,
                target: c.target,
                title: c.title,
                subtitle: c.subtitle,
                icon: c.icon
              })
            )
          ),

      // Footer hint
      React.createElement(
        "p",
        { className: "text-[11px] text-zinc-600 text-center pt-2" },
        "TokenTelemetry runs locally and reads ",
        React.createElement("code", { className: "font-mono" }, "$HERMES_HOME"),
        " (or ",
        React.createElement("code", { className: "font-mono" }, "~/.hermes"),
        " by default). Your data never leaves your machine."
      )
    );
  }

  if (window.__HERMES_PLUGINS__ && typeof window.__HERMES_PLUGINS__.register === "function") {
    window.__HERMES_PLUGINS__.register("tokentelemetry", TokenTelemetryLauncher);
  } else {
    console.error("[tokentelemetry] Hermes plugin loader not found on window");
  }
})();
