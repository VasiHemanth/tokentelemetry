"""Tests for DeepSeek Harness (DSH) session scanning.

DSH (npm @deepseek-ai/dsh, binary `dsh`) writes one zstd-compressed JSONL per
session under ~/.dsh/sessions/<slugged-cwd>/<id>/session.jsonl.zstd. Event
shapes here (header fields, assistant/chunk usage samples, assistant/message
usage, request/context, tool/call) are verified against real on-disk DSH
output, not guessed from docs.

Run: pytest backend/test_dsh_scan.py -q
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402

zstandard = pytest.importorskip("zstandard")


def _write_dsh_session(sessions_dir, workspace_slug, session_id, header_extra,
                        events, project="/Users/dev/project"):
    """Write one zstd-compressed session.jsonl under sessions_dir/<workspace_slug>/<id>/.

    `header_extra` merges into the required {type:"session", id, cwd,
    createdAt, delegationDepth, agentPreset} header. `events` is a list of
    {type, data, time} dicts appended after the header.
    """
    header = {
        "type": "session", "version": 0, "id": session_id, "cwd": project,
        "createdAt": 1786806413737, "delegationDepth": 0, "agentPreset": "standard",
    }
    header.update(header_extra)
    lines = [json.dumps(header)] + [json.dumps(e) for e in events]
    text = "\n".join(lines) + "\n"

    sess_dir = sessions_dir / workspace_slug / session_id
    sess_dir.mkdir(parents=True, exist_ok=True)
    path = sess_dir / "session.jsonl.zstd"
    path.write_bytes(zstandard.ZstdCompressor().compress(text.encode("utf-8")))
    return path


def _usage_events(turn, step, in_t, out_t, provider="cerebras", model="zai-glm-4.7",
                   base_time=1786850753000, duplicate_in_message=True):
    """One (turn,step)'s worth of events: request/context + assistant/chunk usage,
    optionally followed by an assistant/message carrying the SAME sample again
    (as real DSH does) -- callers use duplicate_in_message to prove dedup fires."""
    out = [
        {"type": "request/context", "seq": 1, "time": base_time,
         "data": {"provider": provider, "model": model, "contextWindow": 131072}},
        {"type": "assistant/chunk", "seq": 2, "time": base_time + 1,
         "data": {"turn": turn, "step": step,
                  "chunk": {"type": "usage", "usage": {"inputTokens": in_t, "outputTokens": out_t}}}},
    ]
    if duplicate_in_message:
        out.append({
            "type": "assistant/message", "seq": 3, "time": base_time + 2,
            "data": {"turn": turn, "step": step, "usage": {"inputTokens": in_t, "outputTokens": out_t},
                     "message": {"source": {"provider": provider, "model": model}}},
        })
    out.append({"type": "step/end", "seq": 4, "time": base_time + 3, "data": {"turn": turn, "step": step}})
    return out


@pytest.fixture
def scan_env(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DSH_SESSIONS_DIR", tmp_path / "dsh_sessions")
    monkeypatch.setattr(main, "PROJECT_ALIASES_FILE", tmp_path / "aliases.json")
    return tmp_path


def test_missing_sessions_dir_returns_empty(scan_env):
    assert main._scan_dsh_sessions() == []


def test_usage_dedup_does_not_double_count(scan_env):
    """assistant/chunk and assistant/message repeat the SAME (turn,step) usage
    sample -- the scanner must not sum both, only the deduped total."""
    events = _usage_events(turn=1, step=1, in_t=1000, out_t=200, duplicate_in_message=True)
    _write_dsh_session(scan_env / "dsh_sessions", "--proj--", "session-abc", {}, events)

    out = main._scan_dsh_sessions()
    assert len(out) == 1
    tokens = out[0]["tokens"]
    assert tokens["input"] == 1000
    assert tokens["output"] == 200
    assert tokens["total"] == 1200


def test_maps_project_model_provider_and_cost(scan_env):
    events = _usage_events(turn=1, step=1, in_t=500, out_t=100, provider="cerebras", model="zai-glm-4.7")
    _write_dsh_session(scan_env / "dsh_sessions", "--proj--", "session-abc", {}, events,
                        project="/Users/dev/myproject")

    out = main._scan_dsh_sessions()
    assert len(out) == 1
    sess = out[0]
    assert sess["agent"] == "dsh"
    assert sess["id"] == "session-abc"
    assert sess["project"] == "/Users/dev/myproject"
    assert sess["model"] == "zai-glm-4.7"
    assert sess["provider"] == "cerebras"
    assert sess["tokens"]["input"] == 500
    assert sess["cost"] > 0


def test_mixed_provider_session_prices_each_segment(scan_env):
    """One session spanning a local ollama call and a paid cerebras call must
    price each (turn,step) with its own provider, not one rate for the whole
    session -- real DSH sessions do span providers mid-conversation."""
    events = (
        _usage_events(turn=1, step=1, in_t=1000, out_t=100, provider="ollama",
                      model="deepseek-v4-flash:cloud", base_time=1000)
        + _usage_events(turn=2, step=1, in_t=2000, out_t=300, provider="cerebras",
                        model="zai-glm-4.7", base_time=2000)
    )
    _write_dsh_session(scan_env / "dsh_sessions", "--proj--", "session-mixed", {}, events)

    out = main._scan_dsh_sessions()
    assert len(out) == 1
    sess = out[0]
    assert sess["tokens"]["input"] == 3000
    assert sess["tokens"]["output"] == 400
    # local ollama segment is priced by electricity (near-zero, not the cerebras
    # per-token rate applied to all 3000 input tokens) -- so cost must be well
    # under what a flat cerebras-only price would give.
    cerebras_only_upper_bound = main.calculate_cost("zai-glm-4.7", 3000, 400, 0, provider="cerebras")
    assert sess["cost"] < cerebras_only_upper_bound
    assert sess["model"] == "zai-glm-4.7"  # last model used


def test_subagent_children_fold_into_parent_delegation(scan_env):
    parent_events = _usage_events(turn=1, step=1, in_t=100, out_t=20)
    _write_dsh_session(scan_env / "dsh_sessions", "--proj--", "session-parent", {}, parent_events)

    child_events = _usage_events(turn=1, step=1, in_t=50, out_t=10, provider="cerebras", model="zai-glm-4.7")
    _write_dsh_session(
        scan_env / "dsh_sessions", "--proj--", "child-uuid-1",
        {"origin": "subagent", "parentSession": "session-parent", "delegationDepth": 1},
        child_events,
    )

    out = main._scan_dsh_sessions()
    ids = {s["id"] for s in out}
    assert ids == {"session-parent"}, "subagent child must not appear as its own top-level session"

    parent = out[0]
    deleg = parent["delegation"]
    assert deleg["supported"] is True
    assert deleg["tokens_recorded"] is True
    assert deleg["spawn_count"] == 1
    assert deleg["subagents"][0]["agent_id"] == "child-uuid-1"
    assert deleg["subagents"][0]["tokens"]["input"] == 50
    assert deleg["delegated_total"] == 50 + 10


def test_fork_without_origin_stays_standalone(scan_env):
    """A session- prefixed id with a parentSession but no origin (DSH's
    'fork' shape) has no verified rollup semantics -- must surface as its
    own top-level session, not silently folded or dropped."""
    parent_events = _usage_events(turn=1, step=1, in_t=100, out_t=20)
    _write_dsh_session(scan_env / "dsh_sessions", "--proj--", "session-parent", {}, parent_events)

    fork_events = _usage_events(turn=1, step=1, in_t=30, out_t=5)
    _write_dsh_session(
        scan_env / "dsh_sessions", "--proj--", "session-fork-1",
        {"parentSession": "session-parent"},  # no "origin" key -- the fork shape
        fork_events,
    )

    out = main._scan_dsh_sessions()
    ids = {s["id"] for s in out}
    assert ids == {"session-parent", "session-fork-1"}


def test_errored_turn_with_no_usage_yields_zero_tokens(scan_env):
    """A turn that errors before any usage event fires (e.g. DSH's own
    403/context-window errors) must not crash the scanner or fabricate cost."""
    events = [
        {"type": "request/context", "seq": 1, "time": 1000,
         "data": {"provider": "ollama", "model": "deepseek-v4-flash:cloud", "contextWindow": 262144}},
        {"type": "turn/end", "seq": 2, "time": 1001,
         "data": {"turn": 1, "reason": {"kind": "error", "error": {"message": "403", "code": "AUTH"}}}},
    ]
    _write_dsh_session(scan_env / "dsh_sessions", "--proj--", "session-err", {}, events)

    out = main._scan_dsh_sessions()
    assert len(out) == 1
    assert out[0]["tokens"]["total"] == 0
    assert out[0]["cost"] == 0.0


def test_tool_calls_counted(scan_env):
    events = _usage_events(turn=1, step=1, in_t=10, out_t=5) + [
        {"type": "tool/call", "seq": 5, "time": 1786850753010,
         "data": {"turn": 1, "step": 1, "callId": "c1", "name": "bash", "arguments": "{}"}},
        {"type": "tool/call", "seq": 6, "time": 1786850753011,
         "data": {"turn": 1, "step": 1, "callId": "c2", "name": "bash", "arguments": "{}"}},
    ]
    _write_dsh_session(scan_env / "dsh_sessions", "--proj--", "session-tools", {}, events)

    out = main._scan_dsh_sessions()
    assert out[0]["tool_counts"] == {"bash": 2}
