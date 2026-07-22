"""Tests for published-artifact extraction from Claude session transcripts.

An Artifact tool_use (file_path/title/description/favicon) pairs with its
tool_result, which carries the hosted URL ("Published <path> at
https://claude.ai/code/artifact/<uuid>"). The scan collects these per session
as `published_artifacts`, and /projects rolls them up per project card.

Run: pytest backend/test_published_artifacts.py
"""
import asyncio
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402

SID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
PROJ_DIR = "-tmp-proj"
URL1 = "https://claude.ai/code/artifact/7ad39bb7-21a0-4094-83af-a6130b1102ed"
URL2 = "https://claude.ai/code/artifact/8ac4102a-9921-46d9-b58e-58d5a637f592"


def _jl(**kw) -> str:
    return json.dumps(kw) + "\n"


def _artifact_call(tool_id, ts, **inp):
    return _jl(type="assistant", timestamp=ts, message={
        "model": "claude-opus-4-8",
        "usage": {"input_tokens": 10, "output_tokens": 5},
        "content": [{"type": "tool_use", "id": tool_id, "name": "Artifact", "input": inp}],
    })


def _artifact_result(tool_id, ts, text):
    return _jl(type="user", timestamp=ts, message={
        "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": text}],
    })


def _write_session(claude_dir, lines):
    p_dir = claude_dir / "projects" / PROJ_DIR
    p_dir.mkdir(parents=True, exist_ok=True)
    (p_dir / f"{SID}.jsonl").write_text(
        _jl(type="user", timestamp="2026-07-20T10:00:00Z", cwd="/tmp/proj",
            message={"content": "make me a page"}) + "".join(lines),
        encoding="utf-8",
    )


@pytest.fixture
def scan_env(tmp_path, monkeypatch):
    """Point every agent store at tmp_path so the scan is hermetic."""
    missing = tmp_path / "missing"
    for attr in ("CODEX_DIR", "GEMINI_DIR", "QWEN_DIR", "VIBE_DIR", "OLLAMA_DIR",
                 "GROK_SESSIONS_DIR", "VSCODE_STORAGE", "CURSOR_STORAGE",
                 "COPILOT_CLI_DIR", "ANTIGRAVITY_BRAIN_DIR", "ANTIGRAVITY_CLI_DIR",
                 "HERMES_DIR", "PI_SESSIONS_DIR"):
        monkeypatch.setattr(main, attr, missing / attr.lower())
    monkeypatch.setattr(main, "ANTIGRAVITY_BRAIN_SOURCES", [])
    monkeypatch.setattr(main, "ANTIGRAVITY_BRAIN_DIRS", [])
    monkeypatch.setattr(main, "_antigravity_cli_meta", lambda *a, **k: {})
    monkeypatch.setattr(main, "CLAUDE_DIR", tmp_path / ".claude")
    monkeypatch.setattr(main, "CURSOR_DIR", tmp_path / ".cursor")
    monkeypatch.setattr(main, "OPENCODE_DB", tmp_path / "opencode.db")
    monkeypatch.setattr(main, "HERMES_DB", tmp_path / "hermes-state.db")
    monkeypatch.setattr(main, "HERMES_PROFILES_DIR", missing / "hermes-profiles")
    monkeypatch.setattr(main, "PROJECT_ALIASES_FILE", tmp_path / "aliases.json")
    monkeypatch.setenv("TOKENTELEMETRY_DATA_DIR", str(tmp_path / "tt_data"))
    return tmp_path


def _claude_session(scan_env):
    return [s for s in main._scan_sessions_sync() if s["agent"] == "claude"][0]


def test_publish_extracted(scan_env):
    _write_session(scan_env / ".claude", [
        _artifact_call("t1", "2026-07-20T10:01:00Z",
                       file_path="/tmp/proj/report.html",
                       description="A report page", favicon="📐"),
        _artifact_result("t1", "2026-07-20T10:01:05Z",
                         f"Published /tmp/proj/report.html at {URL1}\n\nTo update: republish."),
    ])
    s = _claude_session(scan_env)
    arts = s["published_artifacts"]
    assert len(arts) == 1
    a = arts[0]
    assert a["url"] == URL1
    assert a["title"] == "report"          # falls back to file basename
    assert a["description"] == "A report page"
    assert a["favicon"] == "📐"
    assert a["file_name"] == "report.html"
    assert a["session_id"] == SID
    assert a["agent"] == "claude"
    assert a["timestamp"] == "2026-07-20T10:01:05Z"


