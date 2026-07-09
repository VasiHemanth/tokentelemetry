"""VS Code Copilot chat-session scanning.

Discussion #129 follow-up: VS Code writes a chatSessions/<id>.json(l) file the
moment the chat panel opens, even if the user never sends a message. Those
zero-request files showed up as copilot sessions with an empty intent and
0 tokens. The scanner must skip them and keep real sessions.

Run: pytest backend/test_copilot_vscode_scan.py -q
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402


@pytest.fixture
def scan_env(tmp_path, monkeypatch):
    """Point every agent store at a nonexistent dir under tmp_path so a full
    _scan_sessions_sync() run is hermetic (mirrors test_cline_smallcode.py)."""
    missing = tmp_path / "missing"
    for attr in ("CODEX_DIR", "GEMINI_DIR", "QWEN_DIR", "VIBE_DIR", "OLLAMA_DIR",
                 "GROK_SESSIONS_DIR", "VSCODE_STORAGE", "CURSOR_STORAGE",
                 "COPILOT_CLI_DIR", "ANTIGRAVITY_BRAIN_DIR", "ANTIGRAVITY_CLI_DIR",
                 "HERMES_DIR"):
        monkeypatch.setattr(main, attr, missing / attr.lower())
    monkeypatch.setattr(main, "ANTIGRAVITY_BRAIN_SOURCES", [])
    monkeypatch.setattr(main, "ANTIGRAVITY_BRAIN_DIRS", [])
    monkeypatch.setattr(main, "_antigravity_cli_meta", lambda *a, **k: {})
    monkeypatch.setattr(main, "CLAUDE_DIR", missing / "claude")
    monkeypatch.setattr(main, "CURSOR_DIR", missing / "cursor")
    monkeypatch.setattr(main, "OPENCODE_DB", missing / "opencode.db")
    monkeypatch.setattr(main, "HERMES_DB", missing / "hermes-state.db")
    monkeypatch.setattr(main, "HERMES_PROFILES_DIR", missing / "hermes-profiles")
    monkeypatch.setattr(main, "PROJECT_ALIASES_FILE", tmp_path / "aliases.json")
    monkeypatch.setattr(main, "CLINE_DIR", missing / "cline")
    monkeypatch.setattr(main, "CLINE_VSCODE_DIR", missing / "cline-vscode")
    monkeypatch.setattr(main, "SMALLCODE_EXTRA_ROOTS", [])
    return tmp_path


def _write_vscode_session(ws_dir: Path, sid: str, body: dict) -> None:
    chat = ws_dir / "chatSessions"
    chat.mkdir(parents=True, exist_ok=True)
    (ws_dir / "workspace.json").write_text(json.dumps({"folder": "file:///tmp/proj"}))
    (chat / f"{sid}.json").write_text(json.dumps(body))


def test_zero_request_phantom_sessions_are_skipped(scan_env, monkeypatch):
    storage = scan_env / "vscode-storage"
    ws = storage / "ws1"
    # Phantom: chat panel opened, nothing ever sent.
    _write_vscode_session(ws, "phantom-1", {
        "version": 3, "creationDate": 1781420401161, "requests": [],
        "pendingRequests": [],
    })
    # Real session with one request.
    _write_vscode_session(ws, "real-1", {
        "version": 3, "creationDate": 1781420401161,
        "requests": [{"message": {"text": "explain this function"},
                      "modelId": "copilot/gpt-5-mini",
                      "timestamp": 1781420405000,
                      "completionTokens": 42}],
    })
    monkeypatch.setattr(main, "VSCODE_STORAGE", storage)

    sessions = [s for s in main._scan_sessions_sync() if s["agent"] == "copilot"]
    ids = {s["id"] for s in sessions}
    assert "real-1" in ids
    assert "phantom-1" not in ids
    real = next(s for s in sessions if s["id"] == "real-1")
    assert real["display"] == "explain this function"
    assert real["tokens"]["output"] == 42


def test_pending_only_session_is_kept(scan_env, monkeypatch):
    # A request in flight when the snapshot was written is still a session.
    storage = scan_env / "vscode-storage"
    _write_vscode_session(storage / "ws1", "pending-1", {
        "version": 3, "creationDate": 1781420401161, "requests": [],
        "pendingRequests": [{"message": {"text": "still running"}}],
    })
    monkeypatch.setattr(main, "VSCODE_STORAGE", storage)

    sessions = [s for s in main._scan_sessions_sync() if s["agent"] == "copilot"]
    assert {s["id"] for s in sessions} == {"pending-1"}
