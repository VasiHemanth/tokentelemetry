"""Tests for Hermes profile attribution and the /hermes/profiles endpoint.

A Hermes profile (~/.hermes/profiles/<name>/) is a full parallel agent home
with its own state.db, logs, cron, and gateway. Covers:
  - _hermes_dbs_with_profiles(): root tagged None, profile DBs tagged by name.
  - _scan_sessions_sync(): sessions from a profile DB carry hermes_profile.
  - _hermes_session_profile(): resolves which home owns a session id.
  - _hermes_log_summary(profile=...): reads the profile's agent.log.
  - _hermes_cwd_by_session(): merges root + profile logs.
  - /hermes/profiles: metadata + per-profile usage rollup, active marker.

Run: pytest backend/test_hermes_profiles.py
"""
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


def _run(coro):
    return asyncio.run(coro)


def _make_hermes_db(path: Path, sid: str, tokens=(100, 40)):
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
                "1750000000, 1750000100, ?, ?, 0, 0, 0, 0.01, 0.01, 'sess', "
                "'anthropic', NULL, 'done')", (sid, tokens[0], tokens[1]))
    con.commit()
    con.close()


@pytest.fixture
def hermes_env(tmp_path, monkeypatch):
    """Hermetic Hermes home: root state.db plus one 'coder' profile."""
    missing = tmp_path / "missing"
    for attr in ("CODEX_DIR", "GEMINI_DIR", "QWEN_DIR", "VIBE_DIR", "OLLAMA_DIR",
                 "GROK_SESSIONS_DIR", "VSCODE_STORAGE", "CURSOR_STORAGE",
                 "COPILOT_CLI_DIR", "ANTIGRAVITY_BRAIN_DIR", "ANTIGRAVITY_CLI_DIR",
                 "PI_SESSIONS_DIR"):
        monkeypatch.setattr(main, attr, missing / attr.lower())
    monkeypatch.setattr(main, "ANTIGRAVITY_BRAIN_SOURCES", [])
    monkeypatch.setattr(main, "ANTIGRAVITY_BRAIN_DIRS", [])
    monkeypatch.setattr(main, "_antigravity_cli_meta", lambda *a, **k: {})
    monkeypatch.setattr(main, "CLAUDE_DIR", tmp_path / ".claude")
    monkeypatch.setattr(main, "CURSOR_DIR", tmp_path / ".cursor")
    monkeypatch.setattr(main, "OPENCODE_DB", tmp_path / "opencode.db")
    monkeypatch.setattr(main, "PROJECT_ALIASES_FILE", tmp_path / "aliases.json")
    monkeypatch.setenv("TOKENTELEMETRY_DATA_DIR", str(tmp_path / "tt_data"))

    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setattr(main, "HERMES_DIR", home)
    monkeypatch.setattr(main, "HERMES_DB", home / "state.db")
    monkeypatch.setattr(main, "HERMES_PROFILES_DIR", home / "profiles")
    _make_hermes_db(home / "state.db", "20260101_000000_aaaa1111")
    _make_hermes_db(home / "profiles" / "coder" / "state.db",
                    "20260102_000000_bbbb2222", tokens=(50, 20))
    return home


def test_dbs_with_profiles(hermes_env):
    got = main._hermes_dbs_with_profiles()
    assert [(p.parent.name if prof else "root", prof) for p, prof in got] == \
        [("root", None), ("coder", "coder")]
    assert main._hermes_dbs() == [p for p, _ in got]


def test_scan_tags_profile(hermes_env):
    by_id = {s["id"]: s for s in main._scan_sessions_sync()
             if s["agent"] == "hermes"}
    assert len(by_id) == 2
    assert "hermes_profile" not in by_id["20260101_000000_aaaa1111"]
    assert by_id["20260102_000000_bbbb2222"]["hermes_profile"] == "coder"