def test_redeploy_same_url_upserts(scan_env):
    _write_session(scan_env / ".claude", [
        _artifact_call("t1", "2026-07-20T10:01:00Z",
                       file_path="/tmp/proj/report.html",
                       title="First title", description="v1", favicon="📐"),
        _artifact_result("t1", "2026-07-20T10:01:05Z", f"Published x at {URL1}"),
        # Redeploy: same URL, no description this time — earlier metadata kept.
        _artifact_call("t2", "2026-07-20T11:00:00Z",
                       file_path="/tmp/proj/report.html", favicon="📐"),
        _artifact_result("t2", "2026-07-20T11:00:05Z", f"Published x at {URL1}"),
    ])
    s = _claude_session(scan_env)
    arts = s["published_artifacts"]
    assert len(arts) == 1
    assert arts[0]["timestamp"] == "2026-07-20T11:00:05Z"   # later publish wins
    assert arts[0]["description"] == "v1"                   # omitted metadata kept


def test_two_urls_sorted_newest_first(scan_env):
    _write_session(scan_env / ".claude", [
        _artifact_call("t1", "2026-07-20T10:01:00Z", file_path="/tmp/a.html"),
        _artifact_result("t1", "2026-07-20T10:01:05Z", f"Published a at {URL1}"),
        _artifact_call("t2", "2026-07-20T12:00:00Z", file_path="/tmp/b.html"),
        _artifact_result("t2", "2026-07-20T12:00:05Z", f"Published b at {URL2}"),
    ])
    arts = _claude_session(scan_env)["published_artifacts"]
    assert [a["url"] for a in arts] == [URL2, URL1]


def test_list_action_and_failed_publish_ignored(scan_env):
    _write_session(scan_env / ".claude", [
        # action:"list" enumerates — its result may mention URLs but isn't a publish.
        _artifact_call("t1", "2026-07-20T10:01:00Z", action="list"),
        _artifact_result("t1", "2026-07-20T10:01:05Z", f"1. My page — {URL1}"),
        # A publish whose result carries no URL (error) records nothing.
        _artifact_call("t2", "2026-07-20T10:02:00Z", file_path="/tmp/x.html"),
        _artifact_result("t2", "2026-07-20T10:02:05Z", "Error: file not found"),
    ])
    s = _claude_session(scan_env)
    assert "published_artifacts" not in s


def test_list_content_blocks_result(scan_env):
    """tool_result content as a list of text blocks (not a plain string)."""
    _write_session(scan_env / ".claude", [
        _artifact_call("t1", "2026-07-20T10:01:00Z", file_path="/tmp/proj/dash.html",
                       title="Dash"),
        _artifact_result("t1", "2026-07-20T10:01:05Z",
                         [{"type": "text", "text": f"Published /tmp/proj/dash.html at {URL2}"}]),
    ])
    arts = _claude_session(scan_env)["published_artifacts"]
    assert arts[0]["url"] == URL2 and arts[0]["title"] == "Dash"


def test_cache_roundtrip_preserves_artifacts(scan_env):
    _write_session(scan_env / ".claude", [
        _artifact_call("t1", "2026-07-20T10:01:00Z", file_path="/tmp/a.html"),
        _artifact_result("t1", "2026-07-20T10:01:05Z", f"Published a at {URL1}"),
    ])
    fresh = _claude_session(scan_env)
    payload = main._claude_cache_payload(fresh)
    restored = {"published_artifacts": None}
    main._apply_claude_cache_hit(restored, json.loads(json.dumps(payload)))
    assert restored["published_artifacts"] == fresh["published_artifacts"]


def test_projects_rollup(scan_env, monkeypatch):
    _write_session(scan_env / ".claude", [
        _artifact_call("t1", "2026-07-20T10:01:00Z", file_path="/tmp/a.html",
                       title="A", favicon="📊"),
        _artifact_result("t1", "2026-07-20T10:01:05Z", f"Published a at {URL1}"),
    ])
    sessions = main._scan_sessions_sync()

    async def fake_cached(fresh=False):
        return sessions
    monkeypatch.setattr(main, "get_sessions_cached", fake_cached)
    monkeypatch.setattr(main, "load_hidden", lambda: set())
    projects = asyncio.run(main.get_projects())
    proj = next(p for p in projects if p["path"] == "/tmp/proj")
    assert len(proj["artifacts"]) == 1
    assert proj["artifacts"][0]["url"] == URL1
    assert proj["artifacts"][0]["session_id"] == SID
