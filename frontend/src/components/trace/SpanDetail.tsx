"use client";

import type { ReactNode } from "react";
import { ExternalLink, ZoomIn } from "lucide-react";
import type { SpanTokens, TraceSpan } from "@/lib/traceTree/types";
import {
  directAgents,
  overlappingAgents,
  ownWork,
  ownerAgent,
  turnOf,
  type Rollup,
  type TraceIndex,
} from "@/lib/traceTree/tree";
import { fmtClock, fmtCost, fmtDur, fmtHm, fmtTokens } from "@/lib/traceTree/timeScale";
import { KindChip, SECTION_LABEL, Tag, type ColorOf } from "./shared";

interface Props {
  span: TraceSpan | null;
  index: TraceIndex;
  rollups: Map<string, Rollup>;
  colorOf: ColorOf;
  real: boolean;
  sessionStart?: number;
  onSelect: (id: string) => void;
  onZoom: (span: TraceSpan) => void;
  onJumpToEvent?: (eventIndex: number) => void;
}

export default function SpanDetail(p: Props) {
  const { span, index, rollups, colorOf, real } = p;

  if (!span) {
    const first = index.agents[0];
    return (
      <div className="space-y-3">
        <h2 className="text-sm font-semibold text-[var(--tt-fg)]">Select a span</h2>
        <p className="text-xs leading-relaxed text-[var(--tt-fg-muted)]">
          Click a row or a timeline bar. Subagents sit under the model call that spawned them, so the tree reads in the order things happened.
          {real && " Their bars share the main agent's clock, which shows when each one started and how long it kept going after the main agent moved on."}
        </p>
        {first && (
          <Section label="Start here">
            <LinkBtn onClick={() => p.onSelect(first.id)} dot={colorOf(first.agent?.agentType)} text={`First spawn: ${first.agent?.agentType ?? first.title}`} right={real ? fmtClock(first.start) : undefined} />
          </Section>
        )}
      </div>
    );
  }

  const roll = rollups.get(span.id);
  const when: Array<[string, ReactNode]> = real
    ? [["Started", fmtClock(span.start)], ["Ended", fmtClock(span.end)], ["Duration", fmtDur(span.end - span.start)]]
    : [];
  if (real && p.sessionStart != null && span.start >= p.sessionStart) when.push(["Into session", fmtDur(span.start - p.sessionStart)]);
  const agentLink = (a: TraceSpan, right?: string) => (
    <LinkBtn key={a.id} onClick={() => p.onSelect(a.id)} dot={colorOf(a.agent?.agentType)} text={`${a.agent?.agentType ?? a.title}${a.label ? ` · ${a.label}` : ""}`} right={right} />
  );

  let body: ReactNode = null;

  if (span.kind === "turn") {
    const work = ownWork(span);
    const spawns = directAgents(span);
    const woke = span.notifiedBy ? index.agentByChild.get(span.notifiedBy) : undefined;
    body = (
      <>
        {span.label && <Quote>{span.label}</Quote>}
        <Kv rows={[...when, ["Model calls", work.llm], ["Tool calls", work.tools], ["Main-agent tokens", fmtTokens(work.tokens)]]} />
        {spawns.length > 0 && (
          <Section label="Spawned in this turn">
            {spawns.map((a) => agentLink(a, real ? `+${fmtDur((a.agent?.callStart ?? a.start) - span.start)}` : undefined))}
          </Section>
        )}
        {woke && (
          <Section label="Woken by">
            {agentLink(woke, real ? fmtDur(woke.end - woke.start) : undefined)}
            {real && <Callout>The main agent was idle until this subagent reported back at {fmtClock(span.start)}.</Callout>}
          </Section>
        )}
      </>
    );
  } else if (span.kind === "llm") {
    const owner = ownerAgent(index, span);
    const t = span.tokens;
    body = (
      <>
        {span.label && <Quote>{span.label}</Quote>}
        <Kv
          rows={[
            ...(real ? ([["Response at", fmtClock(span.end)], ["Waited", `${span.approxStart ? "~" : ""}${fmtDur(span.end - span.start)}`]] as Array<[string, ReactNode]>) : []),
            ...(t ? ([["Input", t.input.toLocaleString()], ["Cache read", t.cacheRead.toLocaleString()], ["Cache write", t.cacheWrite.toLocaleString()], ["Output", t.output.toLocaleString()]] as Array<[string, ReactNode]>) : []),
          ]}
        />
        {t && <TokenBar t={t} />}
        {span.children.length > 0 && (
          <Section label="Calls made">
            {span.children.slice(0, 12).map((c) =>
              c.kind === "agent" ? (
                agentLink(c, real ? fmtDur(c.end - c.start) : undefined)
              ) : (
                <LinkBtn key={c.id} onClick={() => p.onSelect(c.id)} text={`${c.title}${c.label ? ` · ${c.label}` : ""}`} right={real ? fmtDur(c.end - c.start) : undefined} />
              ),
            )}
            {span.children.length > 12 && <div className="px-2 text-[11px] text-[var(--tt-fg-dim)]">{span.children.length - 12} more</div>}
          </Section>
        )}
        {owner && <div className="text-[11px] text-[var(--tt-fg-dim)]">Inside {owner.agent?.agentType ?? owner.title}</div>}
      </>
    );
  } else if (span.kind === "tool") {
    const resumed = span.resumes ? index.agentByChild.get(span.resumes) : undefined;
    body = (
      <>
        {span.label && <p className="text-xs leading-relaxed text-[var(--tt-fg-muted)]">{span.label}</p>}
        <Kv rows={[...when, ...(span.error ? ([["Result", <span key="e" className="text-[var(--tt-danger-fg)]">error</span>]] as Array<[string, ReactNode]>) : [])]} />
        {resumed && (
          <Section label="Resumed">
            <Callout>
              This message woke an existing subagent instead of spawning a new one.{real && ` Its work after ${fmtClock(span.start)} is counted under that subagent.`}
            </Callout>
            {agentLink(resumed, real ? fmtDur(resumed.end - resumed.start) : undefined)}
          </Section>
        )}
      </>
    );
  } else {
    const a = span.agent;
    const turn = turnOf(index, span);
    const callStart = a?.callStart ?? span.start;
    const callEnd = a?.callEnd;
    const overlap = real ? overlappingAgents(index, span) : [];
    const childId = a?.childId;
    const reports = childId ? (index.reports.get(childId) ?? []) : [];
    const resumes = childId ? (index.resumers.get(childId) ?? []) : [];
    const lineage = [
      [turn, `Spawned in ${turn.title}`, callStart] as [TraceSpan, string, number],
      ...reports.map((r): [TraceSpan, string, number] => [r, "Reported back to main agent", r.start]),
      ...resumes.map((r): [TraceSpan, string, number] => [r, `Resumed: ${r.label || r.title}`, r.start]),
    ].sort((x, y) => x[2] - y[2]);
    const loaded = a?.loaded !== false;
    body = (
      <>
        {span.label && <p className="text-xs leading-relaxed text-[var(--tt-fg-muted)]">{span.label}</p>}
        {real && (
          <Callout>
            Spawned {fmtDur(callStart - turn.start)} into {turn.title}, at {fmtClock(callStart)}.{" "}
            {callEnd != null && a?.background
              ? `The call returned after ${fmtDur(callEnd - callStart)} and the subagent kept running in the background for ${fmtDur(span.end - callEnd)}.`
              : callEnd != null
                ? `The main agent waited ${fmtDur(callEnd - callStart)} for it.`
                : ""}
          </Callout>
        )}
        <Kv
          rows={[
            ...when,
            ["Model", a?.model ?? "-"],
            ["Tokens", roll ? roll.tokens.toLocaleString() : "-"],
            ...(a?.cost != null ? ([["Cost", fmtCost(a.cost)]] as Array<[string, ReactNode]>) : []),
            ...(loaded ? ([["Model calls", roll?.llm ?? 0]] as Array<[string, ReactNode]>) : []),
            ["Tool calls", a?.toolCalls ?? roll?.tools ?? 0],
            ["Tool errors", a?.toolErrors ?? roll?.errs ?? 0],
          ]}
        />
        {!loaded && <Callout>The subagent&apos;s own model calls load when you expand this row.</Callout>}
        {overlap.length > 0 && (
          <Section label="Ran in parallel with">
            {overlap.map((o) => agentLink(o, `${fmtHm(o.start)}-${fmtHm(o.end)}`))}
          </Section>
        )}
        <Section label="Lineage">
          {lineage.map(([x, text, at]) => (
            <LinkBtn key={`${x.id}-${text}`} onClick={() => p.onSelect(x.id)} text={text} right={real ? fmtClock(at) : undefined} />
          ))}
        </Section>
        {resumes.length > 0 && (
          <Callout>
            Resumed {resumes.length} time{resumes.length > 1 ? "s" : ""} with a follow-up message, so the bar has idle gaps between bursts of work.
          </Callout>
        )}
      </>
    );
  }

  const agentColor = span.kind === "agent" ? colorOf(span.agent?.agentType) : undefined;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <KindChip span={span} color={agentColor} />
        {span.kind === "turn" && span.turnKind === "notification" && <Tag>notification</Tag>}
        {span.kind === "agent" && !span.error && <Tag>{span.agent?.background ? "background" : "foreground"}</Tag>}
        {span.error && <Tag color="var(--tt-danger-fg)">error</Tag>}
      </div>
      <h2 className="break-words text-sm font-semibold text-[var(--tt-fg)]">{span.title}</h2>
      {body}
      {(real || span.eventIndex != null) && (
        <Section label="View">
          {real && <LinkBtn onClick={() => p.onZoom(span)} icon={<ZoomIn size={12} />} text="Zoom timeline to this span" right={fmtDur(span.end - span.start)} />}
          {span.eventIndex != null && p.onJumpToEvent && (
            <LinkBtn onClick={() => p.onJumpToEvent!(span.eventIndex!)} icon={<ExternalLink size={12} />} text="Open step" />
          )}
        </Section>
      )}
    </div>
  );
}

