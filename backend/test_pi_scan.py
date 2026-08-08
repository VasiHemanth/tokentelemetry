"""Tests for native session scanning of the Pi Coding Agent (issue #135).

Pi stores one JSONL per session, bucketed by encoded cwd:
    ~/.pi/agent/sessions/<encoded-cwd>/<ts>_<uuid>.jsonl

Each file opens with a {"type":"session", id, cwd, timestamp} header, then a
stream of message events. Assistant turns carry `message.provider`,
`message.model` and a per-request `message.usage` block with input/output/
cacheRead/cacheWrite/reasoning and a nested cost — verified against a real Pi
0.80.3 session on disk. The scanner recomputes cost with TokenTelemetry's own
pricing (per message, so mixed-model sessions bill correctly).

Run: pytest backend/test_pi_scan.py -q
"""
import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402
from pricing import calculate_cost  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture builder — mirrors the real Pi JSONL event shape.
# ---------------------------------------------------------------------------

def _assistant(model, provider, *, input, output, cacheRead=0, cacheWrite=0,
               reasoning=0, ts, content):
    return {
        "type": "message",
        "id": "a" + str(ts),
        "timestamp": ts,
        "message": {
            "role": "assistant",
            "content": content,
            "api": "openai-completions",
            "provider": provider,
            "model": model,
            "usage": {
                "input": input, "output": output,
                "cacheRead": cacheRead, "cacheWrite": cacheWrite,
                "reasoning": reasoning,
                "totalTokens": input + output + cacheRead,
                "cost": {"total": 0.0},  # ignored; TT recomputes
            },
            "stopReason": "toolUse" if any(c.get("type") == "toolCall" for c in content) else "endTurn",
        },
    }


def _write_pi_session(root: Path, *, cwd, sid, provider="cerebras",
                      model="zai-glm-4.7", second_model=None):
    """Write one Pi session JSONL and return its path. The session:
      user -> assistant(thinking+toolCall) -> toolResult -> assistant(text).
    When second_model is set, the final assistant turn uses a different model
    to exercise per-message pricing on mixed-model sessions.
    """
    bucket = root / cwd.replace("/", "-")
    bucket.mkdir(parents=True, exist_ok=True)
    m2 = second_model or model
    events = [
        {"type": "session", "version": 3, "id": sid,
         "timestamp": "2026-07-05T07:40:17.539Z", "cwd": cwd},
        {"type": "model_change", "id": "mc1", "provider": provider, "modelId": model},
        {"type": "thinking_level_change", "id": "tl1", "thinkingLevel": "medium"},
        {"type": "message", "id": "u1", "timestamp": "2026-07-05T07:40:59.792Z",
         "message": {"role": "user",
                     "content": [{"type": "text", "text": "add pi support to the scanner"}]}},
        _assistant(model, provider, input=2965, output=185, cacheRead=100,
                   cacheWrite=50, reasoning=100, ts="2026-07-05T07:41:00.789Z",
                   content=[
                       {"type": "thinking", "thinking": "Let me read the docs."},
                       {"type": "text", "text": "Reading the provider docs."},
                       {"type": "toolCall", "id": "tc1", "name": "read",
                        "arguments": {"path": "/docs/models.md"}},
                   ]),
        {"type": "message", "id": "tr1", "timestamp": "2026-07-05T07:41:01.000Z",
         "message": {"role": "toolResult", "toolCallId": "tc1", "toolName": "read",
                     "content": [{"type": "text", "text": "# Custom Models ..."}]}},
        _assistant(m2, provider, input=500, output=42, cacheRead=200, cacheWrite=0,
                   reasoning=0, ts="2026-07-05T07:41:05.000Z",
                   content=[{"type": "text", "text": "Done."}]),
    ]
    f = bucket / f"2026-07-05T07-40-17-539Z_{sid}.jsonl"
    f.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------

