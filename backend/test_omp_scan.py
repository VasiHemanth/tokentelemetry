"""Tests for native session scanning of Oh My Pi (OMP).

OMP stores one JSONL per session, bucketed by encoded cwd:
    ~/.omp/agent/sessions/<encoded-cwd>/<ISO-ts>_<session-uuidv7>.jsonl

Each file opens with a {"type":"session", id, cwd, timestamp} header, followed by
{"type":"model_change"} and then message events. Assistant turns carry
`message.provider`, `message.model` and a per-request `message.usage` block with
input/output/cacheRead/cacheWrite plus a nested `cost.total`, and the latency
fields `duration` / `ttft` / `contextSnapshot`. Tool calls arrive as separate
{"type":"custom","customType":"tool_execution_start"} records. Verified against a
real OMP 18.10.2 session on disk.

OMP reports cost verbatim (sum of usage.cost.total); the scanner never recomputes
it. It is a separate agent from Pi, so it has its own scanner and its own key.

Run: pytest backend/test_omp_scan.py -q
"""
import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture builder — mirrors the real OMP JSONL event shape.
# ---------------------------------------------------------------------------

def _assistant(ts, *, model, provider="anthropic", input=0, output=0,
               cacheRead=0, cacheWrite=0, cost_total=0.0, duration=None,
               ttft=None, contextSnapshot=None, content=None):
    m = {
        "role": "assistant",
        "content": content or [{"type": "text", "text": "Done."}],
        "provider": provider,
        "model": model,
        "usage": {
            "input": input, "output": output,
            "cacheRead": cacheRead, "cacheWrite": cacheWrite,
            "cost": {"total": cost_total},
        },
    }
    if duration is not None:
        m["duration"] = duration
    if ttft is not None:
        m["ttft"] = ttft
    if contextSnapshot is not None:
        m["contextSnapshot"] = contextSnapshot
    return {"type": "message", "id": "a" + str(ts), "timestamp": ts, "message": m}


def _write_omp_session(root: Path, *, cwd, sid, provider="anthropic",
                       model="claude-sonnet-4", second_model=None):
    """Write one OMP session JSONL and return its path. The session is:
      header, model_change, user, tool_start, assistant(toolCall),
      toolResult, assistant(text).
    second_model exercises the last-seen-model headline and models_used list.
    """
    bucket = root / cwd.replace("/", "-")
    bucket.mkdir(parents=True, exist_ok=True)
    m2 = second_model or model
    events = [
        {"type": "title", "title": "ignored in v1"},
        {"type": "session", "version": 1, "id": sid,
         "timestamp": "2026-10-16T07:40:17.539Z", "cwd": cwd},
        {"type": "model_change", "id": "mc1", "model": f"{provider}/{model}"},
        {"type": "thinking_level_change", "id": "tl1", "thinkingLevel": "medium"},
        {"type": "message", "id": "u1", "timestamp": "2026-10-16T07:40:59.792Z",
         "message": {"role": "user",
                     "content": [{"type": "text", "text": "add omp support to the scanner"}]}},
        {"type": "custom", "id": "c1", "customType": "tool_execution_start",
         "timestamp": "2026-10-16T07:41:00.100Z",
         "data": {"toolName": "read", "toolCallId": "tc1"}},
        {"type": "custom", "id": "c2", "customType": "session_exit",
         "data": {}},
        _assistant("2026-10-16T07:41:00.789Z", model=model, provider=provider,
                   input=1000, output=200, cacheRead=100, cacheWrite=50,
                   cost_total=0.0123, duration=1500, ttft=300,
                   contextSnapshot={"tokens": 1234, "files": 3},
                   content=[
                       {"type": "thinking", "thinking": "Let me read the docs."},
                       {"type": "text", "text": "Reading the provider docs."},
                       {"type": "toolCall", "id": "tc1", "name": "read",
                        "arguments": {"path": "/docs/models.md"}},
                   ]),
        {"type": "message", "id": "tr1", "timestamp": "2026-10-16T07:41:01.000Z",
         "message": {"role": "toolResult", "toolCallId": "tc1", "toolName": "read",
                     "content": [{"type": "text", "text": "# Custom Models ..."}]}},
        _assistant("2026-10-16T07:41:05.000Z", model=m2, provider=provider,
                   input=500, output=50, cacheRead=0, cacheWrite=0,
                   cost_total=0.004, duration=500, ttft=100,
                   contextSnapshot={"tokens": 4321},
                   content=[{"type": "text", "text": "Done."}]),
    ]
    f = bucket / f"2026-10-16T07-40-17-539Z_{sid}.jsonl"
    f.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------

