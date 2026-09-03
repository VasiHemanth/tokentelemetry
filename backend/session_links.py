"""Peer messages between two local agent sessions — the edges of a session graph.

Claude Code sessions running on one machine can message each other. Both sides
record their own half of the exchange, and NEITHER half names the other by
session id:

* the SENDER writes an assistant row holding a ``SendMessage`` ``tool_use``
  whose ``input.to`` is whatever the model typed — a display name with a short
  ref (``"Some session [37079d]"``) or a raw socket
  (``"uds:/tmp/cc-socks/4878.sock"``). The matching ``tool_result`` carries the
  delivery receipt, including ``msg_id``.
* the RECEIVER writes a user row whose ``origin`` is a structured envelope:
  ``{kind: "peer", msg_id, name, verifiedPeerPid, hopChain, fromMode, body}``.

``msg_id`` is the ONLY value both sides record, which makes it the join key.
Matching on display name would mis-attach the moment two sessions share a name
(they are user-chosen and not unique), and matching on timestamp would break
under concurrent sends — both halves of a real exchange land within ~100ms, so
a time window cannot separate two conversations happening at once.

An edge is emitted even when only one half is found. A session's transcript is
deleted, rotated, or simply lives outside the scanned directory often enough
that dropping half-edges would silently under-report the graph; ``resolved``
says which case a row is, so the UI can render the difference rather than
pretend a one-sided edge is complete.

WHY THIS IS NOT PART OF THE MAIN SESSION SCAN
Peer messages are sparse: 2 across 100 transcripts (230 MB) on the development
machine. Folding a new field into the session scan would force a
``scan_cache.CACHE_VERSION`` bump, re-parsing the user's ENTIRE history to
surface a rare relationship. Instead this module owns a small mtime-keyed cache
of its own. A substring prefilter (checked before any JSON decoding) keeps a
cold full scan under ~1s over that same 230 MB, because only ~300 of several
million lines survive the filter.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger("tokentelemetry.session_links")

# Only lines containing one of these can possibly be a peer send or receive.
# Checked as a raw substring against the undecoded line: json.loads() on every
# line of a 230 MB tree is the entire cost of this scan, and this skips ~99.99%
# of them. '"peer"' is quoted to avoid matching the word inside prose.
#
# "msg_id" is load-bearing and easy to omit by mistake: a SendMessage
# tool_result names neither the tool nor the peer, so a filter of just
# ('"peer"', "SendMessage") drops every delivery receipt, and with it every
# msg_id — leaving each send unjoinable and the graph one-sided.
_PREFILTER = ('"peer"', "SendMessage", "msg_id")

# A message body is arbitrary text the peer wrote. The endpoint returns a short
# preview so the UI can show what an exchange was ABOUT without shipping a
# multi-kilobyte body into a list view; full text stays in the session detail.
PREVIEW_CHARS = 240


def _preview(text: Any) -> str:
    """First meaningful line of a body, collapsed and truncated for a list row."""
    if not isinstance(text, str):
        return ""
    # Peer messages lead with a self-contained summary line by convention, so
    # the first non-empty line is the most informative thing to show.
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line:
            return line[:PREVIEW_CHARS] + ("…" if len(line) > PREVIEW_CHARS else "")
    return ""


def _msg_id_from_result(block: Dict[str, Any], row: Dict[str, Any]) -> Optional[str]:
    """Pull the delivery receipt's ``msg_id`` out of a SendMessage tool_result.

    Two encodings carry it and neither is guaranteed, so both are tried. The
    row-level ``toolUseResult`` is the structured form; ``content[].text`` holds
    the same payload as a JSON *string* and is what older transcripts have.
    """
    structured = row.get("toolUseResult")
    if isinstance(structured, dict):
        candidate = structured.get("msg_id")
        if isinstance(candidate, str) and candidate:
            return candidate
    content = block.get("content")
    if isinstance(content, list):
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "text":
                continue
            text = part.get("text")
            if not isinstance(text, str) or "msg_id" not in text:
                continue
            try:
                payload = json.loads(text)
            except (TypeError, ValueError):
                continue
            if isinstance(payload, dict):
                candidate = payload.get("msg_id")
                if isinstance(candidate, str) and candidate:
                    return candidate
    return None


def parse_transcript(path: Path) -> Dict[str, Any]:
    """Extract every peer send and receive from one transcript.

    Returns ``{"session": <id>, "cwd": <str|None>, "sent": [...], "received": [...]}``.
    A send is only reported once its receipt is found: the ``tool_use`` supplies
    the address and the human-readable summary, the ``tool_result`` supplies the
    ``msg_id`` that lets it be joined, and an edge keyed on nothing is useless.

    ``cwd`` is taken from the rows that carry peer events, latest wins — NOT from
    the first row of the file. A session can move between directories (a resumed
    session, or one that entered a worktree mid-run), so the opening cwd can name
    a directory the session had already left by the time it spoke to a peer.
    """
    session_id = path.stem
    cwd: Optional[str] = None
    # tool_use id -> the parts of the send known before its receipt arrives.
    pending: Dict[str, Dict[str, Any]] = {}
    sent: List[Dict[str, Any]] = []
    received: List[Dict[str, Any]] = []

    try:
        handle = open(path, "r", encoding="utf-8", errors="replace")
    except OSError as exc:  # unreadable transcript must never break the scan
        logger.debug("session_links: cannot open %s (%s)", path, exc)
        return {"session": session_id, "cwd": None, "sent": [], "received": []}

    with handle:
        for line in handle:
            if not any(token in line for token in _PREFILTER):
                continue
            try:
                row = json.loads(line)
            except (TypeError, ValueError):
                continue
            if not isinstance(row, dict):
                continue
            row_cwd = row.get("cwd") if isinstance(row.get("cwd"), str) else None

            origin = row.get("origin")
            if isinstance(origin, dict) and origin.get("kind") == "peer":
                body = origin.get("body")
                cwd = row_cwd or cwd
                received.append({
                    "msg_id": origin.get("msg_id"),
                    "from_name": origin.get("name"),
                    "from_address": origin.get("from"),
                    "from_pid": origin.get("verifiedPeerPid"),
                    "from_mode": origin.get("fromMode"),
                    # A hop chain longer than one means the message was relayed
                    # rather than sent directly, which changes what the edge means.
                    "hops": len(origin.get("hopChain") or []),
                    "at": row.get("timestamp"),
                    "chars": len(body) if isinstance(body, str) else 0,
                    "preview": _preview(body),
                })
                continue

            content = (row.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use" and block.get("name") == "SendMessage":
                    payload = block.get("input") or {}
                    message = payload.get("message")
                    cwd = row_cwd or cwd
                    pending[block.get("id")] = {
                        "to_address": payload.get("to"),
                        "summary": payload.get("summary"),
                        "at": row.get("timestamp"),
                        "chars": len(message) if isinstance(message, str) else 0,
                        "preview": _preview(message),
                    }
                elif block.get("type") == "tool_result":
                    record = pending.pop(block.get("tool_use_id"), None)
                    if record is None:
                        continue
                    msg_id = _msg_id_from_result(block, row)
                    if msg_id:
                        record["msg_id"] = msg_id
                        sent.append(record)
                    # No receipt means nothing was delivered, so there is no
                    # edge to draw. The common case is a pure idle-notification
                    # subscription: it is a real SendMessage call with no
                    # message body, and counting it would inflate "sent" with
                    # exchanges that never carried anything.

    return {"session": session_id, "cwd": cwd, "sent": sent, "received": received}


# path -> ((mtime_ns, size), parsed). Transcripts are append-only while a
# session is live, so any size change is a real change and a re-parse is cheap.
_CACHE: Dict[str, Tuple[Tuple[int, int], Dict[str, Any]]] = {}
_CACHE_MAX = 512


def _parse_cached(path: Path) -> Dict[str, Any]:
    try:
        stat = path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        return parse_transcript(path)
    key = str(path)
    hit = _CACHE.get(key)
    if hit is not None and hit[0] == stamp:
        return hit[1]
    parsed = parse_transcript(path)
    if key not in _CACHE and len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = (stamp, parsed)
    return parsed


def clear_cache() -> None:
    """Drop the parse cache. Tests reuse file names across temp dirs."""
    _CACHE.clear()


def _transcripts(projects_dir: Path) -> Iterable[Path]:
    if not projects_dir.is_dir():
        return []
    return sorted(projects_dir.glob("*/*.jsonl"))


def build_graph(projects_dir: Path) -> Dict[str, Any]:
    """Join both halves of every peer exchange into a session-to-session graph.

    Nodes are sessions that sent or received at least once; a session with no
    peer traffic is not part of this graph and is deliberately absent rather
    than present with zero counts.
    """
    by_msg: Dict[str, Dict[str, Any]] = {}
    nodes: Dict[str, Dict[str, Any]] = {}
    unjoinable: List[Dict[str, Any]] = []

    def node(session_id: str, cwd: Optional[str]) -> Dict[str, Any]:
        entry = nodes.get(session_id)
        if entry is None:
            entry = {"session": session_id, "cwd": cwd, "sent": 0, "received": 0, "peers": set()}
            nodes[session_id] = entry
        elif entry["cwd"] is None and cwd:
            entry["cwd"] = cwd
        return entry

    def edge(msg_id: str) -> Dict[str, Any]:
        entry = by_msg.get(msg_id)
        if entry is None:
            entry = {
                "msg_id": msg_id, "from_session": None, "to_session": None,
                "from_cwd": None, "to_cwd": None, "from_name": None,
                "to_address": None, "summary": None, "preview": "", "chars": 0,
                "sent_at": None, "received_at": None, "hops": None,
                "from_mode": None, "resolved": False,
            }
            by_msg[msg_id] = entry
        return entry

    for path in _transcripts(projects_dir):
        parsed = _parse_cached(path)
        session_id, cwd = parsed["session"], parsed["cwd"]
        if not parsed["sent"] and not parsed["received"]:
            continue
        entry = node(session_id, cwd)

        for record in parsed["sent"]:
            entry["sent"] += 1
            link = edge(record["msg_id"])
            link["from_session"] = session_id
            link["from_cwd"] = cwd
            link["to_address"] = record.get("to_address")
            link["summary"] = record.get("summary")
            link["sent_at"] = record.get("at")
            # The sender holds the message it actually composed, so its preview
            # and length win over the receiver's copy when both exist.
            link["preview"] = record.get("preview") or link["preview"]
            link["chars"] = record.get("chars") or link["chars"]

        for record in parsed["received"]:
            entry["received"] += 1
            msg_id = record.get("msg_id")
            if not msg_id:
                # No join key: countable, but it can never become an edge.
                unjoinable.append({"session": session_id, "from_name": record.get("from_name"),
                                   "at": record.get("at")})
                continue
            link = edge(msg_id)
            link["to_session"] = session_id
            link["to_cwd"] = cwd
            link["from_name"] = record.get("from_name")
            link["received_at"] = record.get("at")
            link["hops"] = record.get("hops")
            link["from_mode"] = record.get("from_mode")
            if not link["preview"]:
                link["preview"] = record.get("preview") or ""
            if not link["chars"]:
                link["chars"] = record.get("chars") or 0

    edges = []
    for link in by_msg.values():
        link["resolved"] = bool(link["from_session"] and link["to_session"])
        if link["from_session"] and link["to_session"]:
            nodes[link["from_session"]]["peers"].add(link["to_session"])
            nodes[link["to_session"]]["peers"].add(link["from_session"])
        edges.append(link)

    # Newest first: a peer conversation is read like a log, and an unsent edge
    # (received_at only) still has a usable time.
    edges.sort(key=lambda e: e.get("sent_at") or e.get("received_at") or "", reverse=True)

    node_list = []
    for entry in nodes.values():
        node_list.append({**entry, "peers": sorted(entry["peers"]),
                          "peer_count": len(entry["peers"])})
    node_list.sort(key=lambda n: (n["sent"] + n["received"]), reverse=True)

    return {
        "edges": edges,
        "nodes": node_list,
        "totals": {
            "edges": len(edges),
            "resolved": sum(1 for e in edges if e["resolved"]),
            "sessions": len(node_list),
            # Surfaced rather than hidden: a non-zero value here means the graph
            # is knowably incomplete, which is different from having no traffic.
            "unjoinable_receives": len(unjoinable),
        },
    }
