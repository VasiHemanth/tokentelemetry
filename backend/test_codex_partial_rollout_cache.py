"""Regression test for issue #350: a Codex rollout file that fails partway
through parsing must not have its partial read persisted as the durable
per-session cache entry.

Run: pytest backend/test_codex_partial_rollout_cache.py
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402
import scan_cache  # noqa: E402


SID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _jl(**data):
    return json.dumps(data) + "\n"


def _write_rollout(codex_dir, filename, records):
    path = codex_dir / "sessions" / "2026" / "07" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(records), encoding="utf-8")


@pytest.fixture
def scan_env(tmp_path, monkeypatch):
    missing = tmp_path / "missing"
    for attr in (
        "CLAUDE_DIR", "GEMINI_DIR", "QWEN_DIR", "VIBE_DIR", "OLLAMA_DIR",
        "GROK_SESSIONS_DIR", "GROK_UNIFIED_LOG", "VSCODE_STORAGE", "CURSOR_STORAGE",
        "COPILOT_CLI_DIR", "ANTIGRAVITY_BRAIN_DIR", "ANTIGRAVITY_CLI_DIR",
        "HERMES_DIR", "PI_SESSIONS_DIR", "KIMI_DIR", "KIMI_SESSIONS_DIR",
    ):
        monkeypatch.setattr(main, attr, missing / attr.lower())
    monkeypatch.setattr(main, "ANTIGRAVITY_BRAIN_SOURCES", [])
    monkeypatch.setattr(main, "ANTIGRAVITY_BRAIN_DIRS", [])
    monkeypatch.setattr(main, "_antigravity_cli_meta", lambda *args, **kwargs: {})
    monkeypatch.setattr(main, "CODEX_DIR", tmp_path / ".codex")
    monkeypatch.setattr(main, "CURSOR_DIR", tmp_path / ".cursor")
    monkeypatch.setattr(main, "OPENCODE_DB", tmp_path / "opencode.db")
    monkeypatch.setattr(main, "ZCODE_DB", tmp_path / "zcode.db")
    monkeypatch.setattr(main, "HERMES_DB", tmp_path / "hermes-state.db")
    monkeypatch.setattr(main, "HERMES_PROFILES_DIR", missing / "hermes-profiles")
    monkeypatch.setattr(main, "PROJECT_ALIASES_FILE", tmp_path / "aliases.json")
    monkeypatch.setenv("TOKENTELEMETRY_DATA_DIR", str(tmp_path / "tt_data"))
    return tmp_path


def _token_event(input_tokens):
    return _jl(
        type="event_msg",
        timestamp="2026-07-20T10:00:01Z",
        payload={
            "type": "token_count",
            "info": {"total_token_usage": {"input_tokens": input_tokens, "output_tokens": 0}},
        },
    )


def test_partial_second_file_does_not_get_cached_as_final(scan_env):
    codex_dir = scan_env / ".codex"

    # Older rollout: a complete, valid session.
    _write_rollout(
        codex_dir,
        f"rollout-2026-07-20T10-00-00-{SID}.jsonl",
        [
            _jl(type="session_meta", payload={"cwd": "/repo", "model": "gpt-5-codex"}),
            _token_event(15000),
        ],
    )
    # Newer rollout for the SAME session: opens fine, records a token event,
    # then hits a session_meta record with no "payload" key at all (a
    # truncated or corrupted write) and blows up mid-parse.
    _write_rollout(
        codex_dir,
        f"rollout-2026-07-20T11-00-00-{SID}.jsonl",
        [
            _jl(type="session_meta", payload={"cwd": "/repo", "model": "gpt-5-codex"}),
            json.dumps({"type": "session_meta"}) + "\n",
        ],
    )

    sessions = main._scan_sessions_sync()
    sess = next(s for s in sessions if s["id"] == SID)

    # The second file never finished parsing, so nothing here is a complete
    # read of the session. It must stay a stub rather than being persisted
    # to the durable cache as if 15000 tokens were the final total.
    assert sess["stub"] is True

    source_mtime = max(
        (codex_dir / "sessions" / "2026" / "07" / name).stat().st_mtime
        for name in (
            f"rollout-2026-07-20T10-00-00-{SID}.jsonl",
            f"rollout-2026-07-20T11-00-00-{SID}.jsonl",
        )
    )
    assert scan_cache.read_cache("codex", SID, source_mtime) is None
