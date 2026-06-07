"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Sparkles, Target, ListChecks, Gauge, Star, Wrench, FileCode, Terminal,
  AlertTriangle, RefreshCw, Loader2, Coins, Settings2, Info,
  KeyRound, Clock, ServerOff, Ban, AlertOctagon, AlertCircle,
} from "lucide-react";
import { Badge, Button } from "@/components/ui";
import { cn } from "@/lib/cn";
import { formatTokens, formatCost } from "@/lib/format";
import {
  getCachedSummary, generateSummary, getSummarizerConfig,
  type Summary, type SummarizerConfig, type SummaryErrorInfo,
} from "@/lib/summarizer";

interface SummaryPanelProps {
  sessionId: string;
  agent: string;
}

/**
 * Trace summary panel — lives near the top of the session trace page.
 * Always renders the deterministic brief once a summary exists; renders the
 * 4 LLM narrative sections when present. Generate/Regenerate POSTs and shows a
 * loading state for the 10–60s call. Surfaces config-disabled and errors.
 */
export default function SummaryPanel({ sessionId, agent }: SummaryPanelProps) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [config, setConfig] = useState<SummarizerConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorInfo, setErrorInfo] = useState<SummaryErrorInfo | null>(null);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      getCachedSummary(sessionId).catch(() => null),
      getSummarizerConfig().catch(() => null),
    ]).then(([s, c]) => {
      if (cancelled) return;
      setSummary(s);
      setConfig(c);
      setLoading(false);
    });
    return () => { cancelled = true; };
  }, [sessionId]);

  const runGenerate = async (force: boolean) => {
    setGenerating(true);
    setError(null);
    setErrorInfo(null);
    try {
      const res = await generateSummary(sessionId, agent, force);
      if (res.error) {
        setError(res.error);
        if (res.error_info) setErrorInfo(res.error_info);
      } else {
        setSummary(res.summary);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to generate summary.");
    } finally {
      setGenerating(false);
    }
  };

  if (loading) return null;

  const aiEnabled = config?.enabled === true;
  const brief = summary?.brief;
  const narrative = summary?.narrative;
  const hasNarrative = narrative && Object.keys(narrative).length > 0;

  const toolEntries = brief ? Object.entries(brief.tools).sort((a, b) => b[1] - a[1]) : [];
  const maxTool = toolEntries[0]?.[1] || 1;

  return (
    <div className="rounded-[var(--tt-radius-lg)] border border-[var(--tt-border-strong)] bg-gradient-to-br from-[var(--tt-panel)] to-[var(--tt-raised)] overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 px-5 py-3.5 border-b border-[var(--tt-border)]">
        <button
          onClick={() => setCollapsed((v) => !v)}
          className="flex items-center gap-2 group min-w-0"
        >
          <span className="h-7 w-7 grid place-items-center rounded-md bg-[color:var(--tt-brand-glow)] text-[var(--tt-brand)]">
            <Sparkles size={14} />
          </span>
          <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--tt-fg)]">
            Trace summary
          </span>
          {summary?.stale && <Badge variant="warn" size="xs">Stale</Badge>}
          {summary && !hasNarrative && <Badge variant="neutral" size="xs">Brief only</Badge>}
        </button>
        <div className="flex items-center gap-2 shrink-0">
          {summary?.generated_at && (
            <span className="hidden sm:inline text-[10px] font-mono text-[var(--tt-fg-faint)]">
              {new Date(summary.generated_at).toLocaleString()}
            </span>
          )}
          <Button
            variant={summary ? "secondary" : "primary"}
            size="sm"
            onClick={() => runGenerate(!!summary)}
            disabled={generating}
          >
            {generating ? (
              <><Loader2 size={13} className="animate-spin" /> Generating…</>
            ) : summary ? (
              <><RefreshCw size={13} /> Regenerate</>
            ) : aiEnabled ? (
              <><Sparkles size={13} /> Generate summary</>
            ) : (
              <><Sparkles size={13} /> Generate brief</>
            )}
          </Button>
        </div>
      </div>

      {!collapsed && (
        <div className="p-5 space-y-5">
          {generating && !summary && (
            <div className="flex items-center gap-2 text-[12px] text-[var(--tt-fg-muted)]">
              <Loader2 size={14} className="animate-spin text-[var(--tt-brand)]" />
              Generating summary — this can take 10–60s while the agent CLI runs.
            </div>
          )}

          {errorInfo ? (
            <SummaryErrorCard info={errorInfo} />
          ) : error ? (
            <div className="flex items-start gap-2 rounded-[var(--tt-radius)] border border-[var(--tt-danger-bd)] bg-[var(--tt-danger-bg)] px-3 py-2.5">
              <AlertTriangle size={14} className="mt-0.5 shrink-0 text-[var(--tt-danger-fg)]" />
              <p className="text-[12px] text-[var(--tt-danger-fg)]">{error}</p>
            </div>
          ) : null}

          {/* No summary yet */}
          {!summary && !generating && (
            <div className="text-[13px] text-[var(--tt-fg-muted)]">
              {aiEnabled ? (
                <>No summary cached yet. Generate one to get a narrative plus the deterministic brief.</>
              ) : (
                <div className="flex flex-col gap-2">
                  <span>
                    AI narratives are off — generating produces the deterministic brief only
                    (intent, tools, files, cost; no data leaves your machine).
                  </span>
                  <Link
                    href="/settings"
                    className="inline-flex items-center gap-1.5 text-[12px] font-medium text-[var(--tt-brand)] hover:underline"
                  >
                    <Settings2 size={12} /> Enable AI narratives in settings
                  </Link>
                </div>
              )}
            </div>
          )}

          {/* Narrative (LLM) sections */}
          {hasNarrative && (
            <div className="grid gap-4 md:grid-cols-2">
              {narrative.intent_outcome && (
                <NarrativeBlock icon={<Target size={13} />} title="Intent & Outcome" tone="brand">
                  <p className="text-[13px] leading-relaxed text-[var(--tt-fg)]">{narrative.intent_outcome}</p>
                </NarrativeBlock>
              )}
              {narrative.efficiency && (
                <NarrativeBlock icon={<Gauge size={13} />} title="Efficiency" tone="warn">
                  <p className="text-[13px] leading-relaxed text-[var(--tt-fg)]">{narrative.efficiency}</p>
                </NarrativeBlock>
              )}
              {narrative.actions && narrative.actions.length > 0 && (
                <NarrativeBlock icon={<ListChecks size={13} />} title="Actions" tone="info">
                  <ul className="space-y-1.5">
                    {narrative.actions.map((a, i) => (
                      <li key={i} className="flex gap-2 text-[12px] leading-relaxed text-[var(--tt-fg-muted)]">
                        <span className="text-[var(--tt-brand)] mt-0.5">→</span><span>{a}</span>
                      </li>
                    ))}
                  </ul>
                </NarrativeBlock>
              )}
              {narrative.notable && narrative.notable.length > 0 && (
                <NarrativeBlock icon={<Star size={13} />} title="Notable" tone="success">
                  <ul className="space-y-1.5">
                    {narrative.notable.map((n, i) => (
                      <li key={i} className="flex gap-2 text-[12px] leading-relaxed text-[var(--tt-fg-muted)]">
                        <span className="text-[var(--tt-success-fg)] mt-0.5">•</span><span>{n}</span>
                      </li>
                    ))}
                  </ul>
                </NarrativeBlock>
              )}
            </div>
          )}

          {/* Deterministic brief — always shown when a summary exists */}
          {brief && (
            <div className="space-y-4 pt-1">
              {hasNarrative && (
                <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--tt-fg-dim)]">
                  <Info size={11} /> Deterministic brief
                </div>
              )}

              {brief.intent && (
                <div>
                  <div className="text-[9px] font-semibold uppercase tracking-[0.16em] text-[var(--tt-fg-dim)] mb-1">Intent</div>
                  <p className="text-[13px] leading-relaxed text-[var(--tt-fg)]">{brief.intent}</p>
                </div>
              )}

              {/* Token + cost strip */}
              <div className="flex flex-wrap items-center gap-3">
                <Stat label="Input" value={formatTokens(brief.tokens.input)} />
                <Stat label="Output" value={formatTokens(brief.tokens.output)} />
                <Stat label="Total" value={formatTokens(brief.tokens.total)} accent />
                <Stat label="API equiv." value={formatCost(brief.cost)} icon={<Coins size={11} />} accent />
                <Stat label="User turns" value={brief.user_turns} />
                {brief.model && (
                  <Badge variant="success" size="xs" className="font-mono normal-case" title={brief.model}>{brief.model}</Badge>
                )}
              </div>

              {/* Tool histogram */}
              {toolEntries.length > 0 && (
                <BriefSection icon={<Wrench size={12} />} title={`Tools (${toolEntries.length})`}>
                  <div className="space-y-1.5">
                    {toolEntries.map(([name, count]) => (
                      <div key={name} className="space-y-0.5">
                        <div className="flex items-center justify-between text-[11px]">
                          <span className="font-mono text-[var(--tt-fg)] truncate">{name}</span>
                          <span className="tabular text-[var(--tt-fg-dim)]">×{count}</span>
                        </div>
                        <div className="h-1 rounded-full tt-tint-1 overflow-hidden">
                          <div className="h-full bg-sky-500/60" style={{ width: `${(count / maxTool) * 100}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>
                </BriefSection>
              )}

              {brief.files.length > 0 && (
                <BriefSection icon={<FileCode size={12} />} title={`Files touched (${brief.files.length})`}>
                  <div className="space-y-0.5 max-h-40 overflow-y-auto">
                    {brief.files.map((f) => (
                      <div key={f} className="font-mono text-[10px] text-[var(--tt-fg-muted)] truncate" title={f}>{f}</div>
                    ))}
                  </div>
                </BriefSection>
              )}

              {brief.commands.length > 0 && (
                <BriefSection icon={<Terminal size={12} />} title={`Commands (${brief.commands.length})`}>
                  <div className="space-y-1 max-h-48 overflow-y-auto">
                    {brief.commands.map((c, i) => (
                      <pre key={i} className="font-mono text-[10px] text-[var(--tt-fg-muted)] bg-[var(--tt-sunken)] border border-[var(--tt-border)] rounded px-2 py-1 whitespace-pre-wrap break-all">{c}</pre>
                    ))}
                  </div>
                </BriefSection>
              )}

              {brief.errors.length > 0 && (
                <BriefSection icon={<AlertTriangle size={12} className="text-[var(--tt-danger-fg)]" />} title={`Errors (${brief.errors.length})`}>
                  <div className="space-y-1 max-h-40 overflow-y-auto">
                    {brief.errors.map((e, i) => (
                      <pre key={i} className="font-mono text-[10px] text-[var(--tt-danger-fg)] bg-[var(--tt-danger-bg)] border border-[var(--tt-danger-bd)] rounded px-2 py-1 whitespace-pre-wrap break-all">{e}</pre>
                    ))}
                  </div>
                </BriefSection>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function NarrativeBlock({ icon, title, tone, children }: {
  icon: React.ReactNode; title: string;
  tone: "brand" | "warn" | "info" | "success"; children: React.ReactNode;
}) {
  const toneCls = {
    brand: "text-[var(--tt-brand)]",
    warn: "text-[var(--tt-warn-fg)]",
    info: "text-[var(--tt-info-fg)]",
    success: "text-[var(--tt-success-fg)]",
  }[tone];
  return (
    <div className="rounded-[var(--tt-radius)] border border-[var(--tt-border)] bg-[var(--tt-panel)]/60 p-3.5">
      <div className={cn("flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] mb-2", toneCls)}>
        {icon} {title}
      </div>
      {children}
    </div>
  );
}

function BriefSection({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <details open className="group">
      <summary className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--tt-fg-dim)] cursor-pointer hover:text-[var(--tt-fg)] mb-2 list-none">
        {icon} {title}
      </summary>
      {children}
    </details>
  );
}

const ERROR_ICONS: Record<SummaryErrorInfo["category"], React.ComponentType<{ size?: number; className?: string }>> = {
  auth: KeyRound,
  timeout: Clock,
  network: ServerOff,
  quota: Ban,
  too_large: Gauge,
  model: AlertOctagon,
  no_output: AlertCircle,
  unknown: AlertCircle,
};

/**
 * Render a hint string with `inline code` segments rendered as <code>.
 * Splits on backticked spans — pairs of backticks become monospace.
 */
function renderHint(hint: string): React.ReactNode {
  const parts = hint.split(/(`[^`]+`)/g);
  return parts.map((part, i) => {
    if (part.startsWith("`") && part.endsWith("`") && part.length > 1) {
      return (
        <code
          key={i}
          className="font-mono text-[11px] px-1 py-[1px] rounded bg-[var(--tt-panel)] border border-[var(--tt-border)] text-[var(--tt-fg)]"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

function SummaryErrorCard({ info }: { info: SummaryErrorInfo }) {
  const Icon = ERROR_ICONS[info.category] ?? AlertCircle;
  return (
    <div className="rounded-[var(--tt-radius)] border border-[var(--tt-danger-bd)] bg-[var(--tt-danger-bg)] p-3.5 space-y-2.5">
      <div className="flex items-start gap-2.5">
        <span className="h-7 w-7 grid place-items-center rounded-md bg-[var(--tt-danger-bg)] border border-[var(--tt-danger-bd)] text-[var(--tt-danger-fg)] shrink-0">
          <Icon size={14} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-semibold text-[var(--tt-danger-fg)] leading-tight">
            {info.title}
          </div>
          <p className="text-[12px] mt-0.5 leading-relaxed text-[var(--tt-fg)]">
            {info.message}
          </p>
        </div>
      </div>

      {info.hint && (
        <div className="rounded-[var(--tt-radius)] bg-[var(--tt-sunken)] border border-[var(--tt-border)] px-2.5 py-2 text-[12px] leading-relaxed text-[var(--tt-fg-muted)]">
          {renderHint(info.hint)}
        </div>
      )}

      {info.category === "auth" && (
        <Link
          href="/settings"
          className="inline-flex items-center gap-1.5 text-[12px] font-medium text-[var(--tt-brand)] hover:underline"
        >
          <Settings2 size={12} /> Settings →
        </Link>
      )}

      {info.raw && (
        <details className="group">
          <summary className="cursor-pointer text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--tt-fg-dim)] hover:text-[var(--tt-fg)] list-none select-none">
            Show raw error
          </summary>
          <pre className="mt-2 font-mono text-[10px] text-[var(--tt-fg-muted)] bg-[var(--tt-sunken)] border border-[var(--tt-border)] rounded px-2 py-1.5 whitespace-pre-wrap break-all max-h-48 overflow-y-auto">
            {info.raw}
          </pre>
        </details>
      )}
    </div>
  );
}

function Stat({ label, value, accent, icon }: { label: string; value: React.ReactNode; accent?: boolean; icon?: React.ReactNode }) {
  return (
    <div className="inline-flex items-center gap-1.5 bg-[var(--tt-sunken)] border border-[var(--tt-border)] rounded-md px-2.5 h-7">
      {icon && <span className="text-[var(--tt-fg-faint)]">{icon}</span>}
      <span className="text-[9px] font-semibold uppercase tracking-[0.14em] text-[var(--tt-fg-dim)]">{label}</span>
      <span className={cn("text-[12px] font-semibold tabular", accent ? "text-[var(--tt-brand)]" : "text-[var(--tt-fg)]")}>{value}</span>
    </div>
  );
}