def test_scan_pi_maps_tokens_cost_and_project(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    cwd = "/Users/dev/proj-alpha"
    sid = "019f3138-8d03-76e7-9793-2510fffacaef"
    _write_pi_session(root, cwd=cwd, sid=sid)
    monkeypatch.setattr(main, "PI_SESSIONS_DIR", root)
    monkeypatch.setattr(main, "_load_project_aliases", lambda: {})

    out = main._scan_pi_sessions()
    assert len(out) == 1
    s = out[0]
    assert s["agent"] == "pi"
    assert s["id"] == sid
    assert s["project"] == cwd
    assert s["model"] == "zai-glm-4.7"

    # Tokens summed across the two assistant turns.
    tk = s["tokens"]
    assert tk["input"] == 2965 + 500
    assert tk["output"] == 185 + 42
    assert tk["cached"] == 100 + 200
    assert tk["cache_creation"] == 50
    assert tk["reasoning"] == 100
    assert tk["total"] == tk["input"] + tk["output"] + tk["cached"]

    # Cost recomputed per message with TT pricing — must match the sum of the
    # two independent per-turn calculate_cost calls exactly.
    expected = (
        calculate_cost("zai-glm-4.7", 2965, 185, 100, cache_creation_tokens=50, provider="cerebras")
        + calculate_cost("zai-glm-4.7", 500, 42, 200, cache_creation_tokens=0, provider="cerebras")
    )
    assert s["cost"] == pytest.approx(expected)
    assert s["tokens"]["cost"] == pytest.approx(expected)

    # Tool call captured; display taken from the first user prompt.
    assert s["tool_counts"] == {"read": 1}
    assert s["display"] == "add pi support to the scanner"
    assert s["pi"]["provider"] == "cerebras"


def test_scan_pi_mixed_model_prices_each_turn(tmp_path, monkeypatch):
    """A session that switches model mid-way must price each turn with its own
    model, not one session-level model applied to all tokens."""
    root = tmp_path / "sessions"
    _write_pi_session(root, cwd="/Users/dev/proj-beta",
                      sid="019f3139-aaaa-bbbb-cccc-000000000001",
                      provider="cerebras", model="zai-glm-4.7",
                      second_model="qwen-3-235b-a22b-instruct-2507")
    monkeypatch.setattr(main, "PI_SESSIONS_DIR", root)
    monkeypatch.setattr(main, "_load_project_aliases", lambda: {})

    s = main._scan_pi_sessions()[0]
    expected = (
        calculate_cost("zai-glm-4.7", 2965, 185, 100, cache_creation_tokens=50, provider="cerebras")
        + calculate_cost("qwen-3-235b-a22b-instruct-2507", 500, 42, 200, cache_creation_tokens=0, provider="cerebras")
    )
    assert s["cost"] == pytest.approx(expected)
    # Last-seen model wins as the session's headline model.
    assert s["model"] == "qwen-3-235b-a22b-instruct-2507"
    assert set(s["pi"]["models_used"]) == {"zai-glm-4.7", "qwen-3-235b-a22b-instruct-2507"}


def test_scan_pi_applies_project_alias(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    _write_pi_session(root, cwd="/old/path", sid="019f3140-dead-beef-cafe-000000000002")
    monkeypatch.setattr(main, "PI_SESSIONS_DIR", root)
    monkeypatch.setattr(main, "_load_project_aliases", lambda: {"/old/path": "/new/path"})
    s = main._scan_pi_sessions()[0]
    assert s["project"] == "/new/path"


def test_scan_pi_missing_dir_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "PI_SESSIONS_DIR", tmp_path / "nope")
    assert main._scan_pi_sessions() == []


def test_scan_pi_skips_corrupt_lines(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    f = _write_pi_session(root, cwd="/Users/dev/proj", sid="019f3141-0000-0000-0000-000000000003")
    # Corrupt the file with a garbage line in the middle; scan must still work.
    good = f.read_text().splitlines()
    good.insert(4, "{not json at all")
    f.write_text("\n".join(good) + "\n", encoding="utf-8")
    monkeypatch.setattr(main, "PI_SESSIONS_DIR", root)
    monkeypatch.setattr(main, "_load_project_aliases", lambda: {})
    out = main._scan_pi_sessions()
    assert len(out) == 1
    assert out[0]["tokens"]["input"] > 0


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def test_pi_detected_when_sessions_dir_exists(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    _write_pi_session(root, cwd="/Users/dev/proj", sid="019f3142-0000-0000-0000-000000000004")
    monkeypatch.setattr(main, "PI_SESSIONS_DIR", root)
    assert "pi" in main._list_available_agents()

    monkeypatch.setattr(main, "PI_SESSIONS_DIR", tmp_path / "gone")
    assert "pi" not in main._list_available_agents()


# ---------------------------------------------------------------------------
# Session detail trace
# ---------------------------------------------------------------------------

def test_session_detail_pi_normalizes_to_claude_shape(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    sid = "019f3143-0000-0000-0000-000000000005"
    _write_pi_session(root, cwd="/Users/dev/proj", sid=sid)
    monkeypatch.setattr(main, "PI_SESSIONS_DIR", root)

    events = asyncio.run(main.get_session_detail(sid, "pi"))
    assert isinstance(events, list) and events

    # Every event is Claude-shaped and carries a normalized timestamp.
    assert all("normalized_timestamp" in e for e in events)
    message_events = [e for e in events if "message" in e]
    roles = [e["message"]["role"] for e in message_events]
    assert roles[0] == "user"

    # tool_use blocks must pair 1:1 with tool_result blocks by id.
    tu = {b["id"] for e in message_events for b in e["message"]["content"] if b["type"] == "tool_use"}
    tr = {b["tool_use_id"] for e in message_events for b in e["message"]["content"] if b.get("type") == "tool_result"}
    assert tu and tu == tr

    # Thinking + text blocks survive on the assistant turn.
    kinds = {b["type"] for e in message_events for b in e["message"]["content"]}
    assert {"thinking", "text", "tool_use", "tool_result"} <= kinds


def test_session_detail_pi_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "PI_SESSIONS_DIR", tmp_path / "sessions")
    res = asyncio.run(main.get_session_detail("nonexistent-id", "pi"))
    assert res == {"error": "Not found"}
