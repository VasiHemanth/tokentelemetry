/**
 * Peer messages between two local agent sessions (GET /sessions/links).
 *
 * Each side of an exchange records only its own half, and the backend joins them
 * on the delivery receipt's `msg_id`. An edge whose halves could not both be
 * found is still returned, with `resolved: false` — see `SessionLinkEdge`.
 */

export interface SessionLinkEdge {
  msg_id: string;
  /** Null when the sender's transcript was not found on disk. */
  from_session: string | null;
  /** Null when the recipient's transcript was not found on disk. */
  to_session: string | null;
  from_cwd: string | null;
  to_cwd: string | null;
  /** Display name the RECEIVER saw. Absent on a send whose receipt is missing. */
  from_name: string | null;
  /** Whatever the sender typed as an address: a display name, or a raw socket. */
  to_address: string | null;
  /** The sender's own one-line label for the message. */
  summary: string | null;
  preview: string;
  chars: number;
  sent_at: string | null;
  received_at: string | null;
  /** >1 means the message was relayed rather than delivered directly. */
  hops: number | null;
  from_mode: string | null;
  /** True only when BOTH transcripts were found and joined. */
  resolved: boolean;
}

export interface SessionLinkNode {
  session: string;
  cwd: string | null;
  /** Display name, learned from messages this session SENT (only the receiving
   *  side records a peer's name). Null when it never sent to a session on disk. */
  name: string | null;
  sent: number;
  received: number;
  peers: string[];
  peer_count: number;
}

export interface SessionLinkGraph {
  edges: SessionLinkEdge[];
  nodes: SessionLinkNode[];
  totals: {
    edges: number;
    resolved: number;
    sessions: number;
    /** Non-zero means the graph is knowably incomplete, not merely empty. */
    unjoinable_receives: number;
  };
}

/** Edges where `id` is either end, newest first (the backend already sorts). */
export function edgesFor(graph: SessionLinkGraph | undefined, id: string): SessionLinkEdge[] {
  if (!graph) return [];
  return graph.edges.filter((e) => e.from_session === id || e.to_session === id);
}

/**
 * How an edge reads from one session's point of view.
 *
 * A session can appear on either end, so direction is relative rather than a
 * property of the edge itself.
 */
export function directionFor(edge: SessionLinkEdge, id: string): "sent" | "received" {
  return edge.from_session === id ? "sent" : "received";
}

/** session id -> display name, for labelling an end the edge itself only has an address for. */
export function nameIndex(graph: SessionLinkGraph | undefined): Record<string, string> {
  const index: Record<string, string> = {};
  for (const node of graph?.nodes ?? []) {
    if (node.name) index[node.session] = node.name;
  }
  return index;
}

/**
 * The other end's label, from `id`'s point of view.
 *
 * Falls back through what each half recorded: the receiver knows the sender's
 * display name, the sender only knows the address it typed. That address is
 * whatever the model wrote, and when a session replies it is often a raw
 * "uds:/tmp/cc-socks/<pid>.sock" — accurate but unreadable, so a name learned
 * from any other edge wins over it. When nothing identifies the peer, say so
 * rather than render an empty cell.
 */
export function peerLabel(
  edge: SessionLinkEdge,
  id: string,
  names: Record<string, string> = {},
): string {
  const peerId = peerSessionId(edge, id);
  if (peerId && names[peerId]) return names[peerId];
  if (directionFor(edge, id) === "sent") {
    return edge.to_address || edge.to_session || "unknown session";
  }
  return edge.from_name || edge.from_session || "unknown session";
}

/** The peer's session id, when its transcript was found. */
export function peerSessionId(edge: SessionLinkEdge, id: string): string | null {
  return directionFor(edge, id) === "sent" ? edge.to_session : edge.from_session;
}

/**
 * Delivery latency in ms, or null when a half is missing.
 *
 * Both clocks are the same machine's, so this is a real measurement rather than
 * a cross-host comparison.
 */
export function latencyMs(edge: SessionLinkEdge): number | null {
  if (!edge.sent_at || !edge.received_at) return null;
  const delta = Date.parse(edge.received_at) - Date.parse(edge.sent_at);
  return Number.isFinite(delta) ? delta : null;
}