def test_session_profile_resolver(hermes_env):
    assert main._hermes_session_profile("20260101_000000_aaaa1111") is None
    assert main._hermes_session_profile("20260102_000000_bbbb2222") == "coder"
    assert main._hermes_session_profile("20260103_000000_cccc3333") is None


def test_log_summary_reads_profile_log(hermes_env):
    sid = "20260102_000000_bbbb2222"
    line = (f"2026-01-02 00:00:05,123 INFO [{sid}] API call #1: "
            "model=claude-sonnet-4-6 provider=anthropic in=50 out=20 total=70 "
            "latency=1.5s\n")
    logs = hermes_env / "profiles" / "coder" / "logs"
    logs.mkdir(parents=True)
    (logs / "agent.log").write_text(line, encoding="utf-8")
    # Root log has no trace of the session → empty without the profile arg.
    assert main._hermes_log_summary(sid)["summary"] is None
    summ = main._hermes_log_summary(sid, "coder")["summary"]
    assert summ["api_call_count"] == 1
    assert summ["total_latency_s"] == 1.5


def test_cwd_map_merges_profile_logs(hermes_env):
    root_logs = hermes_env / "logs"
    root_logs.mkdir()
    (root_logs / "agent.log").write_text(
        "2026-01-01 00:00:01,000 INFO [20260101_000000_aaaa1111] terminal "
        "sandbox init cwd=/tmp/rootproj\n", encoding="utf-8")
    prof_logs = hermes_env / "profiles" / "coder" / "logs"
    prof_logs.mkdir(parents=True)
    (prof_logs / "agent.log").write_text(
        "2026-01-02 00:00:01,000 INFO [20260102_000000_bbbb2222] terminal "
        "sandbox init cwd=/tmp/coderproj\n", encoding="utf-8")
    cwds = main._hermes_cwd_by_session()
    assert cwds["20260101_000000_aaaa1111"] == "/tmp/rootproj"
    assert cwds["20260102_000000_bbbb2222"] == "/tmp/coderproj"


def test_profiles_endpoint(hermes_env, monkeypatch):
    (hermes_env / "SOUL.md").write_text("root soul", encoding="utf-8")
    coder = hermes_env / "profiles" / "coder"
    (coder / "profile.yaml").write_text(
        "name: coder\ndescription: 'Coding assistant persona'\n",
        encoding="utf-8")
    (coder / "SOUL.md").write_text("coder soul", encoding="utf-8")
    for skill in ("devops", "research"):
        (coder / "skills" / skill).mkdir(parents=True)
    (coder / "skills" / ".curator_state").mkdir()  # hidden → not counted
    (coder / "cron").mkdir()
    (coder / "cron" / "jobs.json").write_text(json.dumps({"jobs": [
        {"id": "j1", "name": "daily", "schedule": {"kind": "daily"}},
    ]}), encoding="utf-8")
    (hermes_env / "active_profile").write_text("coder\n", encoding="utf-8")

    async def fake_sessions(fresh=False):
        ts = datetime(2026, 1, 2, tzinfo=timezone.utc)
        return [
            {"agent": "hermes", "cost": 0.01, "timestamp": ts,
             "tokens": {"input": 100, "output": 40, "total": 140}},
            {"agent": "hermes", "hermes_profile": "coder", "cost": 0.005,
             "timestamp": ts, "tokens": {"input": 50, "output": 20, "total": 70}},
            {"agent": "claude", "cost": 9.99, "timestamp": ts,
             "tokens": {"input": 1, "output": 1, "total": 2}},
        ]
    monkeypatch.setattr(main, "get_sessions_cached", fake_sessions)

    res = _run(main.hermes_profiles())
    assert res["active_profile"] == "coder"
    by_name = {p["name"]: p for p in res["profiles"]}
    assert set(by_name) == {"default", "coder"}

    d = by_name["default"]
    assert d["is_default"] is True and d["active"] is False
    assert d["soul_exists"] is True
    assert d["usage"]["sessions"] == 1
    assert d["usage"]["total_tokens"] == 140

    c = by_name["coder"]
    assert c["active"] is True
    assert c["description"] == "Coding assistant persona"
    assert c["skills_count"] == 2
    assert c["cron_jobs"] == 1
    cu = c["usage"]
    assert cu["sessions"] == 1
    assert cu["input_tokens"] == 50 and cu["output_tokens"] == 20
    assert cu["total_tokens"] == 70
    assert cu["cost"] == 0.005
    assert cu["last_activity"] == "2026-01-02T00:00:00+00:00"
    # The canned session is older than 14 days → burn windows and the 14-day
    # sparkline are all zero, but the shape is always present.
    assert cu["cost_7d"] == 0.0 and cu["cost_prev_7d"] == 0.0
    assert cu["unattended_cost_7d"] == 0.0
    assert len(cu["daily"]) == 14
    assert all(d["cost"] == 0.0 for d in cu["daily"])


