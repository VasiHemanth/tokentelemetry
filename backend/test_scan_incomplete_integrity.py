"""A failed or partial scan must never overwrite or prune durable history.

Regression coverage for three shapes of the same defect:

  - Codex (#350): one rollout file of a multi-file session aborts mid-parse.
    The truncated totals must stay a stub — not cached, not written over the
    durable row.
  - Cline (#222): the CLI ``sessions.db`` query fails ("database is locked").
    Cline contributes zero sessions that scan; ``mark_absent`` must not flag
    its known sessions as gone.
  - Hermes (#223): one profile's ``state.db`` fails to read. Same consequence
    for that profile's sessions.

Every store here lives under ``tmp_path``; nothing reads a real home directory.

Run: python backend/test_scan_incomplete_integrity.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402
import scan_cache  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def scan_env(tmp_path, monkeypatch):
    """Point every agent store and TokenTelemetry's own data dir at tmp_path so
    a full _scan_sessions_sync() + history persist is hermetic (mirrors
    test_cline_smallcode.py's scan_env)."""
    missing = tmp_path / "missing"
    for attr in ("CODEX_DIR", "GEMINI_DIR", "QWEN_DIR", "VIBE_DIR", "OLLAMA_DIR",
                 "GROK_SESSIONS_DIR", "GROK_UNIFIED_LOG", "VSCODE_STORAGE", "CURSOR_STORAGE",
                 "COPILOT_CLI_DIR", "ANTIGRAVITY_BRAIN_DIR", "ANTIGRAVITY_CLI_DIR",
                 "HERMES_DIR", "PI_SESSIONS_DIR", "KIMI_DIR", "KIMI_SESSIONS_DIR",
                 "OMP_DIR", "OMP_SESSIONS_DIR"):
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
    monkeypatch.setenv("TOKENTELEMETRY_DATA_DIR", str(tmp_path / "tt_data"))
    return tmp_path


def _scan_and_persist():
    """One scan cycle exactly as get_sessions_cached() wires it, minus the
    event loop: with no running loop _persist_history_async runs inline, so the
    durable store is settled when this returns."""
    scan_started_at = datetime.now(timezone.utc).isoformat()
    incomplete_agents = set()
    data = main._scan_sessions_sync(incomplete_agents)
    main._persist_history_async(data, scan_started_at=scan_started_at,
                                incomplete_agents=incomplete_agents)
    return data, incomplete_agents


def _stored(agent):
    import history_store
    return {r["id"]: r for r in history_store.query() if r["agent"] == agent}


def _bump_mtime(path: Path, seconds: int = 10) -> None:
    st = path.stat()
    os.utime(path, (st.st_atime + seconds, st.st_mtime + seconds))


def _codex_token_line(ts, input_tokens, output_tokens):
    return json.dumps({
        "timestamp": ts, "type": "event_msg",
        "payload": {"type": "token_count", "info": {"total_token_usage": {
            "input_tokens": input_tokens, "cached_input_tokens": 0,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }}},
    }) + "\n"


def _build_cline_db(db_path: Path, session_id: str, workspace_root: str) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE sessions (session_id TEXT, started_at TEXT, ended_at TEXT, "
        "exit_code INTEGER, status TEXT, provider TEXT, model TEXT, cwd TEXT, "
        "workspace_root TEXT, prompt TEXT, metadata_json TEXT, messages_path TEXT)"
    )
    metadata = {"title": "t", "totalCost": 0.5,
                "aggregateUsage": {"inputTokens": 1000, "outputTokens": 200}}
    conn.execute(
        "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (session_id, "2026-07-01T05:15:01.949Z", "2026-07-01T05:15:22.428Z", 0,
         "completed", "anthropic", "claude-sonnet-4-6", workspace_root,
         workspace_root, "t", json.dumps(metadata), None),
    )
    conn.commit()
    conn.close()