function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <div className={`${SECTION_LABEL} pt-1`}>{label}</div>
      <div className="flex flex-col gap-1">{children}</div>
    </div>
  );
}

function Quote({ children }: { children: ReactNode }) {
  return (
    <blockquote className="max-h-40 overflow-y-auto whitespace-pre-wrap break-words rounded border-l-2 border-[var(--tt-border-strong)] bg-[var(--tt-sunken)] px-2.5 py-2 text-xs leading-relaxed text-[var(--tt-fg-muted)] scrollbar-thin">
      {children}
    </blockquote>
  );
}

function Callout({ children }: { children: ReactNode }) {
  return <p className="text-xs leading-relaxed text-[var(--tt-fg-muted)]">{children}</p>;
}

function Kv({ rows }: { rows: Array<[string, ReactNode]> }) {
  return (
    <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-xs">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-[var(--tt-fg-dim)]">{k}</dt>
          <dd className="break-words text-right font-mono text-[var(--tt-fg)]">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function LinkBtn({ text, right, dot, icon, onClick }: { text: string; right?: string; dot?: string; icon?: ReactNode; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center gap-2 rounded-md border border-[var(--tt-border)] bg-[var(--tt-sunken)] px-2 py-1.5 text-left text-xs text-[var(--tt-fg-muted)] transition-colors hover:border-[var(--tt-border-strong)] hover:text-[var(--tt-fg)]"
    >
      {dot && <span className="size-1.5 shrink-0 rounded-full" style={{ background: dot }} />}
      {icon}
      <span className="min-w-0 flex-1 truncate">{text}</span>
      {right && <span className="shrink-0 font-mono text-[10px] text-[var(--tt-fg-dim)]">{right}</span>}
    </button>
  );
}

const TOKEN_SEGS: Array<[keyof SpanTokens, string, string]> = [
  ["cacheRead", "Cache read", "var(--tt-brand)"],
  ["cacheWrite", "Cache write", "var(--tt-violet-fg)"],
  ["input", "Input", "var(--tt-fg-muted)"],
  ["output", "Output", "var(--tt-cyan-fg)"],
];

function TokenBar({ t }: { t: SpanTokens }) {
  const total = t.input + t.output + t.cacheRead + t.cacheWrite || 1;
  return (
    <div className="space-y-1.5">
      <div className="flex h-2 overflow-hidden rounded-full bg-[var(--tt-sunken)]">
        {TOKEN_SEGS.map(([k, label, c]) =>
          t[k] ? <span key={k} title={`${label}: ${t[k].toLocaleString()}`} style={{ width: `${(t[k] / total) * 100}%`, background: c }} /> : null,
        )}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-[var(--tt-fg-dim)]">
        {TOKEN_SEGS.map(([k, label, c]) => (
          <span key={k} className="inline-flex items-center gap-1">
            <i className="size-1.5 rounded-full" style={{ background: c }} />
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}
