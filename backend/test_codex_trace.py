"""Regression tests for Codex rollout mirror filtering."""

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402


def _write_rollout(root: Path, session_id: str, events: list[dict]) -> None:
    path = root / "sessions" / "2026" / "08" / f"rollout-test-{session_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")


def test_codex_detail_removes_event_msg_mirrors(tmp_path, monkeypatch):
    session_id = "duplicate-trace"
    events = [
        {
            "timestamp": "2026-08-07T10:00:00.000Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Fix the trace"}],
            },
        },
        {
            "timestamp": "2026-08-07T10:00:00.010Z",
            "type": "event_msg",
            "payload": {"type": "user_message", "message": "Fix the trace"},
        },
        {
            "timestamp": "2026-08-07T10:00:01.000Z",
            "type": "response_item",
            "payload": {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "Checking"}],
            },
        },
        {
            "timestamp": "2026-08-07T10:00:01.010Z",
            "type": "event_msg",
            "payload": {"type": "agent_reasoning", "text": "Checking"},
        },
        {
            "timestamp": "2026-08-07T10:00:02.000Z",
            "type": "event_msg",
            "payload": {"type": "agent_message", "message": "Done"},
        },
        {
            "timestamp": "2026-08-07T10:00:02.010Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Done"}],
            },
        },
    ]
    _write_rollout(tmp_path, session_id, events)
    monkeypatch.setattr(main, "CODEX_DIR", tmp_path)

    result = asyncio.run(main.get_session_detail(session_id, "codex"))

    assert [event["type"] for event in result] == [
        "response_item",
        "response_item",
        "response_item",
    ]


def test_codex_detail_keeps_event_only_records(tmp_path, monkeypatch):
    session_id = "legacy-trace"
    events = [
        {
            "timestamp": "2025-01-01T00:00:00Z",
            "type": "event_msg",
            "payload": {"type": "user_message", "message": "Legacy prompt"},
        },
        {
            "timestamp": "2025-01-01T00:00:01Z",
            "type": "event_msg",
            "payload": {"type": "agent_message", "message": "Legacy answer"},
        },
    ]
    _write_rollout(tmp_path, session_id, events)
    monkeypatch.setattr(main, "CODEX_DIR", tmp_path)

    result = asyncio.run(main.get_session_detail(session_id, "codex"))

    assert len(result) == 2


def test_codex_detail_collapses_empty_and_streaming_reasoning_snapshots():
    events = [
        {
            "type": "response_item",
            "payload": {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "Planning"}],
            },
        },
        {
            "type": "event_msg",
            "payload": {"type": "agent_reasoning", "text": "Planning"},
        },
        {
            "type": "response_item",
            "payload": {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "Planning"}],
            },
        },
        {
            "type": "response_item",
            "payload": {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "Planning the fix"}],
            },
        },
        {
            "type": "response_item",
            "payload": {"type": "reasoning", "summary": []},
        },
    ]

    result = main._canonicalize_codex_trace(events)

    assert len(result) == 1
    assert result[0]["payload"]["summary"][0]["text"] == "Planning the fix"