def test_profiles_endpoint_no_hermes(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "HERMES_DIR", tmp_path / "nope")
    monkeypatch.setattr(main, "HERMES_PROFILES_DIR", tmp_path / "nope" / "profiles")
    res = _run(main.hermes_profiles())
    assert res == {"profiles": [], "active_profile": None}


def test_profiles_burn_windows(hermes_env, monkeypatch):
    from datetime import timedelta
    now = datetime.now(timezone.utc)

    async def fake_sessions(fresh=False):
        return [
            # yesterday, unattended (cron) → cost_7d + unattended_cost_7d
            {"agent": "hermes", "cost": 1.0, "timestamp": now - timedelta(days=1),
             "source_subtype": "cron", "tokens": {"total": 10}},
            # yesterday, interactive → cost_7d only
            {"agent": "hermes", "cost": 0.5, "timestamp": now - timedelta(days=1),
             "source_subtype": "cli", "tokens": {"total": 10}},
            # 10 days ago → prev window
            {"agent": "hermes", "cost": 2.0, "timestamp": now - timedelta(days=10),
             "source_subtype": "cli", "tokens": {"total": 10}},
        ]
    monkeypatch.setattr(main, "get_sessions_cached", fake_sessions)

    u = _run(main.hermes_profiles())
    d = {p["name"]: p for p in u["profiles"]}["default"]["usage"]
    assert d["cost_7d"] == pytest.approx(1.5)
    assert d["unattended_cost_7d"] == pytest.approx(1.0)
    assert d["cost_prev_7d"] == pytest.approx(2.0)
    # The 14-day sparkline spans BOTH windows, so all three sessions land in it.
    assert sum(x["cost"] for x in d["daily"]) == pytest.approx(3.5)
    # A profile with zero sessions still gets a zero-filled 14-day series so
    # frontend sparklines align.
    c = {p["name"]: p for p in u["profiles"]}["coder"]["usage"]
    assert len(c["daily"]) == 14 and all(x["cost"] == 0.0 for x in c["daily"])


def test_budget_filter_hermes_profile():
    coder = {"agent": "hermes", "hermes_profile": "coder"}
    root = {"agent": "hermes"}
    assert main._session_matches_filters(coder, {"hermes_profile": "coder"})
    assert not main._session_matches_filters(root, {"hermes_profile": "coder"})
    assert main._session_matches_filters(root, {"hermes_profile": "default"})
    assert not main._session_matches_filters(coder, {"hermes_profile": "default"})


# --- kanban cost board --------------------------------------------------------

