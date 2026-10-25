"""Copilot CLI session scanning (~/.copilot/session-state/<id>/events.jsonl).

Regression test for PR #441: the session timestamp was read in the cost
calculation (``calculate_cost(..., at=ts)``) before ``ts`` was assigned. The
resulting NameError was swallowed by the per-session ``except Exception:
continue``, so Copilot CLI sessions silently never appeared. When an earlier
iteration of the loop happened to leave a ``ts`` bound, later sessions instead
inherited the wrong session's date.

Run: pytest backend/test_copilot_cli_scan.py -q
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402

START = "2026-06-04T11:45:07.548Z"
END = "2026-06-04T11:52:31.120Z"

# Closed-session rollup in the shape Copilot CLI actually writes.
METRICS = {
    "claude-haiku-4.5": {
        "requests": {"count": 2, "cost": 0.12},
        "usage": {
            "inputTokens": 63219,
            "outputTokens": 1365,
            "cacheReadTokens": 34516,
            "cacheWriteTokens": 28676,
            "reasoningTokens": 355,
        },
        "tokenDetails": {
            "input": {"tokenCount": 27},
            "cache_read": {"tokenCount": 34516},
            "cache_write": {"tokenCount": 28676},
            "output": {"tokenCount": 1365},
        },
    }
}


@pytest.fixture
def scan_env(tmp_path, monkeypatch):
    """Point every agent store at a nonexistent dir under tmp_path so a full
    _scan_sessions_sync() run is hermetic (mirrors test_copilot_vscode_scan)."""
    missing = tmp_path / "missing"
    for attr in ("CODEX_DIR", "GEMINI_DIR", "QWEN_DIR", "VIBE_DIR", "OLLAMA_DIR",
                 "GROK_SESSIONS_DIR", "GROK_UNIFIED_LOG", "VSCODE_STORAGE", "CURSOR_STORAGE",
                 "COPILOT_CLI_DIR", "ANTIGRAVITY_BRAIN_DIR", "ANTIGRAVITY_CLI_DIR",
                 "HERMES_DIR", "PI_SESSIONS_DIR", "KIMI_DIR", "KIMI_SESSIONS_DIR"):
        monkeypatch.setattr(main, attr, missing / attr.lower())
    monkeypatch.setattr(main, "ANTIGRAVITY_BRAIN_SOURCES", [])
    monkeypatch.setattr(main, "ANTIGRAVITY_BRAIN_DIRS", [])
    monkeypatch.setattr(main, "_antigravity_cli_meta", lambda *a, **k: {})
    monkeypatch.setattr(main, "CLAUDE_DIR", missing / "claude")
    monkeypatch.setattr(main, "CURSOR_DIR", missing / "cursor")
    monkeypatch.setattr(main, "OPENCODE_DB", missing / "opencode.db")
    monkeypatch.setattr(main, "ZCODE_DB", missing / "zcode.db")
    monkeypatch.setattr(main, "HERMES_DB", missing / "hermes-state.db")
    monkeypatch.setattr(main, "HERMES_PROFILES_DIR", missing / "hermes-profiles")
    monkeypatch.setattr(main, "PROJECT_ALIASES_FILE", tmp_path / "aliases.json")
    monkeypatch.setattr(main, "CLINE_DIR", missing / "cline")
    monkeypatch.setattr(main, "CLINE_VSCODE_DIR", missing / "cline-vscode")
    monkeypatch.setattr(main, "SMALLCODE_EXTRA_ROOTS", [])
    return tmp_path


def _write_cli_session(root, sid, start=START, end=END, message="hello copilot"):
    sess = root / sid
    sess.mkdir(parents=True)
    rows = [
        {"type": "session.start", "timestamp": start,
         "data": {"context": {"cwd": "/tmp/proj"}, "startTime": start}},
        {"type": "user.message", "timestamp": start, "data": {"content": message}},
        {"type": "assistant.message", "timestamp": end,
         "data": {"model": "claude-haiku-4.5", "outputTokens": 1365}},
        {"type": "session.shutdown", "timestamp": end,
         "data": {"modelMetrics": METRICS}},
    ]
    with open(sess / "events.jsonl", "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _cli_sessions():
    return [s for s in main._scan_sessions_sync()
            if s["agent"] == "copilot" and s.get("copilot_source") == "cli"]


def test_cli_session_is_emitted_with_its_own_timestamp(scan_env, monkeypatch):
    root = scan_env / "copilot-session-state"
    _write_cli_session(root, "cli-1")
    monkeypatch.setattr(main, "COPILOT_CLI_DIR", root)

    sessions = _cli_sessions()

    assert [s["id"] for s in sessions] == ["cli-1"], (
        "Copilot CLI session was skipped entirely (timestamp used before assignment)")
    sess = sessions[0]
    # last_ts (last event) wins over start_ts.
    assert sess["timestamp"] == main._parse_copilot_iso(END)
    assert sess["display"] == "hello copilot"
    assert sess["model"] == "claude-haiku-4.5"
    assert sess["tokens"]["input"] == 27
    assert sess["tokens"]["output"] == 1365
    assert sess["tokens"]["cached"] == 34516


def test_cost_is_priced_at_the_session_date(scan_env, monkeypatch):
    root = scan_env / "copilot-session-state"
    _write_cli_session(root, "cli-1")
    monkeypatch.setattr(main, "COPILOT_CLI_DIR", root)

    sess = _cli_sessions()[0]
    expected = main.calculate_cost(
        "claude-haiku-4.5", 27, 1365, 34516,
        cache_creation_tokens=28676, at=main._parse_copilot_iso(END))
    assert sess["tokens"]["cost"] == expected


def test_timestamps_do_not_leak_between_sessions(scan_env, monkeypatch):
    root = scan_env / "copilot-session-state"
    _write_cli_session(root, "cli-old", start="2026-01-02T03:04:05.000Z",
                       end="2026-01-02T03:10:00.000Z", message="old one")
    _write_cli_session(root, "cli-new", start="2026-06-04T11:45:07.548Z",
                       end=END, message="new one")
    monkeypatch.setattr(main, "COPILOT_CLI_DIR", root)

    by_id = {s["id"]: s for s in _cli_sessions()}

    assert set(by_id) == {"cli-old", "cli-new"}
    assert by_id["cli-old"]["timestamp"] == main._parse_copilot_iso(
        "2026-01-02T03:10:00.000Z")
    assert by_id["cli-new"]["timestamp"] == main._parse_copilot_iso(END)


def test_timestamp_falls_back_to_start_time_then_file_mtime(scan_env, monkeypatch):
    # No per-row timestamps at all: startTime still wins over the file mtime.
    root = scan_env / "copilot-session-state"
    sess = root / "cli-no-row-ts"
    sess.mkdir(parents=True)
    with open(sess / "events.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "session.start",
                            "data": {"startTime": START}}) + "\n")
        f.write(json.dumps({"type": "user.message",
                            "data": {"content": "no clock"}}) + "\n")
    monkeypatch.setattr(main, "COPILOT_CLI_DIR", root)

    out = _cli_sessions()

    assert [s["id"] for s in out] == ["cli-no-row-ts"]
    assert out[0]["timestamp"] == main._parse_copilot_iso(START)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
