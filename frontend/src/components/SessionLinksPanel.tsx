"use client";

/**
 * Peer messages this session exchanged with other local agent sessions.
 *
 * Renders nothing at all when the session has no peer traffic. That is the
 * overwhelmingly common case (2 exchanges across 100 transcripts on the
 * development machine), and an empty "no messages" card on every session detail
 * page would be noise on a page that is already dense.
 */

import React from "react";
import Link from "next/link";
import { ArrowDownLeft, ArrowUpRight, Radio, Unlink } from "lucide-react";
import { useResource } from "@/lib/api";
import {
  SessionLinkGraph,
  edgesFor,
  directionFor,
  peerLabel,
  peerSessionId,
  nameIndex,
  latencyMs,
} from "@/lib/sessionLinks";

function shortId(id: string): string {
  return id.slice(0, 8);
}

function whenLabel(iso: string | null): string {
  if (!iso) return "";
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return "";
  // Local time on purpose: these are events on the user's own machine, and a
  // UTC rendering would disagree with every other clock they can see.
  return at.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function SessionLinksPanel({ sessionId }: { sessionId: string }) {
  // No polling. Peer traffic is rare and the page is already poll-heavy; a
  // stale edge costs the reader nothing, and re-scanning transcripts on a timer
  // would be pure waste.
  const { data } = useResource<SessionLinkGraph>("/sessions/links");
  const edges = edgesFor(data, sessionId);
  // Built from the whole graph, not just this session's edges: a peer's name is
  // recorded by whoever RECEIVED from it, which may be an exchange this session
  // was not part of.
  const names = React.useMemo(() => nameIndex(data), [data]);

  if (edges.length === 0) return null;

  return (
    <div
      className="rounded-[var(--tt-radius-lg)] border p-4"
      style={{ borderColor: "var(--tt-border)", background: "var(--tt-panel)" }}
    >
      <div className="mb-3 flex items-center gap-2">
        <Radio size={15} style={{ color: "var(--tt-brand)" }} aria-hidden />
        <h3 className="text-sm font-medium" style={{ color: "var(--tt-fg)" }}>
          Peer messages
        </h3>
        <span className="text-xs" style={{ color: "var(--tt-fg-dim)" }}>
          {edges.length} with {new Set(edges.map((e) => peerSessionId(e, sessionId) ?? peerLabel(e, sessionId, names))).size} session
          {new Set(edges.map((e) => peerSessionId(e, sessionId) ?? peerLabel(e, sessionId, names))).size === 1 ? "" : "s"}
        </span>
      </div>

      <ul className="flex flex-col gap-2">
        {edges.map((edge) => {
          const direction = directionFor(edge, sessionId);
          const outbound = direction === "sent";
          const peerId = peerSessionId(edge, sessionId);
          const latency = latencyMs(edge);
          const Icon = outbound ? ArrowUpRight : ArrowDownLeft;
          return (
            <li
              key={edge.msg_id}
              className="rounded-[var(--tt-radius)] border p-2.5"
              style={{ borderColor: "var(--tt-border)", background: "var(--tt-sunken)" }}
            >
              <div className="flex items-center gap-2 text-xs">
                <Icon size={13} aria-hidden style={{ color: "var(--tt-brand)" }} />
                <span style={{ color: "var(--tt-fg-muted)" }}>{outbound ? "to" : "from"}</span>
                {peerId ? (
                  <Link
                    href={`/sessions/${peerId}?from=/sessions/${sessionId}`}
                    className="font-medium underline underline-offset-2"
                    style={{ color: "var(--tt-fg)" }}
                  >
                    {peerLabel(edge, sessionId, names)}
                  </Link>
                ) : (
                  <span className="font-medium" style={{ color: "var(--tt-fg)" }}>
                    {peerLabel(edge, sessionId, names)}
                  </span>
                )}
                {peerId && (
                  <span className="font-mono" style={{ color: "var(--tt-fg-faint)" }}>
                    {shortId(peerId)}
                  </span>
                )}
                <span className="ml-auto" style={{ color: "var(--tt-fg-dim)" }}>
                  {whenLabel(outbound ? edge.sent_at : edge.received_at)}
                </span>
              </div>

              {edge.summary && (
                <div className="mt-1.5 text-xs font-medium" style={{ color: "var(--tt-fg)" }}>
                  {edge.summary}
                </div>
              )}
              {edge.preview && (
                <p className="mt-1 text-xs leading-snug" style={{ color: "var(--tt-fg-muted)" }}>
                  {edge.preview}
                </p>
              )}

              <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]"
                   style={{ color: "var(--tt-fg-dim)" }}>
                <span>{edge.chars.toLocaleString()} chars</span>
                {latency !== null && <span>delivered in {latency} ms</span>}
                {/* A relayed message did not come straight from the named peer. */}
                {edge.hops !== null && edge.hops > 1 && <span>relayed via {edge.hops} hops</span>}
                {!edge.resolved && (
                  <span className="inline-flex items-center gap-1" style={{ color: "var(--tt-fg-muted)" }}>
                    <Unlink size={10} aria-hidden />
                    {/* Says why a peer has no link, so a missing transcript does
                        not read as a rendering bug. */}
                    other half not found on disk
                  </span>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