def _build_hermes_db(path: Path, sid: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE sessions (id TEXT, source TEXT, model TEXT, "
                "parent_session_id TEXT, started_at INT, ended_at INT, "
                "input_tokens INT, output_tokens INT, cache_read_tokens INT, "
                "cache_write_tokens INT, reasoning_tokens INT, "
                "estimated_cost_usd REAL, actual_cost_usd REAL, title TEXT, "
                "billing_provider TEXT, billing_base_url TEXT, end_reason TEXT)")
    con.execute("CREATE TABLE messages (session_id TEXT, role TEXT, content TEXT, "
                "timestamp INT, tool_name TEXT)")
    con.execute("INSERT INTO sessions VALUES (?, 'cli', 'claude-sonnet-4-6', NULL, "
                "1750000000, 1750000100, 100, 40, 0, 0, 0, 0.01, 0.01, 'sess', "
                "'anthropic', NULL, 'done')", (sid,))
    con.commit()
    con.close()


# ---------------------------------------------------------------------------
# Codex (#350)
# ---------------------------------------------------------------------------

def test_codex_partial_rollout_parse_keeps_durable_totals(scan_env, monkeypatch):
    """Two rollout files for one session id: older 15,000 tokens, newer
    1,200,000. The newer file then gains a schema-drifted line (``payload`` is
    a string, not a dict) that aborts its parse. The truncated 15,000-token
    result must stay a stub: not cached, and not written over the durable
    1,200,000-token row."""
    sid = "aabbccdd-1111-2222-3333-000000000350"
    codex_dir = scan_env / ".codex"
    day = codex_dir / "sessions" / "2026" / "09" / "10"
    day.mkdir(parents=True)
    monkeypatch.setattr(main, "CODEX_DIR", codex_dir)

    meta = json.dumps({
        "timestamp": "2026-09-10T10:00:00.000Z", "type": "session_meta",
        "payload": {"id": sid, "cwd": "/tmp/proj", "model_provider": "openai"},
    }) + "\n"
    older = day / f"rollout-2026-09-10T10-00-00-{sid}.jsonl"
    newer = day / f"rollout-2026-09-10T11-00-00-{sid}.jsonl"
    older.write_text(meta + _codex_token_line("2026-09-10T10:05:00.000Z", 10_000, 5_000),
                     encoding="utf-8")
    newer_good = _codex_token_line("2026-09-10T11:05:00.000Z", 1_000_000, 200_000)
    newer.write_text(newer_good, encoding="utf-8")

    # Scan 1: both files parse; the full total lands in the durable store.
    data, _ = _scan_and_persist()
    live = next(s for s in data if s["agent"] == "codex" and s["id"] == sid)
    assert live["stub"] is False
    assert live["tokens"]["total"] == 1_200_000
    assert _stored("codex")[sid]["tokens"]["total"] == 1_200_000

    # Schema drift at the top of the newer file: data["payload"].get(...) raises
    # before its token_count line is reached. Bump the mtime to force a cache miss.
    drifted = json.dumps({"type": "session_meta", "payload": "drifted"}) + "\n"
    newer.write_text(drifted + newer_good, encoding="utf-8")
    _bump_mtime(newer)

    # Scan 2: partial parse.
    data, _ = _scan_and_persist()
    live = next(s for s in data if s["agent"] == "codex" and s["id"] == sid)
    assert live["stub"] is True, "a partial parse must not be marked authoritative"
    source_mtime = max(older.stat().st_mtime, newer.stat().st_mtime)
    assert scan_cache.read_cache("codex", sid, source_mtime) is None, (
        "a partial parse must not be cached for the current source mtime")
    row = _stored("codex")[sid]
    assert row["tokens"]["total"] == 1_200_000, (
        "durable totals must survive a partial parse")
    assert row["source_present"] is True

    # Scan 3: the file is whole again — a legitimately changed total goes through.
    newer.write_text(_codex_token_line("2026-09-10T11:05:00.000Z", 900_000, 100_000),
                     encoding="utf-8")
    _bump_mtime(newer, 20)
    data, _ = _scan_and_persist()
    live = next(s for s in data if s["agent"] == "codex" and s["id"] == sid)
    assert live["stub"] is False
    assert _stored("codex")[sid]["tokens"]["total"] == 1_000_000, (
        "a complete parse must still be able to lower the durable total")


# ---------------------------------------------------------------------------
# Cline (#222)
# ---------------------------------------------------------------------------

def test_cline_locked_db_does_not_mark_sessions_absent(scan_env, monkeypatch):
    """A writer holding sessions.db exclusively makes the scanner's query fail
    with "database is locked". Cline's known sessions must stay
    source_present; rows of agents that scanned cleanly are still pruned."""
    import history_store
    cline_dir = scan_env / ".cline"
    db = cline_dir / "data" / "db" / "sessions.db"
    _build_cline_db(db, "cline-sess-1", str(scan_env / "proj"))
    monkeypatch.setattr(main, "CLINE_DIR", cline_dir)

    data, incomplete = _scan_and_persist()
    assert incomplete == set()
    assert [s["id"] for s in data if s["agent"] == "cline"] == ["cline-sess-1"]
    assert _stored("cline")["cline-sess-1"]["source_present"] is True

    # A session of another agent that genuinely left the disk — the control.
    history_store.upsert_sessions([{
        "agent": "claude", "id": "gone-1", "project": "/p", "model": "m",
        "timestamp": "2026-06-01T00:00:00+00:00", "cost": 0.0,
        "tokens": {"input": 1, "output": 1, "cached": 0, "total": 2},
    }])

    writer = sqlite3.connect(db, isolation_level=None)
    writer.execute("BEGIN EXCLUSIVE")
    try:
        data, incomplete = _scan_and_persist()
    finally:
        writer.execute("ROLLBACK")
        writer.close()

    assert not [s for s in data if s["agent"] == "cline"]
    assert incomplete == {"cline"}
    row = _stored("cline")["cline-sess-1"]
    assert row["source_present"] is True, (
        "a failed Cline read must not flag its sessions as gone")
    assert row["tokens"]["total"] == 1200
    assert _stored("claude")["gone-1"]["source_present"] is False, (
        "agents that scanned cleanly must still be pruned")

    # Lock released, and the session really is deleted: a clean, empty read
    # is evidence of absence and must prune.
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM sessions")
    conn.commit()
    conn.close()
    data, incomplete = _scan_and_persist()
    assert incomplete == set()
    assert _stored("cline")["cline-sess-1"]["source_present"] is False


def test_cline_unreadable_vscode_history_reports_incomplete(scan_env, monkeypatch):
    """The VS Code taskHistory.json store has the same failure shape."""
    vscode_dir = scan_env / "cline-vscode"
    (vscode_dir / "state").mkdir(parents=True)
    (vscode_dir / "state" / "taskHistory.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(main, "CLINE_VSCODE_DIR", vscode_dir)

    incomplete = set()
    assert main._scan_cline_sessions(incomplete) == []
    assert incomplete == {"cline"}
    # The out-param stays optional for callers that don't persist.
    assert main._scan_cline_sessions() == []


# ---------------------------------------------------------------------------
# Hermes (#223)
# ---------------------------------------------------------------------------

def test_hermes_failing_profile_db_does_not_mark_sessions_absent(scan_env, monkeypatch):
    """One profile's state.db becomes unreadable between scans. The healthy
    root DB still scans; the failed profile's session stays source_present."""
    home = scan_env / ".hermes"
    monkeypatch.setattr(main, "HERMES_DIR", home)
    monkeypatch.setattr(main, "HERMES_DB", home / "state.db")
    monkeypatch.setattr(main, "HERMES_PROFILES_DIR", home / "profiles")
    root_sid, coder_sid = "20260101_000000_aaaa1111", "20260102_000000_bbbb2222"
    coder_db = home / "profiles" / "coder" / "state.db"
    _build_hermes_db(home / "state.db", root_sid)
    _build_hermes_db(coder_db, coder_sid)

    data, incomplete = _scan_and_persist()
    assert incomplete == set()
    assert {s["id"] for s in data if s["agent"] == "hermes"} == {root_sid, coder_sid}
    stored = _stored("hermes")
    assert stored[root_sid]["source_present"] and stored[coder_sid]["source_present"]

    # Not a SQLite file any more: every query against it raises DatabaseError.
    coder_db.write_bytes(b"this is not a sqlite database" * 64)

    data, incomplete = _scan_and_persist()
    assert {s["id"] for s in data if s["agent"] == "hermes"} == {root_sid}
    assert incomplete == {"hermes"}
    stored = _stored("hermes")
    assert stored[coder_sid]["source_present"] is True, (
        "a failed Hermes profile read must not flag its sessions as gone")
    assert stored[coder_sid]["tokens"]["total"] == 140
    assert stored[root_sid]["source_present"] is True


# ---------------------------------------------------------------------------
# Persistence wiring
# ---------------------------------------------------------------------------

def test_mark_absent_skip_agents(scan_env):
    import history_store
    rows = [{"agent": a, "id": "s1", "project": "/p", "model": "m",
             "timestamp": "2026-06-01T00:00:00+00:00", "cost": 0.0,
             "tokens": {"input": 1, "output": 1, "cached": 0, "total": 2}}
            for a in ("cline", "claude")]
    history_store.upsert_sessions(rows)
    history_store.mark_absent(set(), skip_agents={"cline"})
    present = {r["agent"]: r["source_present"] for r in history_store.query()}
    assert present == {"cline": True, "claude": False}


def test_get_sessions_cached_forwards_incomplete_agents(scan_env, monkeypatch):
    """The live scan path must hand the scanner's incomplete set to the persist
    job — otherwise the guard exists but is never fed."""
    captured = {}

    def fake_scan(incomplete_agents=None):
        incomplete_agents.add("hermes")
        return []

    monkeypatch.setattr(main, "_scan_sessions_sync", fake_scan)
    monkeypatch.setattr(main, "_persist_history_async",
                        lambda data, **kw: captured.update(kw))
    monkeypatch.setattr(main, "_sessions_cache", {"data": None, "at": 0.0, "building": False})
    monkeypatch.setattr(main, "_sessions_lock", None)
    monkeypatch.setattr(main, "_harness_scan_reported", True)

    asyncio.run(main.get_sessions_cached(fresh=True))

    assert captured.get("incomplete_agents") == {"hermes"}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
