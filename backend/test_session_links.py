"""Tests for cross-session peer messages (session_links).

Two Claude sessions on one machine can message each other, and each side records
only its own half. Covers:
  - build_graph(): both halves join on msg_id into one resolved edge.
  - the prefilter reaches a delivery receipt, which names neither the tool
    nor the peer (the bug that made every send unjoinable).
  - cwd is the directory a session was in when it spoke, not the one it opened in.
  - a half-edge stays visible and is marked unresolved rather than dropped.
  - a SendMessage that delivered nothing (an idle subscription) is not an edge.
  - a receive with no msg_id is counted, not silently discarded.
  - the mtime cache re-parses an appended transcript.

Run: pytest backend/test_session_links.py
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import session_links  # noqa: E402


SENDER = "aaaaaaaa-0000-0000-0000-000000000001"
RECEIVER = "bbbbbbbb-0000-0000-0000-000000000002"


@pytest.fixture(autouse=True)
def _clear_cache():
    # Temp dirs reuse file names across tests, and the cache is keyed by path.
    session_links.clear_cache()
    yield
    session_links.clear_cache()


def _write(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _send_rows(msg_id, to, summary, body, cwd, at="2026-09-02T17:55:06.306Z"):
    """The sender's two rows: the tool_use, then its delivery receipt.

    The receipt deliberately mentions neither "SendMessage" nor "peer" — that is
    exactly how the real transcript looks, and why the prefilter needs msg_id.
    """
    return [
        {"type": "assistant", "timestamp": at, "cwd": cwd,
         "message": {"content": [
             {"type": "tool_use", "id": "toolu_1", "name": "SendMessage",
              "input": {"to": to, "summary": summary, "message": body}}]}},
        {"type": "user", "timestamp": at, "cwd": cwd,
         "toolUseResult": {"success": True, "msg_id": msg_id},
         "message": {"content": [
             {"type": "tool_result", "tool_use_id": "toolu_1",
              "content": [{"type": "text",
                           "text": json.dumps({"success": True, "msg_id": msg_id})}]}]}},
    ]


def _receive_row(msg_id, from_name, body, cwd, at="2026-09-02T17:55:06.402Z", hops=1):
    return {"type": "user", "timestamp": at, "cwd": cwd, "userType": "external",
            "origin": {"kind": "peer", "from": "uds:/tmp/cc-socks/4878.sock",
                       "verifiedPeerPid": 4878, "msg_id": msg_id, "name": from_name,
                       "hopChain": ["a" * 24] * hops, "fromMode": "bypass",
                       "body": body}}


def test_both_halves_join_on_msg_id_into_one_edge(tmp_path):
    """The join key is msg_id, and it is the only value both sides record.

    The sender addresses the peer by display name and the receiver identifies it
    by pid and socket; neither names a session id, so nothing but msg_id can
    connect the two rows.
    """
    _write(tmp_path / "proj-a" / f"{SENDER}.jsonl",
           _send_rows("msg-1", "Peer session [37079d]", "ask about design",
                      "Need your conclusions.\nMore detail here.", "/w/a"))
    _write(tmp_path / "proj-b" / f"{RECEIVER}.jsonl",
           [_receive_row("msg-1", "sender session", "Need your conclusions.", "/w/b")])

    graph = session_links.build_graph(tmp_path)

    assert graph["totals"] == {"edges": 1, "resolved": 1, "sessions": 2,
                               "unjoinable_receives": 0}
    edge = graph["edges"][0]
    assert edge["from_session"] == SENDER
    assert edge["to_session"] == RECEIVER
    assert edge["resolved"] is True
    assert edge["from_cwd"] == "/w/a"
    assert edge["to_cwd"] == "/w/b"
    # The sender's own label for the message, which the receiver never sees.
    assert edge["summary"] == "ask about design"
    assert edge["to_address"] == "Peer session [37079d]"
    assert edge["from_name"] == "sender session"
    # Preview comes from the sender's composed text, first non-empty line only.
    assert edge["preview"] == "Need your conclusions."
    assert edge["hops"] == 1

    by_id = {n["session"]: n for n in graph["nodes"]}
    assert by_id[SENDER]["sent"] == 1 and by_id[SENDER]["received"] == 0
    assert by_id[RECEIVER]["received"] == 1 and by_id[RECEIVER]["sent"] == 0
    assert by_id[SENDER]["peers"] == [RECEIVER]
    assert by_id[RECEIVER]["peers"] == [SENDER]


def test_prefilter_reaches_a_receipt_that_names_neither_the_tool_nor_a_peer(tmp_path):
    """Regression: a delivery receipt contains no "SendMessage" and no "peer".

    Filtering on only those two tokens skips the receipt, so msg_id is never
    found, every send is dropped, and the graph silently renders one-sided.
    """
    rows = _send_rows("msg-1", "Peer [37079d]", "s", "body", "/w/a")
    receipt = json.dumps(rows[1])
    assert "SendMessage" not in receipt and '"peer"' not in receipt
    assert "msg_id" in receipt  # the only usable token

    _write(tmp_path / "proj-a" / f"{SENDER}.jsonl", rows)
    graph = session_links.build_graph(tmp_path)

    assert graph["nodes"][0]["sent"] == 1
    assert graph["edges"][0]["msg_id"] == "msg-1"


def test_cwd_is_where_the_session_spoke_not_where_it_opened(tmp_path):
    """A resumed session can change directory, so the first row's cwd can be stale.

    Taking the opening cwd attributes the exchange to a directory the session had
    already left.
    """
    rows = [
        # An early, unrelated row that still trips the prefilter.
        {"type": "user", "timestamp": "2026-09-02T10:00:00.000Z", "cwd": "/w/old",
         "message": {"content": [{"type": "text", "text": "mentions SendMessage"}]}},
    ] + _send_rows("msg-1", "Peer [37079d]", "s", "body", "/w/new")
    _write(tmp_path / "proj-a" / f"{SENDER}.jsonl", rows)

    graph = session_links.build_graph(tmp_path)

    assert graph["nodes"][0]["cwd"] == "/w/new"
    assert graph["edges"][0]["from_cwd"] == "/w/new"


def test_a_half_edge_is_kept_and_marked_unresolved(tmp_path):
    """Only one transcript is present, so the peer's side cannot be found.

    Dropping it would under-report the graph; the UI needs to tell "no traffic"
    apart from "traffic whose other half we cannot see".
    """
    _write(tmp_path / "proj-b" / f"{RECEIVER}.jsonl",
           [_receive_row("msg-1", "a session not on disk", "hello", "/w/b")])

    graph = session_links.build_graph(tmp_path)

    assert graph["totals"]["edges"] == 1
    assert graph["totals"]["resolved"] == 0
    edge = graph["edges"][0]
    assert edge["resolved"] is False
    assert edge["from_session"] is None
    assert edge["to_session"] == RECEIVER
    assert edge["from_name"] == "a session not on disk"
    # A one-sided edge still connects nothing, so no peer is claimed.
    assert graph["nodes"][0]["peers"] == []


def test_a_send_that_delivered_nothing_is_not_an_edge(tmp_path):
    """A pure idle-notification subscription is a SendMessage with no receipt.

    It carries no message, so counting it would inflate "sent" with exchanges
    that never happened.
    """
    _write(tmp_path / "proj-a" / f"{SENDER}.jsonl", [
        {"type": "assistant", "timestamp": "2026-09-02T17:55:00.000Z", "cwd": "/w/a",
         "message": {"content": [
             {"type": "tool_use", "id": "toolu_9", "name": "SendMessage",
              "input": {"to": "Peer [37079d]"}}]}},
        {"type": "user", "timestamp": "2026-09-02T17:55:00.100Z", "cwd": "/w/a",
         "toolUseResult": {"success": True, "message": "Subscribed"},
         "message": {"content": [
             {"type": "tool_result", "tool_use_id": "toolu_9",
              "content": [{"type": "text", "text": "Subscribed — will notify when idle."}]}]}},
    ])

    graph = session_links.build_graph(tmp_path)

    assert graph["totals"]["edges"] == 0
    assert graph["nodes"] == []


def test_a_receive_without_a_join_key_is_counted_not_discarded(tmp_path):
    """No msg_id means the edge can never be completed, but it did happen.

    Reporting it in totals keeps "the graph is incomplete" visible instead of
    quietly shrinking the result.
    """
    row = _receive_row("msg-x", "peer", "hi", "/w/b")
    del row["origin"]["msg_id"]
    _write(tmp_path / "proj-b" / f"{RECEIVER}.jsonl", [row])

    graph = session_links.build_graph(tmp_path)

    assert graph["totals"]["unjoinable_receives"] == 1
    assert graph["totals"]["edges"] == 0
    assert graph["nodes"][0]["received"] == 1


def test_appending_to_a_transcript_invalidates_the_cache(tmp_path):
    """Transcripts are append-only while a session is live, so size changes."""
    path = tmp_path / "proj-a" / f"{SENDER}.jsonl"
    _write(path, _send_rows("msg-1", "Peer [37079d]", "s", "one", "/w/a"))
    assert session_links.build_graph(tmp_path)["totals"]["edges"] == 1

    rows = _send_rows("msg-2", "Peer [37079d]", "s", "two", "/w/a",
                      at="2026-09-02T18:00:00.000Z")
    for row in rows:  # a second exchange, distinct tool_use id
        for block in row["message"]["content"]:
            block["id" if block.get("type") == "tool_use" else "tool_use_id"] = "toolu_2"
    with open(path, "a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")

    graph = session_links.build_graph(tmp_path)
    assert graph["totals"]["edges"] == 2
    # Newest first.
    assert graph["edges"][0]["msg_id"] == "msg-2"


def test_a_directory_with_no_peer_traffic_yields_an_empty_graph(tmp_path):
    _write(tmp_path / "proj-a" / f"{SENDER}.jsonl", [
        {"type": "user", "timestamp": "2026-09-02T10:00:00.000Z", "cwd": "/w/a",
         "message": {"content": [{"type": "text", "text": "ordinary turn"}]}}])

    graph = session_links.build_graph(tmp_path)

    assert graph == {"edges": [], "nodes": [],
                     "totals": {"edges": 0, "resolved": 0, "sessions": 0,
                                "unjoinable_receives": 0}}


def test_a_missing_projects_directory_is_not_an_error(tmp_path):
    graph = session_links.build_graph(tmp_path / "does-not-exist")
    assert graph["totals"]["edges"] == 0
