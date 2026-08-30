"use client";

import { useEffect, useState, useRef } from "react";
import { BarChart3, ChevronDown, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/cn";
import { Card, CardHeader, CardTitle, Badge, Skeleton } from "@/components/ui";
import {
  getTelemetryPreview, setTelemetry, type TelemetryPreview,
} from "@/lib/telemetry";

/**
 * Settings → "Usage & privacy". The transparency surface for opt-out telemetry:
 * a default-on toggle plus an inspectable "exactly what we send" disclosure. The
 * anchor id (#usage-privacy) is the target of the first-run notice's
 * "See exactly what" link.
 */
export default function UsagePrivacySettings() {
  const [state, setState] = useState<TelemetryPreview | null>(null);
  const [toggling, setToggling] = useState(false);
  const [showPayload, setShowPayload] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    getTelemetryPreview()
      .then((s) => { if (!cancelled) setState(s); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!state) return;
    if (typeof window !== "undefined" && window.location.hash === "#usage-privacy") {
      const t = setTimeout(() => {
        rootRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 60);
      return () => clearTimeout(t);
    }
  }, [state]);

  const toggle = async () => {
    if (!state || state.env_forced_off) return;
    setToggling(true);
    try {
      const next = !state.enabled;
      const res = await setTelemetry(next);
      // Re-pull the preview so effective/recent stay in sync.
      const fresh = await getTelemetryPreview();
      setState({ ...fresh, ...res });
    } catch {
      /* best-effort */
    }
    setToggling(false);
  };

  return (
    <div ref={rootRef}>
      <Card>
      <CardHeader>
        <CardTitle>
          <BarChart3 size={14} className="text-[var(--tt-brand)]" />
          Anonymous usage stats
        </CardTitle>
        {state && (
          <Badge variant={state.effective ? "success" : "neutral"} size="sm">
            {state.env_forced_off ? "Off · env" : state.is_ci ? "Off · CI" : state.enabled ? "On" : "Off"}
          </Badge>
        )}
      </CardHeader>

      {!state ? (
        <Skeleton className="h-14 w-full" />
      ) : (
        <div className="space-y-4">
          <div className="flex items-start justify-between gap-4">
            <p className="text-[13px] leading-relaxed text-[var(--tt-fg-dim)] max-w-[560px]">
              When on, TokenTelemetry sends <strong className="text-[var(--tt-fg-muted)]">anonymous,
              content-free</strong> stats about which pages and features you use, so we can focus on
              what matters. It <strong className="text-[var(--tt-fg-muted)]">never</strong> sends your
              code, prompts, file paths, project names, tokens, or costs.{" "}
              {state.env_forced_off
                ? "It is currently forced off by an environment variable (DO_NOT_TRACK / TT_NO_TELEMETRY)."
                : "Turn it off anytime with the toggle on the right — or set DO_NOT_TRACK=1 / TT_NO_TELEMETRY=1."}
            </p>
            <button
              onClick={toggle}
              role="switch"
              aria-checked={state.enabled}
              aria-label="Toggle anonymous usage stats"
              disabled={toggling || state.env_forced_off}
              className={cn(
                "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border transition-colors mt-0.5",
                "border-[var(--tt-border)]",
                state.enabled ? "tt-tint-1" : "",
                state.env_forced_off ? "opacity-50 cursor-not-allowed" : "cursor-pointer",
              )}
            >
              <span
                className={cn(
                  "absolute h-3.5 w-3.5 rounded-full transition-transform",
                  state.enabled
                    ? "translate-x-[18px] bg-[var(--tt-brand)]"
                    : "translate-x-0.5 bg-[var(--tt-fg-muted)]",
                )}
              />
            </button>
          </div>

          {/* Never-collected reassurance */}
          <div className="flex flex-wrap gap-1.5">
            {state.never_collected.map((n) => (
              <span
                key={n}
                className="inline-flex items-center gap-1 px-2 h-6 rounded-full text-[11px] text-[var(--tt-fg-dim)] border border-[var(--tt-border)] bg-[var(--tt-panel)]"
              >
                <ShieldCheck size={10} className="text-[var(--tt-success-fg)]" />
                no {n}
              </span>
            ))}
          </div>

          {/* Exactly-what-we-send disclosure */}
          <div className="rounded-[var(--tt-radius)] border border-[var(--tt-border)] overflow-hidden">
            <button
              onClick={() => setShowPayload((v) => !v)}
              className="w-full flex items-center justify-between gap-2 px-3 h-9 text-[12px] font-medium text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] hover:tt-tint-1 transition-colors"
            >
              <span>Show exactly what we send ({state.events.length} event types)</span>
              <ChevronDown size={14} className={cn("transition-transform", showPayload && "rotate-180")} />
            </button>
            {showPayload && (
              <div className="border-t border-[var(--tt-border)] bg-[var(--tt-sunken)] p-3 space-y-4">
                <div>
                  <h3 className="text-[12px] font-medium text-[var(--tt-fg-muted)] mb-2">In plain English</h3>
                  <ul className="text-[12px] text-[var(--tt-fg-dim)] space-y-1 pl-4">
                    <li className="list-disc">Which pages you open — including which coding agent&apos;s panel</li>
                    <li className="list-disc">Which features you use (summaries, filters, budgets, Hermes, etc.)</li>
                    <li className="list-disc">When you open or save a budget — the count only, never the limit or amount</li>
                    <li className="list-disc">Whether a summary succeeded or failed, and which engine</li>
                    <li className="list-disc">
                      For each coding agent found on this machine, whether we could read any sessions
                      from it — as a size band (&ldquo;10-99&rdquo;), never the actual number. This is
                      how we find out that support for an agent is broken without you having to report it.
                    </li>
                    <li className="list-disc">Your OS, CPU type, and app version</li>
                    <li className="list-disc">Your country (from the network edge — never your IP)</li>
                    <li className="list-disc">Which AI agents are detected (Claude, Codex, …)</li>
                    <li className="list-disc">A random per-launch session id (reset each launch, not linked to you)</li>
                  </ul>
                </div>

                {/* The authoritative list. Generated from the same allowlists the
                    sender validates against, so it cannot drift from what is
                    actually sent — every value below is one a real payload can
                    contain, and nothing outside these lists can be transmitted. */}
                <div>
                  <h3 className="text-[12px] font-medium text-[var(--tt-fg-muted)] mb-1">
                    Every event, and every value it can carry
                  </h3>
                  <p className="text-[11px] text-[var(--tt-fg-dim)] mb-2 max-w-[560px]">
                    Read straight from the allowlist the app validates against before sending, so
                    it is always current. Anything not on these lists is replaced with
                    <span className="font-mono"> other</span> — it is never transmitted.
                  </p>
                  <div className="space-y-2">
                    {state.event_catalog.map((spec) => (
                      <div
                        key={spec.event}
                        className="rounded border border-[var(--tt-border)] bg-[var(--tt-panel)] px-2.5 py-2"
                      >
                        <div className="font-mono text-[11px] text-[var(--tt-fg-muted)]">{spec.event}</div>
                        {spec.props.length === 0 ? (
                          <div className="text-[11px] text-[var(--tt-fg-dim)] mt-0.5">
                            no properties — the event name alone
                          </div>
                        ) : (
                          <div className="mt-1 space-y-1">
                            {spec.props.map((prop) => (
                              <div key={prop.name} className="text-[11px] leading-relaxed">
                                <span className="font-mono text-[var(--tt-fg-dim)]">{prop.name}</span>
                                <span className="text-[var(--tt-fg-dim)]">: </span>
                                {prop.values ? (
                                  <span className="text-[var(--tt-fg-dim)]">
                                    {prop.values.join(" · ")}
                                  </span>
                                ) : (
                                  <span className="text-[var(--tt-fg-dim)] italic">
                                    short plain text only (no paths, emails, or free text)
                                  </span>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Real current values, not a description of them. */}
                <div>
                  <h3 className="text-[12px] font-medium text-[var(--tt-fg-muted)] mb-1">
                    Attached to every event
                  </h3>
                  <p className="text-[11px] text-[var(--tt-fg-dim)] mb-2 max-w-[560px]">
                    These are this machine&apos;s actual values right now — not an example.
                  </p>
                  <div className="rounded border border-[var(--tt-border)] bg-[var(--tt-panel)] divide-y divide-[var(--tt-border)]">
                    {state.always_sent.map((row) => (
                      <div key={`${row.scope}.${row.name}`} className="px-2.5 py-1.5">
                        <div className="flex items-baseline gap-2 flex-wrap">
                          <span className="font-mono text-[11px] text-[var(--tt-fg-dim)]">{row.name}</span>
                          <span className="font-mono text-[11px] text-[var(--tt-fg-muted)] break-all">
                            {String(row.value) === "" ? "(empty)" : String(row.value)}
                          </span>
                        </div>
                        {row.note && (
                          <div className="text-[11px] text-[var(--tt-fg-dim)] mt-0.5">{row.note}</div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <button
                    onClick={() => setShowRaw((v) => !v)}
                    className="flex items-center gap-1.5 text-[11px] font-medium text-[var(--tt-fg-muted)] hover:text-[var(--tt-fg)] transition-colors"
                  >
                    <ChevronDown size={12} className={cn("transition-transform", showRaw && "rotate-180")} />
                    {showRaw ? "Hide" : "Show"} the raw payloads
                  </button>
                  {showRaw && (
                    <pre className="mt-2 max-h-[280px] overflow-auto bg-[var(--tt-panel)] p-3 text-[11px] font-mono text-[var(--tt-fg-dim)] leading-relaxed rounded border border-[var(--tt-border)]">
                      {JSON.stringify(state.sample, null, 2)}
                    </pre>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </Card>
    </div>
  );
}