def _make_kanban_db(path: Path, with_session_col: bool = True):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    sid_col = ", session_id TEXT" if with_session_col else ""
    con.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, title TEXT, body TEXT, "
                "assignee TEXT, status TEXT, priority INTEGER DEFAULT 0, "
                "created_at INTEGER, started_at INTEGER, completed_at INTEGER, "
                "consecutive_failures INTEGER DEFAULT 0, last_failure_error TEXT"
                f"{sid_col})")
    con.execute("CREATE TABLE task_runs (id INTEGER PRIMARY KEY, task_id TEXT, "
                "profile TEXT, status TEXT, outcome TEXT, started_at INTEGER)")
    if with_session_col:
        con.execute("INSERT INTO tasks (id, title, assignee, status, created_at, "
                    "completed_at, session_id) VALUES "
                    "('t1', 'build UI', 'frontend-eng', 'done', 1750000000, "
                    "1750000500, '20260102_000000_bbbb2222')")
        con.execute("INSERT INTO tasks (id, title, assignee, status, created_at, "
                    "consecutive_failures, last_failure_error, session_id) VALUES "
                    "('t2', 'flaky deploy', 'devops', 'blocked', 1750000000, 2, "
                    "'spawn timeout', NULL)")
        con.execute("INSERT INTO task_runs (task_id, profile, status, outcome, "
                    "started_at) VALUES ('t1', 'coder', 'done', 'completed', 1750000000)")
        con.execute("INSERT INTO task_runs (task_id, profile, status, outcome, "
                    "started_at) VALUES ('t2', 'coder', 'crashed', 'timed_out', 1750000000)")
    else:
        con.execute("INSERT INTO tasks (id, title, assignee, status, created_at) "
                    "VALUES ('old1', 'legacy task', 'worker', 'todo', 1750000000)")
    con.commit()
    con.close()


def test_kanban_endpoint_joins_session_cost(hermes_env, monkeypatch):
    _make_kanban_db(hermes_env / "kanban.db")

    async def fake_sessions(fresh=False):
        return [{"id": "20260102_000000_bbbb2222", "agent": "hermes",
                 "cost": 0.25, "tokens": {"total": 70},
                 "timestamp": datetime(2026, 1, 2, tzinfo=timezone.utc)}]
    monkeypatch.setattr(main, "get_sessions_cached", fake_sessions)

    res = _run(main.hermes_kanban())
    assert res["installed"] is True
    assert len(res["boards"]) == 1
    b = res["boards"][0]
    assert b["profile"] is None and b["board"] == "default"
    by_id = {t["id"]: t for t in b["tasks"]}
    assert by_id["t1"]["cost"] == 0.25 and by_id["t1"]["tokens"] == 70
    assert by_id["t1"]["runs"] == {"count": 1, "failed": 0, "profiles": ["coder"]}
    assert by_id["t2"]["cost"] == 0.0
    assert by_id["t2"]["runs"]["failed"] == 1
    assert by_id["t2"]["last_failure_error"] == "spawn timeout"
    assert b["totals"]["cost"] == pytest.approx(0.25)
    assert b["totals"]["by_status"] == {"done": 1, "blocked": 1}
    assert b["totals"]["by_assignee"][0] == {"assignee": "frontend-eng",
                                             "tasks": 1, "cost": 0.25}


def test_kanban_endpoint_tolerates_old_schema_and_boards(hermes_env, monkeypatch):
    # Pre-migration DB without session_id, plus a named board in a profile home.
    _make_kanban_db(hermes_env / "kanban.db", with_session_col=False)
    _make_kanban_db(hermes_env / "profiles" / "coder" / "kanban" / "boards" /
                    "swarm" / "kanban.db")

    async def fake_sessions(fresh=False):
        return []
    monkeypatch.setattr(main, "get_sessions_cached", fake_sessions)

    res = _run(main.hermes_kanban())
    keys = [(b["profile"], b["board"]) for b in res["boards"]]
    assert keys == [(None, "default"), ("coder", "swarm")]
    legacy = res["boards"][0]["tasks"][0]
    assert legacy["session_id"] is None and legacy["cost"] == 0.0


def test_kanban_endpoint_no_dbs(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "HERMES_DIR", tmp_path / "nope")
    monkeypatch.setattr(main, "HERMES_PROFILES_DIR", tmp_path / "nope" / "profiles")
    res = _run(main.hermes_kanban())
    assert res == {"installed": False, "boards": []}