def test_scan_omp_maps_tokens_cost_and_project(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    cwd = "/Users/dev/proj-alpha"
    sid = "019f3138-8d03-76e7-9793-2510fffacaef"
    _write_omp_session(root, cwd=cwd, sid=sid)
    monkeypatch.setattr(main, "OMP_SESSIONS_DIR", root)
    monkeypatch.setattr(main, "_load_project_aliases", lambda: {})

    out = main._scan_omp_sessions()
    assert len(out) == 1
    s = out[0]
    assert s["agent"] == "omp"
    assert s["id"] == sid
    assert s["project"] == cwd
    assert s["model"] == "claude-sonnet-4"
    assert s["cost_source"] == "reported"
    assert s["mcp_tools"] == []
    assert s["has_plan"] is False and s["plans"] == []

    # Tokens summed across the two assistant turns; reasoning is always 0.
    tk = s["tokens"]
    assert tk["input"] == 1500
    assert tk["output"] == 250
    assert tk["cached"] == 100
    assert tk["cache_creation"] == 50
    assert tk["reasoning"] == 0
    assert tk["total"] == tk["input"] + tk["output"] + tk["cached"] == 1850
    assert "cost" not in tk, "OMP reports cost at the session level, not per token dict"

    # Cost is reported verbatim: the sum of usage.cost.total, never recomputed.
    assert s["cost"] == pytest.approx(0.0163)

    # Tool call captured from the custom tool_execution_start record only.
    assert s["tool_counts"] == {"read": 1}
    assert s["display"] == "add omp support to the scanner"
    assert s["text"] == s["display"]

    artifact = s["artifacts"][0]
    assert artifact["type"] == "document" and artifact["name"].endswith(".jsonl")

    blob = s["omp"]
    assert blob["provider"] == "anthropic"
    assert blob["models_used"] == ["claude-sonnet-4"]
    assert blob["num_messages"] == 4, "user + assistant + toolResult + assistant"
    assert blob["ttft_ms"] == 200, "mean of 300 and 100"
    assert blob["duration_ms"] == 1000, "mean of 1500 and 500"
    assert blob["context_snapshot"] == {"tokens": 4321}, "the LAST snapshot wins"


def test_scan_omp_tracks_models_used_in_order(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    _write_omp_session(root, cwd="/Users/dev/proj-beta",
                       sid="019f3139-aaaa-bbbb-cccc-000000000001",
                       model="claude-sonnet-4", second_model="claude-opus-4")
    monkeypatch.setattr(main, "OMP_SESSIONS_DIR", root)
    monkeypatch.setattr(main, "_load_project_aliases", lambda: {})

    s = main._scan_omp_sessions()[0]
    assert s["model"] == "claude-opus-4", "last assistant model wins as the headline"
    assert s["omp"]["models_used"] == ["claude-sonnet-4", "claude-opus-4"]


def test_scan_omp_applies_project_alias(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    _write_omp_session(root, cwd="/old/path", sid="019f3140-dead-beef-cafe-000000000002")
    monkeypatch.setattr(main, "OMP_SESSIONS_DIR", root)
    monkeypatch.setattr(main, "_load_project_aliases", lambda: {"/old/path": "/new/path"})
    s = main._scan_omp_sessions()[0]
    assert s["project"] == "/new/path"


def test_scan_omp_missing_dir_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "OMP_SESSIONS_DIR", tmp_path / "nope")
    assert main._scan_omp_sessions() == []


def test_scan_omp_skips_corrupt_lines(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    f = _write_omp_session(root, cwd="/Users/dev/proj", sid="019f3141-0000-0000-0000-000000000003")
    good = f.read_text().splitlines()
    good.insert(4, "{not json at all")
    f.write_text("\n".join(good) + "\n", encoding="utf-8")
    monkeypatch.setattr(main, "OMP_SESSIONS_DIR", root)
    monkeypatch.setattr(main, "_load_project_aliases", lambda: {})
    out = main._scan_omp_sessions()
    assert len(out) == 1
    assert out[0]["tokens"]["input"] > 0


def test_scan_omp_ignores_the_sibling_artifact_directory(tmp_path, monkeypatch):
    """Each session has a same-basename sibling dir holding tool artifacts.

    Real layout (verified on disk): inside a cwd bucket there is both
    `<ts>_<uuid>.jsonl` (the session) and `<ts>_<uuid>/` (per-tool artifact
    logs). Only the bucket's direct *.jsonl are sessions; the artifact dir is
    never walked.
    """
    root = tmp_path / "sessions"
    sid = "019f3144-0000-0000-0000-000000000006"
    sess = _write_omp_session(root, cwd="/Users/dev/proj", sid=sid)
    artifacts = sess.with_suffix("")  # drop .jsonl -> same-basename dir
    artifacts.mkdir()
    nested = artifacts / "tools"
    nested.mkdir()
    for nested_file in (artifacts / "read-1.jsonl", nested / "subagent.jsonl"):
        nested_file.write_text(json.dumps({
            "type": "session", "id": "sub", "cwd": "/Users/dev/proj",
            "timestamp": "2026-10-16T07:40:17.539Z"}) + "\n", encoding="utf-8")
    monkeypatch.setattr(main, "OMP_SESSIONS_DIR", root)
    monkeypatch.setattr(main, "_load_project_aliases", lambda: {})

    out = main._scan_omp_sessions()
    assert [s["id"] for s in out] == [sid]


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def test_omp_detected_when_sessions_dir_exists(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    _write_omp_session(root, cwd="/Users/dev/proj", sid="019f3142-0000-0000-0000-000000000004")
    monkeypatch.setattr(main, "OMP_SESSIONS_DIR", root)
    assert "omp" in main._list_available_agents()

    monkeypatch.setattr(main, "OMP_SESSIONS_DIR", tmp_path / "gone")
    assert "omp" not in main._list_available_agents()


# ---------------------------------------------------------------------------
# Session detail trace
# ---------------------------------------------------------------------------

def test_session_detail_omp_normalizes_to_claude_shape(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    sid = "019f3143-0000-0000-0000-000000000005"
    _write_omp_session(root, cwd="/Users/dev/proj", sid=sid)
    monkeypatch.setattr(main, "OMP_SESSIONS_DIR", root)

    events = asyncio.run(main.get_session_detail(sid, "omp"))
    assert isinstance(events, list) and events

    assert all("normalized_timestamp" in e for e in events)
    message_events = [e for e in events if "message" in e]
    roles = [e["message"]["role"] for e in message_events]
    assert roles[0] == "user"

    tu = {b["id"] for e in message_events for b in e["message"]["content"] if b["type"] == "tool_use"}
    tr = {b["tool_use_id"] for e in message_events for b in e["message"]["content"] if b.get("type") == "tool_result"}
    assert tu and tu == tr

    kinds = {b["type"] for e in message_events for b in e["message"]["content"]}
    assert {"thinking", "text", "tool_use", "tool_result"} <= kinds


def test_session_detail_omp_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "OMP_SESSIONS_DIR", tmp_path / "sessions")
    res = asyncio.run(main.get_session_detail("nonexistent-id", "omp"))
    assert res == {"error": "Not found"}
