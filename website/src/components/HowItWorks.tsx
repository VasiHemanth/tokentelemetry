const STEPS = [
  {
    n: "1",
    title: "Run one command",
    body: "Paste it into your terminal. Installs in seconds, opens automatically — no account, no API keys.",
    code: <><span className="text-[var(--tt-fg-faint)]">$ </span>curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash</>,
  },
  {
    n: "2",
    title: "It finds your agents",
    body: "Scans the log files Claude Code, Codex, Cursor & co. already write to your disk. Read-only. Nothing is sent anywhere.",
    code: <><span className="text-[var(--tt-success-fg,#10b981)]">✓</span> detected 13 agents · 510 sessions</>,
  },
  {
    n: "3",
    title: "Open the dashboard",
    body: "Tokens, cost, traces, and reasoning — for every agent, in one local dashboard.",
    code: <><span className="text-[var(--tt-fg-faint)]">→ </span>http://localhost:3000</>,
  },
];

export default function HowItWorks() {
  return (
    <section className="relative max-w-[1180px] mx-auto px-5 py-12 sm:py-[72px]">
      <div className="text-center max-w-[680px] mx-auto mb-10">
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--tt-fg-dim)] mb-3">
          From zero to dashboard in one command
        </p>
        <h2 className="text-[clamp(26px,3.6vw,42px)] leading-[1.08] tracking-[-0.025em] font-semibold text-[var(--tt-fg)]">
          No instrumentation. <span className="text-[var(--tt-brand)]">No code changes.</span>
        </h2>
        <p className="mt-3.5 text-[15.5px] text-[var(--tt-fg-muted)] leading-relaxed">
          Your agents already write logs. TokenTelemetry just reads them — so setup is one line, and there&apos;s
          nothing to wire into your codebase.
        </p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 sm:gap-4">
        {STEPS.map((s) => (
          <div key={s.n} className="p-6 rounded-[var(--tt-radius-lg)] border border-[var(--tt-border)] bg-[var(--tt-panel)]">
            <div className="inline-flex items-center justify-center w-[30px] h-[30px] rounded-lg mb-3.5 font-mono text-[12px] font-semibold text-[var(--tt-brand)] bg-[color:var(--tt-brand-glow)] border"
              style={{ borderColor: "color-mix(in srgb, var(--tt-brand) 25%, transparent)" }}>
              {s.n}
            </div>
            <h3 className="text-[16px] font-semibold tracking-[-0.01em] text-[var(--tt-fg)] mb-1.5">{s.title}</h3>
            <p className="text-[13.5px] text-[var(--tt-fg-muted)] leading-relaxed">{s.body}</p>
            <div className="mt-3 px-3 py-2 rounded-lg bg-[var(--tt-sunken)] border border-[var(--tt-border)] font-mono text-[11.5px] text-[var(--tt-fg-muted)] overflow-x-auto whitespace-nowrap">
              {s.code}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
