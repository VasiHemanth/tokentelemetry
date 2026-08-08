"""Regression tests for Meta Muse Code and Prime Agent local session scans."""
import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _muse_event(payload_type: str, event: dict, *, recorded_at: int = 1785988885588174) -> dict:
    return {
        "schema_version": 1,
        "id": "event-id",
        "stream": {"kind": "session", "id": "muse-parent"},
        "sequence": 1,
        "recorded_at": recorded_at,
        "record_type": "event",
        "payload_type": payload_type,
        "payload": {"kind": "run", "event": event},
    }


def _write_muse_session(root: Path) -> Path:
    session = root / "2026" / "08" / "06" / "muse-parent" / "session.jsonl"
    _write_jsonl(session, [
        _muse_event("runtime.session.route_facts", {"record": {"cwd": "/tmp/muse-project"}}, recorded_at=1785988000000000),
        _muse_event("run.model.configured", {"record": {"model_id": "muse-spark-1.2-contributor"}}),
        _muse_event("runtime.session", {"model": "muse-spark-1.2-contributor", "usage": {
            "input_tokens": 100, "output_tokens": 20, "cached_tokens": 30,
            "cache_write_tokens": 4, "reasoning_tokens": 5,
        }}),
        # Adjacent accounting records are duplicate turn accounting, not another call.
        _muse_event("runtime.session", {"record": {"quantity": {
            "input_tokens": 100, "output_tokens": 20, "cached_tokens": 30,
        }}}),
        _muse_event("runtime.session", {"child_session_log_path": "subagent/muse-child/session.jsonl"}),
    ])
    _write_jsonl(session.parent / "subagent" / "muse-child" / "session.jsonl", [
        _muse_event("runtime.session", {"model": "muse-spark-1.2-contributor", "usage": {
            "input_tokens": 50, "output_tokens": 10, "cached_tokens": 12,
            "reasoning_tokens": 3,
        }}, recorded_at=1785989000000000),
    ])
    return session


def _write_prime_session(root: Path) -> Path:
    session = root / "prime-parent.jsonl"
    _write_jsonl(session, [
        {"type": "session", "version": 3, "id": "prime-parent", "timestamp": "2026-08-08T04:00:00Z", "cwd": "/tmp/prime-project"},
        {"type": "message", "id": "user-1", "parentId": None, "timestamp": "2026-08-08T04:00:01Z", "message": {"role": "user", "content": "old task"}},
        {"type": "message", "id": "old-assistant", "parentId": "user-1", "timestamp": "2026-08-08T04:00:02Z", "message": {"role": "assistant", "model": "gpt-5.4", "content": [{"type": "text", "text": "old"}], "usage": {"input": 999, "output": 1, "cacheRead": 0, "cacheWrite": 0, "totalTokens": 1000, "cost": {"total": 9.99}}}},
        {"type": "message", "id": "active-user", "parentId": "user-1", "timestamp": "2026-08-08T04:01:00Z", "message": {"role": "user", "content": "integrate traces"}},
        {"type": "message", "id": "active-assistant", "parentId": "active-user", "timestamp": "2026-08-08T04:01:02Z", "message": {"role": "assistant", "model": "gpt-5.4", "content": [{"type": "thinking", "thinking": "check format"}, {"type": "toolCall", "name": "ipython", "arguments": {"code": "1+1"}}], "usage": {"input": 100, "output": 20, "cacheRead": 30, "cacheWrite": 4, "totalTokens": 154, "cost": {"total": 0.12}}}},
        {"type": "child_usage_attributed", "id": "usage-1", "parentId": "active-assistant", "timestamp": "2026-08-08T04:01:03Z", "targetId": "active-assistant", "childUsage": {"input": 50, "output": 5, "cacheRead": 0, "cacheWrite": 0}, "aggregateUsage": {"input": 150, "output": 25, "cacheRead": 30, "cacheWrite": 4, "totalTokens": 209, "cost": {"total": 0.18}}},
    ])
    return session


def test_scan_muse_uses_cwd_and_keeps_child_tokens_out_of_parent_totals(tmp_path, monkeypatch):
    _write_muse_session(tmp_path / "muse")
    monkeypatch.setattr(main, "MUSE_SESSIONS_DIR", tmp_path / "muse")

    sessions = main._scan_muse_sessions()

    assert len(sessions) == 1
    rec = sessions[0]
    assert rec["agent"] == "muse"
    assert rec["project"] == "/tmp/muse-project"
    assert rec["model"] == "muse-spark-1.2-contributor"
    assert rec["tokens"] == {
        "input": 100, "output": 20, "cached": 30, "cache_creation": 4,
        "reasoning": 5, "total": 159, "cost": rec["tokens"]["cost"],
    }
    assert rec["delegation"]["spawn_count"] == 1
    assert rec["delegation"]["delegated_total"] == 75


def test_scan_prime_counts_only_active_branch_and_uses_reported_cost(tmp_path, monkeypatch):
    _write_prime_session(tmp_path / "prime")
    monkeypatch.setattr(main, "PRIME_SESSIONS_DIR", tmp_path / "prime")

    sessions = main._scan_prime_sessions()

    assert len(sessions) == 1
    rec = sessions[0]
    assert rec["agent"] == "prime"
    assert rec["project"] == "/tmp/prime-project"
    assert rec["display"] == "integrate traces"
    assert rec["tokens"]["input"] == 150
    assert rec["tokens"]["output"] == 25
    assert rec["tokens"]["cached"] == 30
    assert rec["tokens"]["cache_creation"] == 4
    assert rec["tokens"]["total"] == 209
    assert rec["cost"] == pytest.approx(0.18)
    assert rec["cost_source"] == "reported"
    assert rec["prime"]["branch_count"] == 2
    assert rec["mcp_tools"] == ["ipython"]


def test_session_detail_prime_normalizes_active_tree_messages(tmp_path, monkeypatch):
    _write_prime_session(tmp_path / "prime")
    monkeypatch.setattr(main, "PRIME_SESSIONS_DIR", tmp_path / "prime")

    events = asyncio.run(main.get_session_detail("prime-parent", "prime"))

    assert [event["type"] for event in events] == ["user", "user", "assistant_thinking", "tool_call"]
    assert events[-1]["payload"]["tool"] == "ipython"


def test_muse_delegation_exposes_child_trace(tmp_path, monkeypatch):
    _write_muse_session(tmp_path / "muse")
    monkeypatch.setattr(main, "MUSE_SESSIONS_DIR", tmp_path / "muse")

    delegation = asyncio.run(main.session_delegation("muse-parent", "muse"))
    child_events = asyncio.run(main.session_subagent_trace("muse-parent", "muse-child", "muse"))

    assert delegation["spawn_count"] == 1
    assert delegation["totals"]["total"] == 75
    assert child_events[-1]["type"] == "usage"
